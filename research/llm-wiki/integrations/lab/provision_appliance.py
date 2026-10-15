"""Copy this reviewed lab to the authorized solution appliance; never local Compose.

Creates only /home/user/mcpgw-interop-lab-20261013. Secrets are generated there,
remain outside Git, and are never returned. Does not start or modify the product.
"""
import json
from pathlib import Path
import subprocess

TARGET = "/home/user/mcpgw-interop-lab-20261013"
MARKER = "mcpgw-interoperability-lab-20261013"


def main():
    root = Path(__file__).resolve().parent
    files = {}
    for path in root.rglob("*"):
        if path.is_file() and not any(part in {"runtime", "__pycache__", ".venv", "secrets"} for part in path.relative_to(root).parts):
            if path.suffix in {".py", ".sh", ".yaml", ".hcl", ".md", ".json"} or path.name == "Caddyfile":
                files[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8")
    program = "import json,os,secrets\nfrom pathlib import Path\n"
    program += "target=Path("+repr(TARGET)+"); marker="+repr(MARKER)+"; files="+repr(files)+"\n"
    program += '''
if target.exists() and (not (target/'.lab-owner').is_file() or (target/'.lab-owner').read_text().strip()!=marker):
    raise SystemExit('Refusing an existing directory not owned by this lab')
target.mkdir(mode=0o700, parents=False, exist_ok=True)
(target/'.lab-owner').write_text(marker+'\\n')
for name, text in files.items():
    path=(target/name).resolve()
    if not path.is_relative_to(target.resolve()): raise SystemExit('Invalid artifact path')
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(text,encoding='utf-8'); path.chmod(0o700 if path.suffix=='.sh' else 0o644 if path.suffix=='.hcl' else 0o600)
directory=target/'secrets'; directory.mkdir(mode=0o700,exist_ok=True)
for name in ('postgres_password','litellm_master_key','litellm_salt_key'):
    path=directory/name
    if not path.exists():
        value=('sk-' if name=='litellm_master_key' else '')+secrets.token_urlsafe(32)
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream: stream.write(value)
    if path.is_symlink() or path.stat().st_mode & 0o077: raise SystemExit('Unsafe secret file')
(target/'.env').write_text('INTEROP_BIND=100.83.175.111\\nINTEROP_SECRET_DIR='+str(directory)+'\\n'
                         +'OPENBAO_CONFIG_DIR='+str(target/'openbao')+'\\n'
                         +'OPENBAO_RUNTIME_DIR='+str(target/'openbao/runtime')+'\\n',encoding='utf-8')
(target/'.env').chmod(0o600)
print(json.dumps({'target':str(target),'copied_files':len(files),'secrets_generated_or_preserved':3,'secret_values_returned':False,'containers_started':False}))
'''
    run = subprocess.run(["wsl.exe", "-d", "kali-linux", "--", "ssh", "-T", "-o", "ConnectTimeout=10",
                          "user@100.83.175.111", "python3 -"],input=program,text=True,encoding="utf-8",capture_output=True)
    print(run.stdout)
    if run.returncode:
        print("Provisioning failed; no credential output is returned")
    return run.returncode


if __name__ == "__main__":
    raise SystemExit(main())
