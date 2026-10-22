import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from coordination import Coordinator
from worker import Hub
from agent_policy import policy


class GraphChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        for args in (('init','-q'),('config','user.name','Test'),('config','user.email','test@example.invalid'),('commit','--allow-empty','-qm','baseline')):
            subprocess.run(['git','-C',str(self.repo),*args],check=True,capture_output=True)
        (self.root/'config.json').write_text(json.dumps({'providers':{p:{'executable':'unused','model':'test','effort':'high'} for p in ('codex','claude','antigravity')}}))
        self.prompt=self.root/'prompt.md'
        self.prompt.write_text('One bounded task',encoding='utf-8')
        self.hub=Hub(self.root)
        self.coordinator=Coordinator(self.hub)
        self.coordinator.add('CHECK-1',self.repo,self.prompt,time.time()+3600)

    def tearDown(self):
        self.coordinator.close()
        self.temp.cleanup()

    def pending(self):
        with self.hub.db() as db:
            return dict(db.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY updated DESC LIMIT 1").fetchone())

    def complete(self,text='ACK CHECK-1; implementation evidence'):
        job=self.pending()
        if job['provider']=='codex':
            source=self.repo/'source.txt'
            source.write_text((source.read_text() if source.exists() else '')+job['id'])
            text+='\nWORK_STATUS: DONE'
        result=self.root/(job['id']+'.md')
        result.write_text(text,encoding='utf-8')
        with self.hub.db() as db:
            db.execute("UPDATE jobs SET state='completed',result=?,updated=? WHERE id=?",(str(result),time.time(),job['id']))
        self.coordinator.tick()

    def status(self):
        with self.hub.db() as db:
            return dict(db.execute("SELECT * FROM workflows WHERE id='CHECK-1'").fetchone())

    def test_checkpoint_restart_does_not_repeat_implementation(self):
        self.coordinator.tick()
        first=self.pending()['id']
        self.coordinator.close()
        self.coordinator=Coordinator(self.hub)
        self.coordinator.tick()
        self.assertEqual(self.pending()['id'],first)
        self.complete()
        self.assertEqual(self.pending()['provider'],'antigravity')
        self.complete('VERDICT: PASS\nEvidence reviewed, runtime checks remain unverified.')
        self.assertEqual(self.status()['state'],'ready')
        with self.hub.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],2)

    def test_fix_loop_stops_after_second_review_and_one_arbitration(self):
        self.coordinator.tick()
        self.complete()
        self.complete('VERDICT: FIX\nSpecific finding')
        self.assertEqual(self.pending()['provider'],'codex')
        self.complete('ACK CHECK-1; corrected finding')
        self.complete('VERDICT: FIX\nUnresolved finding')
        self.assertEqual(self.pending()['provider'],'claude')
        self.complete('VERDICT: BLOCK\nNeeds a human decision')
        self.assertEqual(self.status()['state'],'needs_attention')
        self.coordinator.tick()
        with self.hub.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],5)

    def test_quota_wait_is_checkpointed_without_polling_the_model(self):
        self.coordinator.tick()
        job=self.pending()
        with self.hub.db() as db:
            db.execute("UPDATE jobs SET state='waiting_quota',next_at=? WHERE id=?",(time.time()+18000,job['id']))
        for _ in range(4):
            self.coordinator.tick()
        self.assertEqual(self.status()['state'],'waiting')
        with self.hub.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],1)

    def test_changed_source_invalidates_review_without_repeated_requests(self):
        self.coordinator.tick()
        self.complete()
        (self.repo/'new.txt').write_text('source changed during review')
        self.complete('VERDICT: PASS')
        self.assertEqual(self.status()['state'],'needs_attention')
        self.assertIn('판본',self.status()['summary'])

    def test_ambiguous_verdict_does_not_trigger_more_model_calls(self):
        self.coordinator.tick()
        self.complete()
        self.complete('VERDICT: PASS\nVERDICT: FIX')
        self.assertEqual(self.status()['state'],'needs_attention')

    def test_blocked_implementation_does_not_spend_a_review_call(self):
        self.coordinator.tick()
        job=self.pending()
        result=self.root/'blocked.md'
        result.write_text('Cannot run tools\nWORK_STATUS: BLOCKED')
        with self.hub.db() as db:
            db.execute("UPDATE jobs SET state='completed',result=? WHERE id=?",(str(result),job['id']))
        self.coordinator.tick()
        self.assertEqual(self.status()['state'],'needs_attention')
        with self.hub.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],1)

    def test_paused_or_failed_graph_cannot_launch_its_queued_job(self):
        self.coordinator.tick()
        with self.hub.db() as db:
            db.execute("UPDATE workflows SET state='needs_attention' WHERE id='CHECK-1'")
        self.assertIsNone(self.hub.claim())
        with self.hub.db() as db:
            db.execute("UPDATE workflows SET state='active' WHERE id='CHECK-1'")
        self.assertEqual(self.hub.claim()['task_id'],'CHECK-1')

    def test_review_gets_actual_bounded_handoff_without_file_read_permission(self):
        self.coordinator.tick()
        self.complete()
        job=self.pending()
        prompt=Path(job['prompt']).read_text(encoding='utf-8')
        self.assertIn('implementation evidence',prompt)
        self.assertIn("untrusted='true'",prompt)
        self.assertLess(len(prompt),24000)


class HierarchyChecks(unittest.TestCase):
    tearDown=GraphChecks.tearDown
    pending=GraphChecks.pending
    status=GraphChecks.status

    PLAN="\n".join(("GOAL: Complete the authorized bounded source fix", "FILES: source.txt", "INVARIANTS: Preserve authorization and existing changes", "STEPS: Inspect, edit, verify targeted behavior", "CHECKS: Run the targeted source check", "ROLLBACK: Revert only this task's source change", "STOP: Refusal, scope change or ambiguous evidence", "WORKER: sol", "PLAN_STATUS: READY"))

    def setUp(self):
        GraphChecks.setUp(self)
        with self.hub.db() as db:
            db.execute("DELETE FROM workflows")
        self.hub.policy=policy({"agent_policy":{"enabled":True}})
        self.coordinator.add('CHECK-1',self.repo,self.prompt,time.time()+3600)

    def complete(self,text,change=False):
        job=self.pending()
        if change:
            source=self.repo/'source.txt'
            source.write_text((source.read_text() if source.exists() else '')+job['id'])
        result=self.root/(job['id']+'.md')
        result.write_text(text,encoding='utf-8')
        with self.hub.db() as db:
            db.execute("UPDATE jobs SET state='completed',result=?,updated=? WHERE id=?",(str(result),time.time(),job['id']))
        self.coordinator.tick()
        return job

    def test_normal_path_uses_opus_plan_and_judgment_with_main_coder(self):
        self.coordinator.tick()
        self.assertEqual((self.pending()['agent'],self.pending()['phase']),('opus','plan'))
        self.complete(self.PLAN)
        self.assertEqual((self.pending()['agent'],self.pending()['mode']),('sol','workspace-write'))
        self.complete('WORK_STATUS: DONE',change=True)
        self.assertEqual(self.pending()['agent'],'gemini')
        self.complete('VERDICT: PASS')
        self.assertEqual((self.pending()['agent'],self.pending()['phase']),('opus','judge'))
        self.complete('VERDICT: PASS')
        self.assertEqual(self.status()['state'],'ready')
        with self.hub.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],4)

    def test_policy_and_pending_job_are_frozen_across_restart(self):
        self.coordinator.tick()
        first=self.pending()['id']
        original=self.hub.policy['profiles']['sol']['model']
        self.hub.policy['profiles']['sol']['model']='new-model-for-future-work'
        self.hub.policy['max_calls']=1
        self.coordinator.close()
        self.coordinator=Coordinator(self.hub)
        self.coordinator.tick()
        self.assertEqual(self.pending()['id'],first)
        self.complete(self.PLAN)
        self.assertEqual(self.pending()['model'],original)
        self.assertEqual(json.loads(self.pending()['policy'])['max_calls'],18)

    def test_held_opus_plan_hands_off_to_sol_without_attempting_opus(self):
        self.coordinator.tick()
        first=self.pending()['id']
        self.hub.hold('claude',time.time()+3600,'quota')
        self.assertIsNone(self.hub.claim(first))
        self.coordinator.tick()
        self.assertEqual((self.pending()['agent'],self.pending()['phase']),('sol','plan'))
        with self.hub.db() as db:
            self.assertEqual(db.execute('SELECT attempts FROM jobs WHERE id=?',(first,)).fetchone()[0],0)
        self.complete(self.PLAN)
        self.complete('WORK_STATUS: DONE',change=True)
        self.complete('VERDICT: PASS')
        self.assertEqual(self.pending()['agent'],'sol')
        self.complete('VERDICT: PASS')
        self.assertEqual(self.status()['state'],'ready')

    def test_safety_refusal_stops_before_any_model_switch(self):
        self.coordinator.tick()
        self.complete('REFUSAL: SAFETY\nPLAN_STATUS: BLOCKED')
        self.assertEqual(self.status()['state'],'needs_attention')
        self.coordinator.tick()
        with self.hub.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],1)

    def test_auxiliary_is_read_only_once_and_returns_to_main_worker(self):
        self.coordinator.tick()
        self.complete(self.PLAN)
        self.complete('WORK_STATUS: BLOCKED\nAUX_REQUEST: luna\nNarrow dependency question')
        self.assertEqual((self.pending()['agent'],self.pending()['mode']),('luna','read-only'))
        self.complete('One narrow answer and evidence path')
        self.assertEqual(self.pending()['agent'],'sol')
        self.complete('WORK_STATUS: DONE',change=True)
        self.complete('VERDICT: PASS')
        self.complete('VERDICT: PASS')
        self.assertEqual(self.status()['state'],'ready')

    def test_repeat_failure_requires_sol_intervention_request_then_single_opus_consult(self):
        self.coordinator.tick()
        self.complete(self.PLAN)
        self.complete('WORK_STATUS: DONE',change=True)
        for _ in range(2):
            self.complete('VERDICT: FIX\nSpecific reproducible finding')
            self.complete('VERDICT: FIX\nDetailed bounded correction')
            if _==0:
                self.complete('WORK_STATUS: DONE',change=True)
        self.assertEqual((self.pending()['agent'],self.pending()['phase']),('sol','request_opus'))
        self.complete('REQUEST_OPUS: YES\nExact blocker, attempted fixes and checks')
        self.assertEqual((self.pending()['agent'],self.pending()['phase']),('opus','intervene'))
        self.complete('WORK_STATUS: DONE',change=True)
        self.complete('VERDICT: FIX\nRemaining boundary problem')
        self.complete('VERDICT: BLOCK\nCONSULT: astra\nOne short broad question')
        consult=self.pending()
        self.assertEqual((consult['agent'],consult['mode'],consult['effort']),('astra','read-only','high'))
        self.complete('One discriminating check; no implementation')
        self.complete('VERDICT: BLOCK\nBounded automatic effort exhausted')
        self.assertEqual(self.status()['state'],'needs_attention')
        self.coordinator.tick()
        with self.hub.db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM jobs WHERE phase='intervene'").fetchone()[0],1)
            self.assertEqual(db.execute("SELECT count(*) FROM jobs WHERE phase='consult'").fetchone()[0],1)
            self.assertLessEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],16)

    def test_incomplete_plan_is_not_treated_as_detailed_instructions(self):
        self.coordinator.tick()
        self.complete('WORKER: sol\nPLAN_STATUS: READY')
        self.assertEqual(self.status()['state'],'needs_attention')

    def test_missing_or_ambiguous_work_status_never_escalates(self):
        self.coordinator.tick()
        self.complete(self.PLAN)
        self.complete('Unable to proceed\nAUX_REQUEST: luna\nREQUEST_OPUS: YES')
        self.assertEqual(self.status()['state'],'needs_attention')
        with self.hub.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],2)


if __name__=='__main__':
    unittest.main()
