from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

repo = Path(__file__).resolve().parents[3]
files = ["full_stack_lab/gateway/app/"+name+".py" for name in ("privacy", "core", "mcp_facade")]
test = "full_stack_lab/tests/mcp_result_services_check.py"
source = {path: (repo/path).read_text(encoding="utf-8") for path in [*files, test]}
program = "import ast,json,math,sys,types,unittest\nfrom app import privacy,core,mcp_facade\n"
program += "sources="+repr(source)+"\n"
program += "for name,symbols in [('privacy',{'mask_payload'}),('core',{'_guarded_result','_inspected_result','_decoded_strings'}),('mcp_facade',{'_render'})]:\n module=sys.modules['app.'+name]; module.__dict__.update(json=json,math=math); tree=ast.parse(sources['full_stack_lab/gateway/app/'+name+'.py']); tree.body=[n for n in tree.body if (isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in symbols) or (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in {'OUTPUT_INSPECTION_TIMEOUT_SECONDS','RECOGNIZERS'} for t in n.targets))]; exec(compile(tree,module.__file__,'exec'),module.__dict__)\n"
program += "module=types.ModuleType('mcpgw_result_services'); module.__file__='/app/tests/mcp_result_services_check.py'; sys.modules[module.__name__]=module\nexec(compile(sources['"+test+"'],module.__file__,'exec'),module.__dict__)\nsuite=unittest.defaultTestLoader.loadTestsFromModule(module); result=unittest.TextTestRunner().run(suite); sys.exit(not result.wasSuccessful())\n"
run = subprocess.run(["wsl.exe", "-d", "kali-linux", "--", "ssh", "-T", "-o", "ConnectTimeout=10",
                      "user@100.83.175.111", "docker exec -i mcpgw-55e075465e-gateway-1 python -"],
                     input=program, capture_output=True, text=True, encoding="utf-8", timeout=150)
document = {"checked_at": datetime.now(timezone.utc).isoformat(), "host": "100.83.175.111",
            "scope": "isolated_process_with_real_appliance_presidio_and_gitleaks",
            "services_or_deployed_code_modified": False, "actual_mcp_server_experiment": False,
            "source_files": [{"path":p,"normalized_sha256":hashlib.sha256((repo/p).read_bytes().replace(b'\r\n',b'\n')).hexdigest()} for p in source],
            "exit_code":run.returncode,"output":run.stdout+run.stderr}
(repo/"research/llm-wiki/status/reports/2026-10-13-real-inspectors-results.json").write_text(json.dumps(document,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(document,ensure_ascii=False))
raise SystemExit(run.returncode)
