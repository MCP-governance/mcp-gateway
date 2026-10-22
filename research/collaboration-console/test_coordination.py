import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from coordination import Coordinator
from worker import Hub


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


if __name__=='__main__':
    unittest.main()
