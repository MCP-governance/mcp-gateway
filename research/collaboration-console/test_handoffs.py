import json
from pathlib import Path
import tempfile
import time
import threading
import subprocess
import sys
import unittest

from console import EventLog
from handoffs import tick, MAX_REPLIES
from worker import Hub


class Checks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'config.json').write_text(json.dumps({'providers':{p:{'executable':'missing','model':'fixture','effort':'high'} for p in ('codex','claude','antigravity')}}))
        self.hub=Hub(self.root)
        self.log=EventLog(self.hub.runtime/'events.jsonl')
        tick(self.hub,self.log)

    def ask(self, task='CHECK'):
        self.log.append('Codex','message',task,'waiting','Verify the assigned result and clarify remaining work.',recipient='Claude')
        return self.log.snapshot()['events'][-1]['id']

    def rows(self):
        with self.hub.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM handoffs ORDER BY round,created')]

    def complete(self, row, response):
        path=self.hub.runtime/'results'/('fixture-'+row['job']+'.md')
        path.parent.mkdir(exist_ok=True)
        path.write_text(response)
        with self.hub.db() as db:
            db.execute("UPDATE jobs SET state='completed',result=?,updated=? WHERE id=?",(str(path),time.time(),row['job']))

    def test_bootstrap_does_not_replay_history(self):
        self.ask()
        with self.hub.db() as db: db.execute("DELETE FROM meta WHERE key='handoff_cursor'")
        tick(self.hub,self.log)
        self.assertFalse(self.rows())

    def test_request_survives_restart_once_and_next_request_still_works(self):
        source=self.ask()
        tick(self.hub,self.log)
        tick(Hub(self.root),self.log)
        self.assertEqual(len(self.rows()),1)
        self.assertEqual(self.rows()[0]['source'],source)
        self.complete(self.rows()[0],'HANDOFF_STATUS: DONE')
        tick(self.hub,self.log)
        self.ask('SECOND-REAL-EVENT')
        tick(self.hub,self.log)
        self.assertEqual(len(self.rows()),2)
        self.assertEqual(self.rows()[0]['state'],'done')

    def test_real_followup_question_routes_to_next_agent_without_looping(self):
        self.ask()
        tick(self.hub,self.log)
        self.complete(self.rows()[0],'HANDOFF_STATUS: NEEDS_REPLY\nTO: Codex\nQUESTION: Which checks remain unexecuted?')
        tick(self.hub,self.log)
        tick(Hub(self.root),self.log)
        rows=self.rows()
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[1]['root'],rows[0]['root'])
        self.assertEqual(rows[1]['round'],2)
        with self.hub.db() as db:
            self.assertEqual(db.execute('SELECT provider FROM jobs WHERE id=?',(rows[1]['job'],)).fetchone()[0],'codex')
        self.complete(rows[1],'HANDOFF_STATUS: DONE')
        tick(self.hub,self.log)
        self.assertEqual(len(self.rows()),3)
        self.assertEqual(self.rows()[2]['purpose'],'conclusion')
        self.complete(self.rows()[2],'HANDOFF_STATUS: DONE')
        tick(self.hub,self.log)
        self.assertEqual([r['state'] for r in self.rows()],['forwarded','forwarded','done'])
        self.assertEqual(len(self.hub.snapshot()['jobs']),3)

    def test_interleaved_writer_cannot_replace_the_forwarded_request(self):
        self.ask()
        tick(self.hub,self.log)
        first=self.rows()[0]
        self.complete(first,'HANDOFF_STATUS: NEEDS_REPLY\nTO: Codex\nQUESTION: Check the same scope.')
        append=self.log.append
        def interleaved(*args,**kwargs):
            result=append(*args,**kwargs)
            if kwargs.get('source_id','').startswith('handoff-clarification-'):
                append('System','message','UNRELATED','completed','Concurrent writer',recipient='All')
            return result
        self.log.append=interleaved
        tick(self.hub,self.log)
        rows=self.rows()
        self.assertEqual(len(rows),2)
        event=next(e for e in self.log.snapshot()['events'] if e['id']==rows[1]['source'])
        self.assertEqual(event['source_id'],'handoff-clarification-'+first['request'])
        self.assertEqual(event['to'],'Codex')

    def test_quota_wait_does_not_create_repeated_calls(self):
        self.log.append('Claude','message','CHECK','waiting','Verify the result.',recipient='Codex')
        tick(self.hub,self.log)
        job=self.rows()[0]['job']
        self.hub.observe_quota('codex',{'status':'known','remaining_percent':0,'reset_at':time.time()+3600,'observed_at':time.time(),'source':'test'})
        self.assertIsNone(self.hub.claim(job))
        tick(self.hub,self.log)
        before=self.log.snapshot()['cursor']
        tick(self.hub,self.log)
        self.assertEqual(self.log.snapshot()['cursor'],before)
        self.assertEqual(len(self.rows()),1)
        self.assertEqual(self.rows()[0]['state'],'waiting_budget')
        self.hub.observe_quota('codex',{'status':'known','remaining_percent':50,'observed_at':time.time()+1,'source':'test'})
        self.assertIsNotNone(self.hub.claim(job))

    def test_agy_model_groups_admit_only_the_usable_bucket(self):
        self.hub.config['providers']['antigravity']['model']='claude-sonnet-4-6'
        now=time.time()
        def observation(group,left):
            return {'status':'known' if left else 'exhausted','remaining_percent':left,'observed_at':now,'reset_at':now+3600,'source':'fixture','windows':[{'group':group,'window':'Weekly Limit Remaining','remaining_percent':left,'reset_at':now+3600}]}
        self.hub.observe_quota('antigravity',observation('Claude and GPT models',0))
        self.hub.observe_quota('antigravity',observation('Gemini Models',1))
        prompt=self.root/'small.md';prompt.write_text('small read-only task')
        frozen=json.loads(json.dumps(self.hub.policy));frozen['reserve_percent']=0
        self.assertTrue(self.hub.agent_available('gemini',frozen))
        usable=self.hub.add('antigravity','small',self.root,prompt,agent='gemini',policy_snapshot=frozen)
        blocked=self.hub.add('antigravity','default',self.root,prompt,task_id='DEFAULT')
        self.assertIsNotNone(self.hub.claim(usable,nested=True))
        with self.hub.db() as db:
            db.execute("UPDATE jobs SET state='completed' WHERE id=?",(usable,))
        self.assertIsNone(self.hub.claim(blocked,nested=True))
        with self.hub.db() as db:
            self.assertEqual(db.execute('SELECT state FROM jobs WHERE id=?',(blocked,)).fetchone()[0],'waiting_budget')

    def test_round_budget_stops_ping_pong(self):
        self.ask()
        tick(self.hub,self.log)
        for number in range(MAX_REPLIES):
            row=self.rows()[-1]
            self.complete(row,'HANDOFF_STATUS: NEEDS_REPLY\nTO: Codex\nQUESTION: Please clarify the same question.')
            tick(self.hub,self.log)
        self.assertEqual(len(self.rows()),MAX_REPLIES)
        self.assertEqual(self.rows()[-1]['state'],'blocked')

    def test_large_log_gap_is_consumed_from_oldest_without_losing_requests(self):
        self.ask('EARLY')
        for _ in range(1001):
            self.log.append('System','message','NOISE','completed','state',recipient='All')
        self.ask('LATE')
        tick(self.hub,self.log)
        tick(self.hub,self.log)
        self.assertEqual({r['task'] for r in self.rows()},{'EARLY','LATE'})

    def test_completed_standalone_work_is_automatically_reviewed(self):
        prompt=self.root/'source.md'
        prompt.write_text('Approved original scope')
        job=self.hub.add('codex','real work',self.root,prompt,task_id='WORK')
        result=self.hub.runtime/'results'/'work.md'
        result.parent.mkdir(exist_ok=True)
        result.write_text('Actual work report')
        with self.hub.db() as db:
            db.execute("UPDATE jobs SET state='completed',result=?,updated=? WHERE id=?",(str(result),time.time(),job))
            self.hub.event(db,job,'completed',str(result))
            event=db.execute('SELECT MAX(id) FROM events').fetchone()[0]
        self.log.append('Codex','message','WORK','completed','Actual work report',recipient='Claude',source_id=f'worker-event-{event}.result')
        tick(self.hub,self.log)
        self.assertEqual(len(self.rows()),1)
        with self.hub.db() as db:
            reply=db.execute('SELECT mode,phase,prompt FROM jobs WHERE id=?',(self.rows()[0]['job'],)).fetchone()
        self.assertEqual((reply['mode'],reply['phase']),('read-only','communication'))
        self.assertIn(str(result),Path(reply['prompt']).read_text(encoding='utf-8'))

    def test_available_gemini_peer_review_returns_to_opus_for_final_judgment(self):
        self.hub.config.setdefault('agent_policy',{})['agy_use_remaining']=True
        now=time.time()
        self.hub.observe_quota('antigravity',{'status':'known','remaining_percent':1,'observed_at':now,'reset_at':now+3600,'source':'fixture','windows':[{'group':'Gemini Models','window':'Weekly Limit Remaining','remaining_percent':1,'reset_at':now+3600}]})
        self.test_completed_standalone_work_is_automatically_reviewed()
        first=self.rows()[0]
        self.assertEqual(first['purpose'],'peer_review')
        with self.hub.db() as db:
            job=db.execute('SELECT agent,policy FROM jobs WHERE id=?',(first['job'],)).fetchone()
        self.assertEqual(job['agent'],'gemini')
        self.assertEqual(json.loads(job['policy'])['reserve_percent'],0)
        self.complete(first,'HANDOFF_STATUS: DONE')
        tick(self.hub,self.log)
        final=self.rows()[1]
        self.assertEqual(final['purpose'],'lead_decision')
        with self.hub.db() as db:
            self.assertEqual(db.execute('SELECT agent FROM jobs WHERE id=?',(final['job'],)).fetchone()[0],'opus')
        self.complete(final,'HANDOFF_STATUS: DONE')
        tick(self.hub,self.log)
        self.assertEqual(self.rows()[1]['state'],'done')

    def test_missing_contract_and_failed_cli_are_visible_blockers(self):
        self.ask('MALFORMED')
        tick(self.hub,self.log)
        self.complete(self.rows()[0],'No structured outcome')
        tick(self.hub,self.log)
        self.assertEqual(self.rows()[0]['state'],'blocked')
        self.ask('FAILED')
        tick(self.hub,self.log)
        with self.hub.db() as db:
            db.execute("UPDATE jobs SET state='needs_attention',error='process failed' WHERE id=?",(self.rows()[-1]['job'],))
        tick(self.hub,self.log)
        self.assertEqual(self.rows()[-1]['state'],'blocked')

    def test_delayed_request_notifies_once_without_resubmission(self):
        self.ask()
        tick(self.hub,self.log)
        with self.hub.db() as db: db.execute('UPDATE handoffs SET created=?',(time.time()-301,))
        tick(self.hub,self.log)
        before=self.log.snapshot()['cursor']
        tick(self.hub,self.log)
        self.assertEqual(self.log.snapshot()['cursor'],before)
        self.assertEqual(self.rows()[0]['state'],'delayed')

    def test_missing_result_blocks_only_that_request(self):
        self.ask('MISSING')
        self.ask('HEALTHY')
        tick(self.hub,self.log)
        first,second=self.rows()
        with self.hub.db() as db:
            db.execute("UPDATE jobs SET state='completed',result=? WHERE id=?",(str(self.root/'missing.md'),first['job']))
        self.complete(second,'HANDOFF_STATUS: DONE')
        tick(self.hub,self.log)
        self.assertEqual([r['state'] for r in self.rows()],['blocked','done'])

    def test_disabled_recipient_does_not_poison_following_request(self):
        self.hub.policy['profiles']['gemini']['enabled']=False
        self.log.append('Codex','message','UNAVAILABLE','waiting','question',recipient='Gemini')
        self.ask('AVAILABLE')
        tick(self.hub,self.log)
        self.assertEqual([r['task'] for r in self.rows()],['AVAILABLE'])
        self.assertTrue(any(e.get('source_id','').startswith('handoff-rejected-') for e in self.log.snapshot()['events']))

    def test_reload_drains_existing_jobs_before_new_admission(self):
        self.ask()
        tick(self.hub,self.log)
        with self.hub.db() as db:db.execute("INSERT INTO meta VALUES('reload_worker_pending','1')")
        self.assertIsNone(self.hub.claim(self.rows()[0]['job']))

    def test_new_opus_quota_block_hands_unclaimed_reply_to_sol_once(self):
        self.ask('DEPUTY')
        tick(self.hub,self.log)
        original=self.rows()[0]
        self.hub.observe_quota('claude',{'status':'exhausted','remaining_percent':0,'reset_at':time.time()+3600,'observed_at':time.time(),'source':'fixture'})
        self.assertIsNone(self.hub.claim(original['job']))
        tick(self.hub,self.log)
        tick(Hub(self.root),self.log)
        rows=self.rows()
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['state'],'forwarded')
        self.assertEqual(rows[1]['purpose'],'lead_decision')
        with self.hub.db() as db:
            self.assertEqual(db.execute('SELECT state FROM jobs WHERE id=?',(original['job'],)).fetchone()[0],'closed')
            self.assertEqual(db.execute('SELECT agent FROM jobs WHERE id=?',(rows[1]['job'],)).fetchone()[0],'sol')
        self.complete(rows[1],'HANDOFF_STATUS: DONE')
        tick(self.hub,self.log)
        self.assertEqual(self.rows()[1]['state'],'done')

    def test_two_processes_and_later_restart_deliver_each_request_once(self):
        self.ask('PROCESS-ONE')
        script="import sys,time; from pathlib import Path; from worker import Hub; import handoffs; original=handoffs.request; handoffs.request=lambda *a,**k: (time.sleep(0.5),original(*a,**k))[1]; handoffs.tick(Hub(Path(sys.argv[1])))"
        args=[sys.executable,'-c',script,str(self.root)]
        processes=[subprocess.Popen(args,cwd=Path(__file__).resolve().parent,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
        for process in processes:
            out,err=process.communicate(timeout=20)
            self.assertEqual(process.returncode,0,err.decode())
        self.assertEqual(len(self.rows()),1)
        self.ask('PROCESS-TWO')
        result=subprocess.run(args,cwd=Path(__file__).resolve().parent,capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        self.assertEqual(len(self.rows()),2)

    def test_busy_coding_provider_does_not_block_another_providers_reply(self):
        prompt=self.root/'coding.md'
        prompt.write_text('coding task')
        self.hub.add('codex','coding',self.root,prompt)
        self.ask()
        tick(self.hub,self.log)
        release=threading.Event()
        started={provider:threading.Event() for provider in ('codex','claude')}
        def run(job):
            started[job['provider']].set()
            release.wait(5)
        self.hub.run=run
        threads=self.hub.launch_ready([])
        try:
            self.assertTrue(started['codex'].wait(2))
            self.assertTrue(started['claude'].wait(2))
            self.assertEqual(len(self.hub.launch_ready(threads)),2)
        finally:
            release.set()
            for thread in threads:thread.join(2)


if __name__=='__main__': unittest.main()
