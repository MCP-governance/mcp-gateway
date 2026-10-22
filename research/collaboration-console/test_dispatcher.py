import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import dispatcher as d
from console import EventLog
from worker import Hub


class Checks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.standing = self.root / 'standing'
        self.standing.mkdir()
        self.cwd = self.root / 'mcp-gw-test'
        self.cwd.mkdir()
        (self.root / 'config.json').write_text(json.dumps({'providers':{p:{'executable':'missing','model':'test','effort':'high'} for p in d.PROVIDERS + ('claude',)}}))
        self.hub = Hub(self.root)
        self.emit = self.enterContext(patch.object(d, 'emit'))
        for name, value in {'ROOT':self.root,'STANDING':self.standing,'STATE':self.standing/'.state.json','HUB_ROOT':self.root}.items():
            self.enterContext(patch.object(d, name, value))
        self.body = f'cwd: {self.cwd}\nmode: read-only\ntask: CHECK\n---\nInspect assigned files.'

    def queue(self, provider='codex'):
        target = self.standing / provider
        target.mkdir(exist_ok=True)
        path = target / 'check.md'
        path.write_text(self.body)
        return path

    def test_failed_submit_preserves_instruction(self):
        path = self.queue()
        with patch.object(self.hub, 'add', side_effect=ValueError('denied')):
            with self.assertRaises(ValueError):
                d.dispatch(self.hub, {})
        self.assertTrue(path.exists())
        self.assertFalse((self.standing/'done').exists())

    def test_submit_is_deduplicated_and_archived_only_after_success(self):
        self.queue()
        d.dispatch(self.hub, {})
        self.assertTrue((self.standing/'done/codex-check.md').exists())
        self.queue()
        d.dispatch(self.hub, {})
        self.assertEqual(len(self.hub.snapshot()['jobs']), 1)

    def test_quota_rest_report_once_and_resume(self):
        self.queue()
        state = {}
        self.hub.observe_quota('codex', {'status':'known','remaining_percent':9,'observed_at':time.time(),'reset_at':time.time()+3600,'source':'test'})
        d.dispatch(self.hub, state)
        d.dispatch(self.hub, state)
        self.assertEqual(self.emit.call_count, 1)
        self.assertFalse(self.hub.snapshot()['jobs'])
        self.hub.observe_quota('codex', {'status':'known','remaining_percent':60,'observed_at':time.time()+1,'source':'test'})
        d.dispatch(self.hub, state)
        self.assertEqual(len(self.hub.snapshot()['jobs']), 1)
        self.assertIn('사용량 회복', self.emit.call_args_list[1].args[1])

    def test_planner_failure_is_not_harvested(self):
        state = {'planner_job_codex':'failed'}
        d.harvest(state, [{'id':'failed','state':'needs_attention','result':'partial.md'}])
        self.assertIn('planner_job_codex', state)
        self.emit.assert_not_called()

    def test_task_cannot_escape_scope(self):
        with self.assertRaises(ValueError):
            d.parse_text('cwd: C:/\nmode: danger-full-access\n---\nDo anything')

    def test_dispatch_freezes_requested_model_before_config_changes(self):
        self.queue()
        d.dispatch(self.hub, {})
        self.hub.config['providers']['codex']['model'] = 'changed-later'
        self.assertEqual(self.hub.snapshot()['jobs'][0]['model'], 'test')

    def test_restart_waits_for_running_cli(self):
        path = self.root / 'prompt.md'
        path.write_text('inspect')
        self.hub.add('codex','test',self.cwd,path)
        self.hub.claim()
        with self.hub.db() as db:
            db.execute("INSERT INTO meta VALUES('reload_worker_pending','1')")
        with patch.object(d.subprocess,'run') as run:
            d.restart_when_idle(self.hub)
        run.assert_not_called()

    def test_paused_job_is_preserved_without_disabling_other_work(self):
        path = self.root / 'paused.md'
        path.write_text('preserve paused work')
        job_id = self.hub.add('codex','paused',self.cwd,path)
        with self.hub.db() as db:
            db.execute("UPDATE jobs SET state='paused' WHERE id=?",(job_id,))
        self.queue()
        d.dispatch(self.hub, {})
        states = {j['id']:j['state'] for j in self.hub.snapshot()['jobs']}
        self.assertEqual(states[job_id], 'paused')
        self.assertEqual(len(states), 2)

    def test_idle_restart_consumes_request(self):
        with self.hub.db() as db:
            db.execute("INSERT INTO meta VALUES('reload_worker_pending','1')")
        with patch.object(d.subprocess,'run') as run:
            run.return_value.returncode = 0
            d.restart_when_idle(self.hub)
        run.assert_called_once()
        with self.hub.db() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM meta WHERE key='reload_worker_pending'").fetchone())

    def test_only_explicit_unstarted_paused_job_resumes_after_reload(self):
        path = self.root / 'resume.md'
        path.write_text('authorized resume')
        job_id = self.hub.add('antigravity','resume',self.cwd,path)
        with self.hub.db() as db:
            db.execute("UPDATE jobs SET state='paused' WHERE id=?",(job_id,))
            db.execute("INSERT INTO meta VALUES('reload_worker_pending','1')")
            db.execute("INSERT INTO meta VALUES('resume_after_reload',?)",(json.dumps([job_id]),))
        self.hub.config['providers']['antigravity']['model']='requested-model'
        with patch.object(d.subprocess,'run') as run:
            run.return_value.returncode=0
            d.restart_when_idle(self.hub)
        row=self.hub.snapshot()['jobs'][0]
        self.assertEqual((row['state'],row['model']),('queued','requested-model'))

    def test_all_jobs_receive_latest_inbox_and_effective_timeout(self):
        path = self.root / 'prompt.md'
        path.write_text('inspect')
        job_id = self.hub.add('codex','test',self.cwd,path,task_id='CHECK')
        job = self.hub.snapshot()['jobs'][0]
        log = EventLog(self.root/'messages.jsonl')
        log.append('Claude','message','CHECK','completed','timeout updated',recipient='Codex')
        relevant = log.snapshot()['events'][-1]
        log.append('Claude','message','UNRELATED','completed','ignore this',recipient='Codex')
        self.hub.config['timeout_seconds'] = 3600
        context = self.hub.handoff_context(job, log)
        self.assertIn('"timeout_seconds": 3600', context)
        self.assertIn('timeout updated', context)
        self.assertNotIn('ignore this', context)
        self.assertIn('CHECKED:', context)
        with self.hub.db() as db:
            receipt = json.loads(db.execute('SELECT value FROM meta WHERE key=?',('handoff:'+job_id,)).fetchone()[0])
        self.assertEqual(receipt['message_ids'], [relevant['id']])


if __name__ == '__main__':
    unittest.main()
