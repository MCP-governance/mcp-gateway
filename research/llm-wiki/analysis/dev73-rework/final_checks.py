"""Check this lane's text/artifacts and record the permitted Git commit attempt."""
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
OUTPUT=HERE/'final-checks.json'
OUTPUT.write_text('{}\n',encoding='utf-8',newline='\n')


def call(args):
    run=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
    return {'command':args,'at':datetime.now(timezone.utc).isoformat(),'returncode':run.returncode,
            'stdout':run.stdout,'stderr':run.stderr}


tracked=call(['git','diff','--name-only'])['stdout'].splitlines()
new=call(['git','ls-files','--others','--exclude-standard'])['stdout'].splitlines()
paths=sorted(set(tracked+new))
bad=[]
for relative in paths:
    path=ROOT/relative
    raw=path.read_bytes()
    try:raw.decode('utf-8')
    except UnicodeDecodeError:bad.append({'path':relative,'problem':'not UTF-8'});continue
    if raw.startswith(b'\xef\xbb\xbf'):bad.append({'path':relative,'problem':'BOM'})
    if b'\r\n' in raw:bad.append({'path':relative,'problem':'CRLF'})

links=[]
for path in [HERE/'README.md',ROOT/'research/llm-wiki/status/reports/2026-10-21-dev73-rework.md']:
    for target in re.findall(r'\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
        if target.startswith(('http:','https:','#')):continue
        target=target.split('#')[0]
        if not (path.parent/target).exists():links.append({'path':str(path.relative_to(ROOT)),'target':target})
inherited=[]
for relative in ('full_stack_lab/tests/local_run_manifest_check.py','full_stack_lab/tests/local_jobs_pg_check.py'):
    original=subprocess.check_output(['git','show','217da74:'+relative],cwd=ROOT)
    inherited.append({'path':relative,'unchanged_from_217da74':original==(ROOT/relative).read_bytes()})
source=[]
for requirement in json.loads((HERE/'requirements.json').read_text(encoding='utf-8'))['requirements']:
    for entry in requirement['source']:
        if hashlib.sha256((ROOT/entry['path']).read_bytes()).hexdigest()!=entry['sha256']:source.append(entry['path'])
results={'at':datetime.now(timezone.utc).isoformat(),'files':paths,'text_errors':bad,'missing_own_links':links,
         'source_hash_mismatches':source,'inherited_tests':inherited,
         'existing_tests_diff':call(['git','diff','--name-only','--','full_stack_lab/tests']),
         'current_status_diff':call(['git','diff','--name-only','--','research/llm-wiki/status/current.md']),
         'whitespace':call(['git','diff','--check'])}
results['git_add']=call(['git','add','--',*paths])
if results['git_add']['returncode']==0:
    results['commit']=call(['git','commit','-m','fix(v2): rework DEV-73 after rejection',
                           '-m','Apply the arbitration scope, bounded execution and stop receipts while preserving the existing controls.'])
OUTPUT.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps({'text_errors':bad,'missing_links':links,'source_mismatches':source,
                  'existing_tests_unchanged':not results['existing_tests_diff']['stdout'],
                  'current_status_unchanged':not results['current_status_diff']['stdout'],
                  'git_add_returncode':results['git_add']['returncode']},ensure_ascii=False))
