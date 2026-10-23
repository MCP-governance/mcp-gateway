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

    def check_output_budget(self, chunks, expected):
        import io
        from unittest.mock import Mock
        partial = json.dumps({'type': 'result', 'result': 'saved partial result'}) + '\n'
        process = Mock(pid=12345, returncode=0, stdin=io.StringIO(),
                       stdout=Mock(wraps=io.StringIO(partial + ''.join(chunks))))
        # Seed only this temporary database; managed tests never enqueue an agent.
        with self.hub.db() as db:
            db.execute("INSERT INTO jobs(id,provider,title,cwd,prompt,deps,state,next_at,updated) VALUES(?,?,?,?,?,?,?,?,?)",
                       ('output-fixture', 'claude', 'check', str(self.root), str(self.prompt), '[]', 'running', time.time(), time.time()))
            job = dict(db.execute("SELECT * FROM jobs WHERE id='output-fixture'").fetchone())
        with patch('worker.subprocess.Popen', return_value=process), \
             patch('worker.pid_identity', return_value='fixture'), \
             patch.object(self.hub, 'stop_child') as stop:
            self.hub._run(job)
        job = self.hub.snapshot()['jobs'][0]
        self.assertEqual(job['state'], 'needs_attention')
        self.assertEqual(job['error'], expected)
        stop.assert_called_once_with(process)
        process.wait.assert_called_once_with(timeout=15)
        process.stdout.close.assert_called_once_with()
        self.assertTrue(process.stdin.closed)
        for call in process.stdout.readline.call_args_list:
            self.assertEqual(call.args, (524289,))
        report = Path(job['result']).read_text(encoding='utf-8')
        self.assertIn('saved partial result', report)
        self.assertIn(expected, report)
        self.assertNotIn('raw_cli_marker', report)
        metadata = json.loads(Path(job['result']).with_suffix('.json').read_text(encoding='utf-8'))
        self.assertTrue(metadata['error'])
        self.assertTrue(metadata['terminal_success'])
        self.assertIsNone(self.hub.claim())

    def test_single_line_output_budget_diagnostic(self):
        boundary = json.dumps({'type': 'progress'}).ljust(524287) + '\n'
        oversized = 'raw_cli_marker'.ljust(524289)
        self.check_output_budget([boundary, oversized],
            'CLI output budget exceeded: single line characters observed=524289 limit=524288')

    def test_aggregate_output_budget_diagnostic(self):
        partial = json.dumps({'type': 'result', 'result': 'saved partial result'}) + '\n'
        remaining = 8*1024*1024 - len(partial)
        chunk = json.dumps({'type': 'progress', 'data': 'raw_cli_marker'}).ljust(524287) + '\n'
        chunks = [chunk] * (remaining // len(chunk))
        chunks.append(json.dumps({'type': 'progress'}).ljust(remaining % len(chunk) - 1) + '\n')
        chunks.append('!')
        self.check_output_budget(chunks,
            'CLI output budget exceeded: aggregate characters observed=8388609 limit=8388608')

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

    def test_closed_workflow_clears_unclaimed_stages_without_touching_live_jobs(self):
        states=('queued','waiting_quota','waiting_service','waiting_budget','running','paused','needs_attention')
        for state in states:
            self.prompt.write_text('stage '+state)
            self.hub.add('codex',state,self.root,self.prompt,job_id='wf-closed-'+state,task_id='CLOSED')
        active=self.hub.add('antigravity','active',self.root,self.prompt,job_id='wf-active',task_id='ACTIVE')
        with self.hub.db() as db:
            db.execute('CREATE TABLE workflows (id TEXT PRIMARY KEY,state TEXT,spec TEXT)')
            db.executemany('INSERT INTO workflows VALUES(?,?,?)',[('CLOSED','closed','{}'),('ACTIVE','active','{}')])
            for state in states:
                db.execute('UPDATE jobs SET state=?,next_at=? WHERE id=?',(state,time.time()+3600,'wf-closed-'+state))
            db.execute('UPDATE jobs SET next_at=? WHERE id=?',(time.time()+3600,active))
        self.assertIsNone(self.hub.claim())
        self.assertIsNone(self.hub.claim())
        with self.hub.db() as db:
            for state in states:
                expected='closed' if state.startswith('waiting_') or state=='queued' else state
                self.assertEqual(db.execute('SELECT state FROM jobs WHERE id=?',('wf-closed-'+state,)).fetchone()[0],expected)
            self.assertEqual(db.execute('SELECT state FROM jobs WHERE id=?',(active,)).fetchone()[0],'queued')
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events WHERE state='closed'").fetchone()[0],4)

    def test_public_snapshot_keeps_old_waiting_jobs_beside_recent_completions(self):
        waiting=self.add(job_id='old-waiting')
        with self.hub.db() as db:
            db.execute("UPDATE jobs SET state='waiting_budget',updated=1 WHERE id=?",(waiting,))
            for index in range(45):
                db.execute("INSERT INTO jobs(id,provider,title,cwd,prompt,mode,state,updated) SELECT 'done-'||?,provider,title,cwd,prompt,mode,'completed',? FROM jobs WHERE id=?",(index,index+2,waiting))
        snapshot=public_snapshot(self.root)
        self.assertTrue(snapshot['available'])
        self.assertEqual(snapshot['jobs'][0]['id'],waiting)
        self.assertEqual(len(snapshot['jobs']),41)
        self.assertEqual(snapshot['jobs_truncated'],0)

    def test_public_snapshot_keeps_pending_workflows_and_handoffs(self):
        from handoffs import table
        table(self.hub)
        job=self.add()
        with self.hub.db() as db:
            db.execute('CREATE TABLE workflows (id TEXT PRIMARY KEY,spec TEXT,state TEXT,summary TEXT,created REAL,updated REAL)')
            for index in range(25):
                state='waiting' if index==0 else 'closed'
                db.execute('INSERT INTO workflows VALUES(?,?,?,?,?,?)',(str(index),'{}',state,'fixture',index,index))
                state='blocked' if index==0 else 'done'
                clone='handoff-job-'+str(index)
                db.execute("INSERT INTO jobs(id,provider,title,cwd,prompt,state,updated) SELECT ?,provider,title,cwd,prompt,'completed',? FROM jobs WHERE id=?",(clone,index,job))
                db.execute('INSERT INTO handoffs(request,root,task,source,job,round,state,created,updated) VALUES(?,?,?,?,?,?,?,?,?)',(str(index),str(index),'fixture',index,clone,1,state,index,index))
        snapshot=public_snapshot(self.root)
        self.assertTrue(snapshot['available'])
        self.assertEqual(len(snapshot['workflows']),21)
        self.assertEqual(snapshot['workflows'][0]['state'],'waiting')
        self.assertEqual(len(snapshot['handoffs']),21)
        self.assertEqual(snapshot['handoffs'][0]['state'],'blocked')

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

    def fake_run(self,job,events):
        import io
        class FakeProcess:
            pid,returncode=12345,0
            stdin=io.StringIO()
            stdout=io.StringIO(''.join(json.dumps(event)+'\n' for event in events))
            def wait(self,timeout=None):
                return 0
            def poll(self):
                return 0
        with patch('worker.subprocess.Popen',return_value=FakeProcess()),patch('worker.pid_identity',return_value='fixture'):
            self.hub.run(job)
        with self.hub.db() as db:
            return dict(db.execute('SELECT * FROM jobs WHERE id=?',(job['id'],)).fetchone())

    def test_explicit_model_mismatch_cannot_complete_an_opus_judgment(self):
        job_id=self.add('claude',agent='opus',phase='judge')
        result=self.fake_run(self.hub.claim(job_id),[{'type':'assistant','message':{'model':'different-model'}},{'type':'result','result':'VERDICT: PASS'}])
        self.assertEqual(result['state'],'needs_attention')
        self.assertIn('model mismatch',result['error'])
        self.assertEqual(self.hub.profile('opus')['availability'],'unverified')

    def test_unreported_response_model_is_unverified_even_when_the_turn_completes(self):
        job_id=self.add('claude',agent='opus',phase='plan')
        result=self.fake_run(self.hub.claim(job_id),[{'type':'system','subtype':'init','model':'claude-opus-5-5'},{'type':'result','result':'one actual report'}])
        self.assertEqual(result['state'],'completed')
        self.assertEqual(self.hub.profile('opus')['availability'],'unverified')

    def test_opus_quota_hands_lead_to_sol_but_safety_refusal_never_does(self):
        self.hub.config['limits']={'provider_gap_seconds':0}
        job_id=self.add('claude',agent='opus',phase='plan')
        job=self.hub.claim(job_id)
        result=self.fake_run(job,[{'type':'rate_limit_event','rate_limit_info':{'status':'rejected','resetsAt':time.time()+3600}}])
        self.assertEqual(result['state'],'lead_handoff')
        self.hub.hold('claude',0,'fixture release')
        self.hub.observe_quota('claude',{'status':'known','remaining_percent':80,'reset_at':time.time()+3600,'observed_at':time.time(),'source':'fixture'})
        self.prompt.write_text('distinct refusal fixture')
        refused=self.add('claude',agent='opus',phase='judge')
        result=self.fake_run(self.hub.claim(refused),[{'type':'refusal'},{'type':'rate_limit_event','rate_limit_info':{'status':'rejected','resetsAt':time.time()+3600}}])
        self.assertEqual(result['state'],'needs_attention')

    def test_stale_quota_and_failed_refresh_do_not_erase_recovery_reserve(self):
        now=time.time()
        self.hub.observe_quota('codex',{'status':'warning','remaining_percent':6,'reset_at':now+3600,'observed_at':now-600,'source':'fixture'})
        self.hub.observe_quota('codex',{'status':'unknown','remaining_percent':None,'reset_at':None,'observed_at':now,'source':'probe unavailable'})
        self.add()
        self.assertIsNone(self.hub.claim())
        self.assertEqual(self.hub.snapshot()['jobs'][0]['state'],'waiting_budget')
        with self.hub.db() as db:
            value=json.loads(db.execute("SELECT quota FROM providers WHERE name='codex'").fetchone()[0])
        self.assertEqual(value['remaining_percent'],6)

    def test_usage_probe_is_account_scoped_throttled_and_preserves_windows(self):
        executable=self.root/'fixture.exe'
        executable.touch()
        self.hub.config['providers']['codex']['executable']=str(executable)
        now=time.time()
        observation={'status':'known','remaining_percent':51,'reset_at':now+3600,'observed_at':now,'source':'fixture','windows':[{'group':'codex','window':'primary','remaining_percent':51,'reset_at':now+3600}]}
        with patch('worker.probe_usage',return_value=observation) as probe:
            self.hub.refresh_usage('codex')
            self.hub.refresh_usage('codex')
            self.assertEqual(probe.call_count,1)
        with self.hub.db() as db:
            self.assertEqual(json.loads(db.execute("SELECT quota FROM providers WHERE name='codex'").fetchone()[0])['windows'],observation['windows'])

    def test_missing_codex_bundle_uses_existing_resolver_for_command_and_usage(self):
        executable=self.root/'new-codex.exe'
        executable.touch()
        self.hub.config['providers']['codex']['executable']=str(self.root/'OpenAI/Codex/bin/old/codex.exe')
        with patch.dict('os.environ',{'LOCALAPPDATA':str(self.root)}),patch('worker.ROOT',self.root),patch('console.find_codex_windows_executable',return_value=executable),patch('worker.probe_usage',return_value=None) as probe:
            self.hub.refresh_usage('codex')
            command,_=self.hub.command({'provider':'codex','mode':'read-only','cwd':str(self.root)},'fixture')
            self.assertEqual(command[0],str(executable))
            probe.assert_called_once_with('codex',str(executable))

    def seed_actor(self,agent,phase,report,actor=None,mode='read-only'):
        provider=self.hub.profile(agent)['provider']
        self.prompt.write_text('fixture '+agent+' '+phase+' '+report)
        job_id=self.add(provider,agent=agent,phase=phase,task_id='ESC-1',actor_job=actor,mode=mode)
        result=self.root/(job_id+'.md')
        result.write_text(report)
        with self.hub.db() as db:
            db.execute("UPDATE jobs SET state='completed',result=? WHERE id=?",(str(result),job_id))
        return job_id

    def test_only_sol_request_can_authorize_one_opus_intervention(self):
        wrong=self.seed_actor('sonnet','request_opus','REQUEST_OPUS: YES')
        with self.assertRaisesRegex(ValueError,'Unauthorized'):
            self.add('claude',agent='opus',phase='intervene',task_id='ESC-1',actor_job=wrong,mode='workspace-write')
        right=self.seed_actor('sol','request_opus','REQUEST_OPUS: YES')
        self.seed_actor('opus','intervene','WORK_STATUS: DONE',actor=right,mode='workspace-write')
        self.prompt.write_text('second intervention')
        with self.assertRaisesRegex(ValueError,'one-call ceiling'):
            self.add('claude',agent='opus',phase='intervene',task_id='ESC-1',actor_job=right,mode='workspace-write')

    def test_high_end_requires_opus_two_failed_reviews_and_single_read_only_call(self):
        request=self.seed_actor('sol','request_opus','REQUEST_OPUS: YES')
        self.seed_actor('opus','intervene','WORK_STATUS: DONE',actor=request,mode='workspace-write')
        judge=self.seed_actor('opus','judge','VERDICT: BLOCK\nCONSULT: astra')
        with self.assertRaisesRegex(ValueError,'repeated failures'):
            self.add('codex',agent='astra',phase='consult',task_id='ESC-1',actor_job=judge)
        self.seed_actor('gemini','review','VERDICT: FIX')
        self.seed_actor('sonnet','review','VERDICT: BLOCK')
        self.prompt.write_text('single brief consultation')
        consult=self.add('codex',agent='astra',phase='consult',task_id='ESC-1',actor_job=judge)
        self.assertEqual(self.hub.claim(consult)['mode'],'read-only')
        with self.hub.db() as db:
            db.execute("UPDATE jobs SET state='waiting_service',attempts=1,next_at=0 WHERE id=?",(consult,))
        self.assertIsNone(self.hub.claim(consult))
        self.prompt.write_text('second consultation')
        with self.assertRaisesRegex(ValueError,'one-call ceiling'):
            self.add('codex',agent='astra',phase='consult',task_id='ESC-1',actor_job=judge)


if __name__ == "__main__":
    unittest.main(verbosity=2)
