"""Reproduce local-only DEV-73 checks and retain exact commands, timestamps and raw output."""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
PY=sys.executable
changed=subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True,encoding='utf-8').splitlines()
untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True,encoding='utf-8').splitlines()
files=sorted({p for p in changed+untracked if p.endswith('.py')})
checks=[('py_compile',[PY,'-X','utf8','-m','py_compile',*files]),
        ('javascript',['node','--check','full_stack_lab/gateway/app/agent_static/console.js']),
        ('open_endpoints',[PY,'-X','utf8','full_stack_lab/tests/open_endpoints.py']),
        ('console_state',['node','--test','full_stack_lab/tests/console-state.test.mjs'])]
for name in ('dev73_rework_check','user_server_suspend_check','endpoint_offline_buffer_check','root_solo_check',
             'solo_mode_ledger_check','dispatch_recheck_check','upstream_session_reuse_test','outcome_axes_check','schema_check',
             'local_run_manifest_check','dev73_rework_pg_check'):
    checks.append((name,[PY,'-X','utf8','full_stack_lab/tests/'+name+'.py']))
checks.append(('pyflakes',[PY,'-X','utf8','-m','pyflakes',*files]))
checks.extend((name,[PY,'-X','utf8','research/llm-wiki/tools/'+name+'.py']) for name in ('build_wiki','check_wiki'))
results=[]
for name,command in checks:
    record={'name':name,'command':command,'cwd':str(ROOT),'started_at':datetime.now(timezone.utc).isoformat()}
    try:
        result=subprocess.run(command,cwd=ROOT,capture_output=True,encoding='utf-8',errors='replace',timeout=55)
        record.update(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr)
    except (OSError,subprocess.TimeoutExpired) as exc:
        record.update(returncode=None,error=type(exc).__name__,detail=str(exc))
    record['finished_at']=datetime.now(timezone.utc).isoformat()
    results.append(record)
    (HERE/'checks.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(name,record['returncode'],flush=True)
