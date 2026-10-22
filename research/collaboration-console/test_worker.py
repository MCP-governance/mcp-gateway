import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from worker import Hub, Outcome, pid_identity, public_snapshot, redact, reset_at, service_lock


class Checks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "config.json").write_text(json.dumps({"providers": {p: {"executable": "missing-cli", "model": "test", "effort": "high"} for p in ("codex", "claude", "antigravity")}}))
        self.prompt = self.root / "prompt.md"
        self.prompt.write_text("read only check")
        self.hub = Hub(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def add(self, provider="codex", **kwargs):
        return self.hub.add(provider, "check", self.root, self.prompt, **kwargs)

    def test_dependency_and_provider_hold(self):
        first = self.add()
        self.add("antigravity", deps=[first])
        self.hub.hold("codex", time.time() + 3600, "quota")
        self.assertIsNone(self.hub.claim())
        self.hub.hold("codex", 0, "released")
        self.assertEqual(self.hub.claim()["id"], first)
        self.assertIsNone(self.hub.claim())

    def test_same_provider_cannot_be_nested(self):
        self.add()
        self.hub.claim()
        second = self.add()
        self.assertIsNone(self.hub.claim(second, nested=True))
        reviewer = self.add("antigravity")
        self.assertEqual(self.hub.claim(reviewer, nested=True)["id"], reviewer)

    def test_warning_and_quoted_quota_are_not_errors(self):
        result = Outcome("claude")
        result.feed({"type": "rate_limit_event", "rate_limit_info": {"status": "allowed_warning", "resetsAt": time.time() + 300}})
        self.assertFalse(result.limited)
        result = Outcome("codex")
        result.feed({"type": "item.completed", "item": {"type": "agent_message", "text": "Fix rate limit handling"}})
        result.feed({"type": "turn.completed"})
        self.assertTrue(result.done)
        self.assertFalse(result.limited)

    def test_structured_limit_and_reset(self):
        now = time.time()
        result = Outcome("claude")
        result.feed({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "rate_limit_type": "seven_day", "resetsAt": now + 600}})
        self.assertTrue(result.limited)
        self.assertGreaterEqual(result.retry_at, now + 660)
        self.assertAlmostEqual(reset_at({"reset_at": (now + 400) * 1000}, now), now + 460, delta=0.001)

    def test_human_reset_and_fallback(self):
        from datetime import datetime
        now = datetime.fromisoformat("2026-10-21T14:00:00+09:00").timestamp()
        self.assertEqual(reset_at({"error": "try again at 5:21 PM (Asia/Seoul)"}, now), datetime.fromisoformat("2026-10-21T17:22:00+09:00").timestamp())
        self.assertEqual(reset_at({}, now), now + 18300)
        self.assertEqual(reset_at({"error": "resets at 2:00 PM UTC"}, now), datetime.fromisoformat("2026-10-21T23:01:00+09:00").timestamp())

    def test_provider_retry_delay_is_respected_without_five_hour_sleep(self):
        now=time.time()
        self.assertAlmostEqual(reset_at({'error':{'retryDelay':'12s'}},now),now+13,delta=0.01)
        self.assertEqual(reset_at({'reset_at':'inf'},now),now+18300)

    def test_vendor_terminal_shapes(self):
        result = Outcome("antigravity")
        result.feed({"event": "result", "result": {"conversation_id": "abc", "status": "SUCCESS", "response": "review passed"}})
        self.assertTrue(result.done)
        self.assertEqual(result.session, "abc")
        result = Outcome("codex")
        result.feed({"type": "turn.failed", "error": {"message": "usage limit exceeded"}})
        self.assertTrue(result.limited)

    def test_observed_codex_capacity_is_distinct_from_quota(self):
        result = Outcome("codex")
        result.feed({"type": "error", "message": "Selected model is at capacity. Please try a different model."})
        result.feed({"type": "turn.failed", "error": {"message": "Selected model is at capacity. Please try a different model."}})
        self.assertTrue(result.capacity)
        self.assertFalse(result.limited)

    def test_antigravity_progress_is_not_terminal_and_error_is_quota(self):
        result = Outcome("antigravity")
        result.feed({"event": "step_update", "status": "SUCCESS", "response": "partial"})
        self.assertFalse(result.done)
        self.assertFalse(result.error)
        result.feed({"event": "error", "error": {"code": 429, "message": "RESOURCE_EXHAUSTED"}})
        self.assertTrue(result.limited)

    def test_orphan_exit_changes_to_attention(self):
        self.add()
        job = self.hub.claim()
        with self.hub.db() as db:
            db.execute("UPDATE jobs SET state='orphan_running',pid=99999999,identity='gone' WHERE id=?", (job["id"],))
        self.hub.reap()
        self.assertEqual(self.hub.snapshot()["jobs"][0]["state"], "needs_attention")

    def test_antigravity_prompt_uses_stdin(self):
        self.add("antigravity")
        command, stdin = self.hub.command(self.hub.claim(), "private evidence")
        self.assertNotIn("private evidence", command)
        self.assertIn("stream-json", command)
        self.assertEqual(json.loads(stdin)["message"]["content"], "private evidence")

    def test_launch_failure_is_not_completed_or_auto_replayed(self):
        self.add()
        self.hub.run(self.hub.claim())
        job = self.hub.snapshot()["jobs"][0]
        self.assertEqual(job["state"], "needs_attention")
        self.assertIsNone(self.hub.claim())

    def test_quota_is_persisted_with_session(self):
        self.add()
        job = self.hub.claim()
        class FakeProcess:
            pid, returncode = 12345, 1
            import io
            stdin = io.StringIO()
            stdout = io.StringIO(json.dumps({"type": "thread.started", "thread_id": "session-123"}) + "\n" + json.dumps({"type": "turn.failed", "error": {"message": "usage limit exceeded"}}) + "\n")
            def wait(self, timeout=None):
                return 1
            def poll(self):
                return 1
        with patch("worker.subprocess.Popen", return_value=FakeProcess()), patch("worker.pid_identity", return_value="identity"):
            self.hub.run(job)
        self.hub = Hub(self.root)
        job = self.hub.snapshot()["jobs"][0]
        self.assertEqual(job["state"], "waiting_quota")
        self.assertEqual(job["session"], "session-123")
        self.assertIsNone(self.hub.claim())

    def test_crash_recovery_preserves_unknown_write(self):
        self.add(mode="danger-full-access")
        job = self.hub.claim()
        self.hub.recover()
        self.assertEqual(self.hub.snapshot()["jobs"][0]["state"], "needs_attention")
        self.assertIsNone(self.hub.claim())

    def test_pid_identity_and_redaction(self):
        import os
        self.assertIsNotNone(pid_identity(os.getpid()))
        self.assertIsNone(pid_identity(99999999))
        self.assertNotIn("sk-", redact("sk-abcdefghijklmnopqrst"))
        self.assertNotIn("abc123", redact("Bearer abc123"))
        self.assertNotIn("credential-value", redact('{"api_key": "credential-value"}'))

    def test_duplicate_service_lock(self):
        with service_lock(self.root):
            with self.assertRaises(OSError):
                with service_lock(self.root):
                    pass

    def test_same_request_returns_existing_job(self):
        first=self.add(task_id='DUP-1')
        self.assertEqual(self.add(task_id='DUP-1'),first)
        with self.hub.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],1)

    def test_anonymous_duplicate_and_nested_requests_do_not_create_calls(self):
        self.assertEqual(self.add(),self.add())
        with patch.dict('os.environ',{'MINT_COORDINATED_JOB':'running-job'}):
            with self.assertRaisesRegex(ValueError,'cannot enqueue'):
                self.add('antigravity')

    def test_normal_work_does_not_wait_two_minutes(self):
        self.add(task_id='FAST-1')
        first=self.hub.claim()
        with self.hub.db() as db:
            db.execute("UPDATE jobs SET state='completed' WHERE id=?",(first['id'],))
            db.execute("UPDATE events SET at=? WHERE job=? AND state='running'",(time.time()-10,first['id']))
        second=self.add(task_id='FAST-2')
        self.assertEqual(self.hub.claim(second)['id'],second)

    def test_workflow_attempt_budget_is_shared_across_roles(self):
        first=self.hub.add('codex','first',self.root,self.prompt,job_id='wf-first',task_id='FLOW-1')
        second=self.hub.add('antigravity','review',self.root,self.prompt,job_id='wf-review',task_id='FLOW-1')
        with self.hub.db() as db:
            db.execute("UPDATE jobs SET state='completed',attempts=8 WHERE id=?",(first,))
        self.assertIsNone(self.hub.claim(second))
        self.assertIn('budget',self.hub.snapshot()['jobs'][0]['error'].lower())

    def test_hourly_budget_and_gap_defer_without_launching(self):
        self.hub.config['limits']={'provider_gap_seconds':120}
        self.add(task_id='RATE-1')
        first=self.hub.claim()
        with self.hub.db() as db:
            db.execute("UPDATE jobs SET state='completed' WHERE id=?",(first['id'],))
        second=self.add(task_id='RATE-2')
        self.assertIsNone(self.hub.claim(second))
        with self.hub.db() as db:
            self.assertGreater(db.execute('SELECT next_at FROM jobs WHERE id=?',(second,)).fetchone()[0],time.time()+100)

    def test_token_budget_stops_calls(self):
        self.hub.config['limits']={'observed_tokens_per_day':200000}
        self.add(task_id='TOKEN-1')
        with self.hub.db() as db:
            db.execute('INSERT INTO call_usage VALUES(?,?,?,?,?)',('old','codex',time.time(),200000,1))
        self.assertIsNone(self.hub.claim())
        self.assertEqual(self.hub.snapshot()['jobs'][0]['state'],'waiting_budget')

    def test_resume_uses_native_subcommand_without_new_sandbox(self):
        job={'provider':'codex','session':'01a13365-044b-7392-8264-a37172f443f7','mode':'read-only','cwd':str(self.root)}
        command,_=self.hub.command(job,'continue')
        self.assertEqual(command[command.index('exec'):command.index('exec')+2],['exec','resume'])
        self.assertNotIn('-s',command)
        self.assertNotIn('-C',command)

    def test_provider_diagnostics_and_results_are_bounded(self):
        result=Outcome('codex')
        for _ in range(100):
            result.feed({'type':'error','message':'transport failed'})
            result.feed({'type':'item.completed','item':{'type':'agent_message','text':'x'*40000}})
        self.assertLessEqual(len(result.diagnostics),12)
        self.assertLessEqual(len(result.schemas),32)
        self.assertLessEqual(sum(map(len,result.texts)),128000)

    def test_cli_that_never_reads_stdin_is_stopped_on_startup_timeout(self):
        import sys
        script=self.root/'silent.py'
        script.write_text('import time; time.sleep(30)')
        self.hub.config['startup_timeout_seconds']=0.1
        self.add(mode='workspace-write',task_id='SILENT-1')
        started=time.monotonic()
        with patch.object(self.hub,'command',return_value=([sys.executable,str(script)],'x'*24000)):
            self.hub.run(self.hub.claim())
        self.assertLess(time.monotonic()-started,8)
        job=self.hub.snapshot()['jobs'][0]
        self.assertEqual(job['state'],'needs_attention')
        self.assertIn('timeout',job['error'])

    def test_prompt_preparation_error_is_not_left_running(self):
        self.add(task_id='MISSING-1')
        job=self.hub.claim()
        self.prompt.unlink()
        self.hub.run(job)
        self.assertEqual(self.hub.snapshot()['jobs'][0]['state'],'needs_attention')
        self.assertIsNone(self.hub.claim())

    def test_expiration_does_not_launch(self):
        self.add(until=time.time() - 10)
        self.assertIsNone(self.hub.claim())
        self.assertEqual(self.hub.snapshot()["jobs"][0]["state"], "expired")

    def test_public_snapshot_does_not_create_missing_queue(self):
        missing = self.root / "missing"
        self.assertFalse(public_snapshot(missing)["available"])
        self.assertFalse(missing.exists())

    def test_console_bridge_routes_real_artifact_once_and_keeps_task_id(self):
        from console import EventLog
        log = EventLog(self.root / "public-events.jsonl")
        job_id = self.add("antigravity", task_id="DEV-81")
        self.hub.sync_console(log)
        self.assertEqual(log.snapshot()["events"][0]["to"], "Gemini")
        result = self.hub.runtime / "results" / "review.md"
        result.parent.mkdir()
        result.write_text("ACK DEV-81; bounded test artifact; verify before integration", encoding="utf-8")
        with self.hub.db() as db:
            db.execute("UPDATE jobs SET state='completed',result=?,updated=? WHERE id=?", (str(result),time.time(),job_id))
            self.hub.event(db,job_id,"completed",str(result))
        self.hub.sync_console(log)
        self.hub.sync_console(log)
        replies = [event for event in log.snapshot()["events"] if event["author"] == "Gemini"]
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0]["to"], "Codex")
        self.assertEqual(replies[0]["task_id"], "DEV-81")
        self.assertIn("ACK DEV-81", replies[0]["body"])
        import os
        os.utime(result, (time.time()-60,time.time()-60))
        with self.hub.db() as db:
            db.execute("UPDATE jobs SET state='queued',updated=? WHERE id=?", (time.time(),job_id))
            self.hub.event(db,job_id,"queued","Operator resume")
        self.hub.sync_console(log)
        self.assertEqual(len([event for event in log.snapshot()["events"] if event["author"] == "Gemini"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
