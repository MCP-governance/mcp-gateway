"""Record local provenance and exact source locations without changing shared status files."""
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent


def command(args):
    result=subprocess.run(args,cwd=ROOT,capture_output=True,timeout=30)
    decode=lambda b:b.decode('utf-16-le' if b'\x00' in b else 'utf-8',errors='replace')
    return {'command':args,'at':datetime.now(timezone.utc).isoformat(),'returncode':result.returncode,
            'stdout':decode(result.stdout),'stderr':decode(result.stderr)}


environment={'captured_at':datetime.now(timezone.utc).isoformat(),'python':sys.version,
             'tools':{n:shutil.which(n) for n in ('python','python3','node','git','rg','wsl','docker','podman','openssl')},
             'packages':{n:bool(importlib.util.find_spec(n)) for n in ('mcp','psycopg','pydantic','cryptography','pyflakes','pglast')},
             'commands':[command(args) for args in (
                 ['git','rev-parse','HEAD','origin/main','origin/10/20-dev73-impl'],
                 ['git','branch','--show-current'],['git','fetch','origin','main','10/20-dev73-impl'],
                 ['git','ls-remote','--symref','origin','HEAD'],['git','checkout','-B','10/21-dev73-rework','origin/main'],
                 ['git','diff','--check'],['git','diff','--name-only','--','full_stack_lab/tests'],
                 ['wsl.exe','-d','kali-linux','--','python3','--version'])]}
(HERE/'environment.json').write_text(json.dumps(environment,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
scopes={
 'F1':[('docs/ai/SECURITY_BOUNDARIES.md','## 4.'),('research/llm-wiki/analysis/direction-1020/dev73-local-isolated-run.md','## 9.')],
 'F2':[('full_stack_lab/gateway/app/local_jobs.py','async def validate_job'),('full_stack_lab/gateway/app/local_jobs.py','async def current_job'),
       ('full_stack_lab/gateway/app/local_jobs.py','async def quiesce'),('full_stack_lab/gateway/app/local_jobs.py','async def prepare_token_revocation'),
       ('full_stack_lab/gateway/app/local_run_tables.sql','CREATE OR REPLACE FUNCTION'),('full_stack_lab/gateway/app/idp.py','async def _revoke_family')],
 'F3':[('full_stack_lab/gateway/app/local_jobs.py','def mirror_image'),('endpoint-agent/local-runner.py','def engine_configuration')],
 'F4':[('endpoint-agent/local-runner.py','class PinnedMounts')],
 'F5':[('endpoint-agent/local-runner.py','def container_command'),('endpoint-agent/local-runner.py','    def mapping')],
 'F6':[('endpoint-agent/local-runner.py','    def _read'),('endpoint-agent/local-runner.py','    def request'),('endpoint-agent/local-runner.py','    def stop')],
 'F7':[('full_stack_lab/gateway/app/local_jobs.py','async def exchange'),('full_stack_lab/gateway/app/local_jobs.py','async def cleanup'),
       ('full_stack_lab/gateway/app/local_jobs.py','async def claim'),('full_stack_lab/gateway/app/local_jobs.py','async def complete')],
 'F8':[('full_stack_lab/gateway/app/local_jobs.py','async def applicant_device'),('full_stack_lab/gateway/app/core.py','async def discover_for_registration'),
       ('full_stack_lab/gateway/app/agent_static/console.js','    const pcRun'),
       ('endpoint-agent/local-runner.py','def execute_job')],
 'F9':[('full_stack_lab/gateway/app/local_jobs.py','def remember'),('full_stack_lab/gateway/app/local_jobs.py','async def record_evidence'),
       ('full_stack_lab/gateway/app/local_run_tables.sql','CREATE TABLE IF NOT EXISTS local_job_events')],
 'F10':[('full_stack_lab/gateway/app/core.py','async def _decision_payload'),('endpoint-agent/local-runner.py','def recover')]
}
rows=[]
tests=ROOT/'full_stack_lab/tests/dev73_rework_check.py'
for finding,locations in scopes.items():
    evidence=[]
    for path,symbol in locations:
        raw=(ROOT/path).read_bytes();lines=raw.decode('utf-8').splitlines()
        at=next(i+1 for i,line in enumerate(lines) if line.startswith(symbol))
        evidence.append({'path':path,'symbol':symbol.strip(),'line':at,'sha256':hashlib.sha256(raw).hexdigest()})
    cases=[{'path':str(tests.relative_to(ROOT)).replace('\\','/'),'line':i+1,'symbol':line.strip().split('(')[0].split()[-1]}
           for i,line in enumerate(tests.read_text(encoding='utf-8').splitlines()) if ('def test_'+finding+'_') in line or ('def test_F9_F10_' in line and finding in ('F9','F10'))]
    rows.append({'requirement':finding,'disposition':'scope_documented' if finding=='F1' else 'implemented_pending_runtime',
                 'source':evidence,'unit_cases':cases,'runtime':'NOT_EXECUTED','deployment':'NOT_EXECUTED',
                 'postgresql_case':'full_stack_lab/tests/dev73_rework_pg_check.py' if finding in ('F2','F7','F9','F10') else None})
(HERE/'requirements.json').write_text(json.dumps({'base':'7151de41b228676f5ecd33dddc57cec06465cc6c',
    'revision':'uncommitted-worktree','requirements':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
print('captured environment and requirement source hashes')
