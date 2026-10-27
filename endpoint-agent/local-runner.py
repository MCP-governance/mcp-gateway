"""Device executor for gateway-issued local MCP jobs; the gateway is trusted.

Only pre-imported internal-mirror digests run. No container survives a job, including an
ambiguous result. A stop receipt means the local engine confirmed the container is gone.
"""
import base64
import hashlib
import json
import os
import queue
import re
import stat
from contextlib import ExitStack
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

IMAGE = re.compile(r"^[a-z0-9][a-z0-9._/:-]{0,200}@sha256:[0-9a-f]{64}$")
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
ENV_DENIED = re.compile(r"^(LD_|DYLD_|PYTHON|NODE_OPTIONS$|BASH_ENV$|ENV$|PATH$|HOME$)")
PROTOCOL = "2025-06-18"
MAX_LINE = 262144
MAX_BYTES = 1048576
MAX_LINES = 1024
MAX_QUEUE = 32
READ_SECONDS = 20
PREPARE_SECONDS = 180
# 설치·승인 때 미리 받을 때는 첫 호출 한도(PREPARE_SECONDS)에 묶이지 않는다. PJ1의 첫 pull이 5~15분이었다.
PREFETCH_SECONDS = 1800
PREPARE_EVERY = 60
PREPARE_WAITING = 15
PREPARE_RETRY = 300
STDERR_BYTES = 4096
STDERR_LINES = 5
WORKSPACE = '/workspace'  # 컨테이너 안 고정 마운트 위치: 실행 인자가 PC 계정 이름에 묶이지 않는다
ENGINE_ENV = {'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','HOME':'/root','LANG':'C.UTF-8'}


def canonical(manifest):
    # Same bytes as gateway/app/local_jobs.canonical and field/sign-local-manifest.py.
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def signed(manifest, signature, public_pem):
    """openssl, not a Python crypto package: the root service keeps to the standard library."""
    if not public_pem:
        return False
    with tempfile.TemporaryDirectory() as folder:
        files = {"pub": public_pem.encode(), "body": canonical(manifest), "sig": base64.b64decode(signature, validate=True)}
        for name, content in files.items():
            Path(folder, name).write_bytes(content)
        result = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", f"{folder}/pub", "-rawin",
                                 "-in", f"{folder}/body", "-sigfile", f"{folder}/sig"], capture_output=True, timeout=10)
    return result.returncode == 0


def iso(value):
    """datetime.fromisoformat before Python 3.11 (Ubuntu 20.04·22.04) refuses a trailing Z and a fraction that
    is not 3 or 6 digits; a Gateway timestamp may have either."""
    text = re.sub(r"Z$", "+00:00", str(value))
    text = re.sub(r"\.(\d+)(?=[+-]\d\d:\d\d$|$)", lambda m: "." + (m.group(1) + "000000")[:6], text)
    return datetime.fromisoformat(text)


def image_allowed(image, mirrors):
    return bool(IMAGE.fullmatch(image) and any(image.startswith(m.rstrip('/')+'/') for m in mirrors if m))


class PinnedMounts:
    """Pin every parent with openat/O_NOFOLLOW; the local engine binds the held inode, not a user pathname."""
    def __init__(self, manifest, home, owner=None, documents=None):
        """documents: (home, uid, gid) of the employee when the harness runs in a separate managed account. A
        read-only mount then comes from the employee's own home, where they can put files; writable state stays in
        the managed account's home, which the employee cannot reach (D-224)."""
        self.stack, self.paths, self.options, self.readable = ExitStack(), [], [], []
        try:
            if not Path(home).is_absolute() or home in ('/','/root') or ':' in home or ',' in home:
                raise ValueError('허용하지 않는 홈 경로')
            for item in manifest['mounts']:
                relative, mode = item['path'],item['mode']
                parts = relative.split('/')
                if mode not in ('ro','rw') or any(not p or p.startswith('.') or ':' in p or ',' in p for p in parts) or relative.startswith('/'):
                    raise ValueError('허용하지 않는 마운트 경로')
                base, creator, folder_mode = home, owner, 0o700
                if documents and mode == 'ro':
                    base, creator, folder_mode = documents[0], documents[1:], 0o755
                inside = len(Path(base).parts)
                absolute = Path(base).joinpath(*parts)
                parent = None
                for index, part in enumerate(absolute.parts):
                    if creator and index >= inside:
                        # 첫 설치 PC에는 승인된 폴더가 아직 없다(10-23 pj2). 관리 계정 홈 안의 승인 경로만,
                        # 고정된 부모 FD 아래에 그 계정 소유 0700으로 만든다. 이미 있는 링크·파일은 아래 open이 거부한다.
                        try:
                            os.mkdir(part,folder_mode,dir_fd=parent)
                            os.chown(part,*creator,dir_fd=parent,follow_symlinks=False)
                            os.chmod(part,folder_mode,dir_fd=parent)
                        except FileExistsError:
                            pass
                    try:
                        descriptor = os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
                    except OSError as exc:
                        # A missing directory or a symlink anywhere on the path is a refused mount, not a fault.
                        raise ValueError('허용하지 않는 마운트 경로') from exc
                    self.stack.callback(os.close,descriptor)
                    parent=descriptor
                self._inspect(parent)
                info=os.fstat(parent)
                self.paths.append((absolute,parent,info.st_dev,info.st_ino))
                self.options += ['-v',f'/proc/{os.getpid()}/fd/{parent}:{WORKSPACE}/{relative}:{mode}']
                if mode == 'ro':
                    self.readable.append(str(absolute))
        except BaseException:
            self.stack.close()
            raise

    def _inspect(self, root):
        count=0
        # Directory FDs keep inspection independent of rename/link replacement in any parent.
        for _,folders,files,descriptor in os.fwalk('.',dir_fd=root,follow_symlinks=False):
            for name in folders+files:
                count+=1
                info=os.stat(name,dir_fd=descriptor,follow_symlinks=False)
                if count>10000 or stat.S_ISLNK(info.st_mode) or (stat.S_ISREG(info.st_mode) and info.st_nlink!=1):
                    raise ValueError('링크 또는 마운트 검사 상한')
                if not stat.S_ISREG(info.st_mode) and not stat.S_ISDIR(info.st_mode):
                    raise ValueError('일반 파일과 폴더만 마운트합니다')

    def recheck(self):
        for path,descriptor,dev,ino in self.paths:
            # A replacement is refused here; a later replacement still cannot redirect the held FD.
            parent=None
            with ExitStack() as opened:
                for part in path.parts:
                    parent=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
                    opened.callback(os.close,parent)
                info=os.fstat(parent)
                if (info.st_dev,info.st_ino)!=(dev,ino):
                    raise ValueError('실행 직전 마운트 경로가 변경됐습니다')
            self._inspect(descriptor)

    def close(self):
        self.stack.close()


def container_command(engine, manifest, account, *, mount_options=None, namespace='host', name=None, host_paths=None):
    if account.pw_uid<=0 or account.pw_gid<=0:
        raise ValueError('관리 계정은 root로 실행할 수 없습니다')
    if not IMAGE.fullmatch(manifest['image']):
        raise ValueError('digest로 고정하지 않은 이미지')
    env=manifest['env']
    if not isinstance(env,dict) or len(env)>32 or not all(ENV_NAME.fullmatch(k) and not ENV_DENIED.match(k)
            and isinstance(v,str) and len(v)<=256 and '\0' not in v for k,v in env.items()):
        raise ValueError('허용하지 않는 환경 변수')
    command=manifest['command']
    if not isinstance(command,list) or len(command)>32 or not all(isinstance(v,str) and 0<len(v)<=512 and '\0' not in v for v in command):
        raise ValueError('허용하지 않는 명령')
    if mount_options is None:
        raise ValueError('고정된 마운트가 필요합니다')
    name=name or f"mcpgw-local-{manifest['server_id']}-{account.pw_uid}"
    args=[engine] if isinstance(engine,str) else list(engine)
    args += ['run','--rm','-i','--name',name,'--label','mcpgw.local=1','--pull=never','--network=none',
             '--read-only','--tmpfs','/tmp:rw,size=64m','--cap-drop=ALL','--security-opt=no-new-privileges',
             '--pids-limit=128','--memory=512m','--cpus=1','--log-driver=none','--user',f'{account.pw_uid}:{account.pw_gid}']
    if namespace=='podman-auto':
        args+=['--userns=auto']
        mount_options=[v for binding in mount_options[1::2]
                       for source,target,mode in [binding.rsplit(':',2)]
                       for v in ('--mount',f'type=bind,source={source},target={target},{mode},idmap')]
    elif namespace not in ('docker-remap','host'):
        raise ValueError('엔진별 사용자 매핑 설정이 없습니다')
    else:
        # runc 1.2+는 다른 프로세스의 /proc/<pid>/fd 링크를 바인드 원천으로 받지 않는다(EINVAL, 10-22 PJ1 docker 29.8.1).
        # 경로로 바인드하고 생성 직전 recheck()가 고정한 inode와 같은지 확인한다.
        # ponytail: 생성~시작 사이 폴더 교체 경쟁은 남는다. 막으려면 open_tree 지원 엔진의 FD 마운트로 옮긴다.
        if host_paths is None or len(host_paths)!=len(mount_options)//2:
            raise ValueError('경로 바인드에는 고정한 홈 경로가 필요합니다')
        mount_options=[v for binding,host in zip(mount_options[1::2],host_paths)
                       for _,target,mode in [binding.rsplit(':',2)]
                       for v in ('-v',f'{host}:{target}:{mode}')]
    args += [v for k,value in sorted(env.items()) for v in ('-e',f'{k}={value}')]
    return name,args+mount_options+[manifest['image']]+command


def engine_argv(engine):
    binary='/usr/bin/'+engine
    return [binary,'--remote=false'] if engine=='podman' else [binary,'--host','unix:///var/run/docker.sock']


def client_version(argv):
    return subprocess.run(argv+['version','--format','{{.Client.Version}}'],capture_output=True,timeout=5,env=ENGINE_ENV,check=True).stdout.decode().strip()


def detect_engine(setting):
    """PC마다 설치된 엔진과 판본이 다르다. 기기가 한 값을 강제하면 대부분의 PC가 거부되므로 여기서 측정한다."""
    for engine in ('podman','docker'):
        if not os.path.isfile('/usr/bin/'+engine):
            continue
        argv=engine_argv(engine)
        version=client_version(argv)
        if engine=='podman':
            namespace='podman-auto'
        else:
            options=subprocess.run(argv+['info','--format','{{json .SecurityOptions}}'],capture_output=True,timeout=5,env=ENGINE_ENV,check=True).stdout
            namespace='docker-remap' if b'name=userns' in options else 'host'
        return {**setting,'engine':engine,'namespace':namespace,'version':version}
    raise ValueError('컨테이너 엔진이 없습니다')


def engine_configuration(config, manifest, check=None, seconds=PREPARE_SECONDS):
    setting=config.get('local_engine') or {}
    if not setting.get('engine'):
        setting=config['local_engine']=detect_engine(setting)
    engine,namespace=setting.get('engine'),setting.get('namespace')
    if engine not in ('podman','docker') or namespace not in ('podman-auto','docker-remap','host'):
        raise ValueError('엔진별 사용자 매핑 설정이 없습니다')
    if namespace!='host' and not namespace.startswith(engine):
        raise ValueError('엔진과 사용자 매핑 설정이 다릅니다')
    if namespace=='host' and setting.get('accepted_risk')!='탈출 시 호스트 root':
        raise ValueError('탈출 시 호스트 root 범위가 승인되지 않았습니다')
    if not image_allowed(manifest['image'],setting.get('mirrors',[])):
        raise ValueError('내부 미러 이미지가 아닙니다')
    argv=engine_argv(engine)
    version=client_version(argv)
    if not setting.get('version') or version!=setting['version']:
        raise ValueError('측정 대상으로 지정한 엔진 판본과 다릅니다')
    inspect=argv+['image','inspect','--format','{{json .Config.Volumes}}',manifest['image']]
    image=subprocess.run(inspect,capture_output=True,timeout=5,env=ENGINE_ENV)
    if image.returncode:
        # 허용 저장소의 digest 고정 이미지만 여기까지 온다. 받은 내용이 digest와 다르면 엔진이 거부한다.
        # Control polling renews the unstarted claim; a cancelled preparation never starts a container.
        pull=subprocess.Popen(argv+['pull',manifest['image']],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=ENGINE_ENV)
        try:
            end=time.monotonic()+seconds
            while pull.poll() is None:
                if check:
                    check()
                if time.monotonic()>=end:
                    raise TimeoutError('이미지 수신 기한이 지났습니다')
                time.sleep(.2)
            if pull.returncode:
                raise ValueError('승인 이미지를 수신하지 못했습니다')
        finally:
            if pull.poll() is None:
                pull.kill()
                pull.wait(timeout=3)
        image=subprocess.run(inspect,capture_output=True,timeout=5,check=True,env=ENGINE_ENV)
    if len(image.stdout)>16384 or json.loads(image.stdout or b'null'):
        raise ValueError('이미지의 추가 볼륨은 허용하지 않습니다')
    return argv,namespace


class McpError(RuntimeError):
    """The MCP answered the request with a JSON-RPC error. Its message is the only record of why (10-27: memory's
    EROFS on a read-only root came back on stdout while stderr held just the start banner)."""
    def __init__(self, error):
        super().__init__('로컬 MCP가 오류를 반환했습니다')
        error=error if isinstance(error,dict) else {}
        code,text=error.get('code'),error.get('message')
        self.detail=(f'{code} ' if type(code) is int else '')+(text if isinstance(text,str) else '')


def masked_stderr(raw, secrets=()):
    if len(raw)>=STDERR_BYTES:
        # A rolling buffer can begin inside a credential; discard that incomplete line entirely.
        raw=raw.partition(b'\n')[2]
    text=raw.decode('utf-8',errors='replace')
    # Mask before clipping: a boundary must not expose half of a known credential.
    for value in sorted({v for v in secrets if isinstance(v,str) and v},key=len,reverse=True):
        text=text.replace(value,'[비밀 숨김]')
    text=re.sub(r'(?im)^.*(?:token|secret|password|passwd|authorization|api[_-]?key|credential|-----BEGIN).*$',
                '[비밀 숨김]',text)
    text=re.sub(r'(?i)(?:https?://)[^\s/]+@', 'https://[비밀 숨김]@',text)
    text=''.join(c for c in text if c in '\n\t' or ord(c)>=32 and ord(c)!=127)
    lines=[]
    remaining=300
    for line in reversed(text.splitlines()[-STDERR_LINES:]):
        if len(line)>remaining:
            line='[긴 오류 생략]'
        if len(line)+1>remaining:
            break
        lines.append(line)
        remaining-=len(line)+1
    return '\n'.join(reversed(lines))


class Session:
    def __init__(self, engine, manifest, account, namespace, name, check, documents=None):
        self.engine,self.name=engine,name
        self.lines=queue.Queue(MAX_QUEUE)
        self.next_id=0
        self.failure=None
        self.stopped=threading.Event()
        self.stop_lock=threading.Lock()
        self.stop_confirmed=False
        self.creation_uncertain=False
        self.process=None
        self.stderr_tail=bytearray()
        self.stderr_lock=threading.Lock()
        self.stderr_done=threading.Event()
        self.exit_code=None
        self.pinned=None
        self.pinned=PinnedMounts(manifest,account.pw_dir,(account.pw_uid,account.pw_gid),documents)
        try:
            _,command=container_command(engine,manifest,account,mount_options=self.pinned.options,namespace=namespace,name=name,
                                         host_paths=[str(path) for path,*_ in self.pinned.paths])
            check()
            self.pinned.recheck()
            command[command.index('run')]='create'
            # Keep the exited state until our explicit rm, otherwise --rm erases its exit code.
            command.remove('--rm')
            self.creation_uncertain=True
            created=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=5,env=ENGINE_ENV)
            if created.returncode:
                self.stderr_tail.extend(created.stderr[-STDERR_BYTES:])
                self.stderr_done.set()
                raise OSError('로컬 MCP 컨테이너를 생성하지 못했습니다')
            self.creation_uncertain=False
            check()
            self.process=subprocess.Popen(engine+['start','-a','-i',name],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                          bufsize=0,env=ENGINE_ENV)
            threading.Thread(target=self._read_stderr,daemon=True).start()
            threading.Thread(target=self._read,daemon=True).start()
        except BaseException:
            self.pinned.close()
            raise

    def _read_stderr(self):
        try:
            while True:
                chunk=self.process.stderr.read(1024)
                if not chunk:
                    return
                with self.stderr_lock:
                    self.stderr_tail.extend(chunk)
                    del self.stderr_tail[:-STDERR_BYTES]
        except OSError:
            pass
        finally:
            self.stderr_done.set()

    def diagnostic(self, secrets=()):
        self.stderr_done.wait(.2)
        with self.stderr_lock:
            raw=bytes(self.stderr_tail)
        # A launcher error is not proof of an image's file mode; report execution permission only.
        denied=b'permission denied' in raw.lower() and (b'exec' in raw.lower() or b'/app/.venv/' in raw)
        return {'kind':'permission' if denied else 'exited' if self.exit_code is not None else 'failed','exit_code':self.exit_code,
                'stderr_tail':masked_stderr(raw,secrets)}

    def mapping(self, namespace):
        end=time.monotonic()+3
        while True:
            if self.stopped.is_set():
                raise ValueError('폐기된 로컬 MCP 세션')
            result=subprocess.run(self.engine+['inspect','--format','{{.State.Pid}}',self.name],capture_output=True,
                                  timeout=1,check=True,env=ENGINE_ENV)
            pid=int(result.stdout.strip())
            if pid>0:
                break
            if time.monotonic()>=end:
                raise ValueError('컨테이너 실행 프로세스가 없습니다')
            time.sleep(.05)
        mapping=Path(f'/proc/{pid}/uid_map').read_text()
        root=[int(v) for v in mapping.splitlines()[0].split()]
        if namespace!='host' and (root[0]!=0 or root[1]==0):
            raise ValueError('호스트 root 사용자 매핑입니다')
        return {'uid_map':mapping,'namespace':namespace,'scope':'탈출 시 호스트 root' if namespace=='host' else '사용자 매핑 적용'}

    def _read(self):
        pending=bytearray()
        total=lines=0
        try:
            while not self.stopped.is_set():
                chunk=self.process.stdout.read(4096)
                if not chunk:
                    raise OSError('로컬 MCP 프로세스가 종료됐습니다')
                total+=len(chunk)
                if total>MAX_BYTES:
                    raise ValueError('출력 바이트 상한')
                pending.extend(chunk)
                while b'\n' in pending:
                    line,_,tail=pending.partition(b'\n')
                    pending=bytearray(tail)
                    lines+=1
                    if len(line)>MAX_LINE or lines>MAX_LINES:
                        raise ValueError('출력 행 상한')
                    self.lines.put_nowait(bytes(line))
                if len(pending)>MAX_LINE:
                    raise ValueError('출력 행 바이트 상한')
        except (OSError,ValueError,queue.Full) as exc:
            self.failure=type(exc).__name__
            self.stop()

    def _send(self, message):
        if self.stopped.is_set():
            raise OSError('폐기된 로컬 MCP 세션')
        self.process.stdin.write(json.dumps(message,ensure_ascii=False).encode()+b'\n')
        self.process.stdin.flush()

    def request(self, method, params, timeout):
        self.next_id+=1
        ident=self.next_id
        self._send({'jsonrpc':'2.0','id':ident,'method':method,'params':params})
        end=time.monotonic()+min(timeout,READ_SECONDS)
        try:
            while time.monotonic()<end:
                if self.failure or self.stopped.is_set():
                    raise OSError('로컬 MCP 출력 또는 세션이 폐기됐습니다')
                try:
                    line=self.lines.get(timeout=min(.1,max(.001,end-time.monotonic())))
                except queue.Empty:
                    continue
                message=json.loads(line)
                if message.get('id')==ident and 'method' not in message:
                    if 'error' in message:
                        raise McpError(message['error'])
                    return message['result']
                if 'method' in message and 'id' in message:
                    self._send({'jsonrpc':'2.0','id':message['id'],'error':{'code':-32601,'message':'not supported'}})
            raise TimeoutError('로컬 MCP 읽기 기한 상한')
        except BaseException:
            self.stop()
            raise

    def stop(self):
        self.stopped.set()
        with self.stop_lock:
            if self.stop_confirmed:
                return True
            if self.process and self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=3)
            try:
                # Inspect before removal: docker start's status can differ from the container's status.
                if hasattr(self,'stderr_lock'):
                    try:
                        state=subprocess.run(self.engine+['inspect','--format','{{json .State}}',self.name],
                                             capture_output=True,timeout=1,env=ENGINE_ENV)
                        if state.returncode==0:
                            info=json.loads(state.stdout)
                            if not info.get('Running'):
                                self.exit_code=info.get('ExitCode')
                                if info.get('Error'):
                                    with self.stderr_lock:
                                        self.stderr_tail.extend(str(info['Error']).encode()[:STDERR_BYTES])
                                        del self.stderr_tail[:-STDERR_BYTES]
                    except (OSError,ValueError,subprocess.SubprocessError):
                        pass  # 진단 조회가 실패해도 컨테이너 회수는 반드시 시도한다.
                subprocess.run(self.engine+['rm','-f',self.name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=3,env=ENGINE_ENV)
                listed=subprocess.run(self.engine+['ps','-a','--filter',f'name=^{self.name}$','--format','{{.ID}}'],
                                      capture_output=True,timeout=3,env=ENGINE_ENV,check=True)
                gone=not listed.stdout.strip() and not self.creation_uncertain
            except (OSError,ValueError,subprocess.SubprocessError):
                gone=False
            if gone:
                if self.pinned:
                    self.pinned.close()
                self.stop_confirmed=True
            return gone


def check_control(job, control):
    now=time.time()
    if (control['revoked'] or control['lifecycle'] not in ('OPERATING','OBSERVING')
            or any(control[k]!=job[k] for k in ('manifest_sha256','policy_generation','device_epoch','device_policy','policy_version','control_sha256','account_uid'))
            or iso(control['expires_at']).timestamp()<=now
            or iso(control['deadline']).timestamp()<=now
            or control['signature_generation']!=job['manifest']['approval']['generation']):
        raise ValueError('현재 로컬 실행 승인이 아닙니다')


def verify_manifest(config, manifest, signature, digest, server_id):
    """작업 실행과 미리 준비가 같은 검사를 쓴다: 게이트웨이가 준 값이 아니라 이 PC에 고정한 승인 키로 확인한다."""
    if hashlib.sha256(canonical(manifest)).hexdigest()!=digest or manifest.get('server_id')!=server_id:
        raise ValueError('승인 매니페스트가 아닙니다')
    if not signed(manifest,signature,config.get('manifest_pubkey','')):
        raise ValueError('승인 매니페스트 서명이 아닙니다')


def employee_documents(config):
    """별도 관리 계정을 쓰는 직원의 (홈, uid, gid). 읽기 전용 마운트는 그 홈에서 온다(D-224)."""
    if config.get('owner_uid') is None:
        return None
    import pwd
    employee=pwd.getpwuid(config['owner_uid'])
    return (employee.pw_dir,employee.pw_uid,employee.pw_gid)


def execute_job(config, job, request, account):
    manifest=job['manifest']
    if account.pw_uid!=job['account_uid'] or account.pw_uid!=config['uid']:
        raise ValueError('등록한 실행 계정 번호가 아닙니다')
    verify_manifest(config,manifest,job['signature'],job['manifest_sha256'],job['server_id'])
    if iso(job['lease_until']).timestamp()<=time.time():
        raise ValueError('수령 기한이 지났습니다')
    engine=None
    path=f"/api/endpoint/local-jobs/{job['id']}"
    cancelled=threading.Event()
    session=None
    def check():
        if cancelled.is_set():
            raise ValueError('취소된 로컬 실행')
        control=request(config,path+'/control')
        check_control(job,control)
        return control
    control=check()
    def stop_at_deadline():
        if not cancelled.wait(max(0,deadline-time.time())):
            cancelled.set()
            if session:
                session.stop()
    def watch():
        while not cancelled.wait(.2):
            try:
                check()
            except Exception:
                cancelled.set()
                if session:
                    session.stop()
                return
    threading.Thread(target=watch,daemon=True).start()
    answer={'error':'로컬 실행 결과를 확인하지 못했습니다'}
    isolation=None
    mcp_error=''
    try:
        engine,namespace=engine_configuration(config,manifest,check)
        check()
        started=request(config,path+'/start',{})
        check_control(job,started)
        deadline=min(iso(started['deadline']).timestamp(),time.time()+READ_SECONDS)
        threading.Thread(target=stop_at_deadline,daemon=True).start()
        session=Session.__new__(Session)
        session.__init__(engine,manifest,account,namespace,'mcpgw-local-'+job['id'],check,employee_documents(config))
        isolation=session.mapping(namespace)
        isolation['engine_version']=config['local_engine']['version']
        isolation['engine']=config['local_engine']['engine']
        check()
        hello=session.request('initialize',{'protocolVersion':PROTOCOL,'capabilities':{},
                              'clientInfo':{'name':'mint-local-runner','version':'1'}},deadline-time.time())
        if control.get('protocol_version') and hello.get('protocolVersion')!=control['protocol_version']:
            raise ValueError('승인된 프로토콜 판본과 다릅니다')
        session._send({'jsonrpc':'2.0','method':'notifications/initialized'})
        method,params=job['method'],job['params'] or {}
        if method=='initialize':
            result=hello
        elif method=='tools/list' and set(params)<={'cursor'}:
            check()
            result=session.request(method,params,deadline-time.time())
        elif method=='tools/call' and set(params)=={'name','arguments'}:
            # Each fresh container must present the requested tool's approved contract on this device.
            listed=session.request('tools/list',{},deadline-time.time())
            tool=next((t for t in listed.get('tools',[]) if t.get('name')==params['name']),None)
            pin=control['contracts'].get(params['name'])
            if not tool or not pin or any(hashlib.sha256(canonical(value)).hexdigest()!=pin[key] for key,value in
                [('description_sha256',tool.get('description','')),('schema_sha256',tool.get('inputSchema',{})),
                 ('output_schema_sha256',tool.get('outputSchema'))]):
                raise ValueError('엔드포인트의 도구 계약이 승인값과 다릅니다')
            check()
            result=session.request(method,params,deadline-time.time())
        else:
            raise ValueError('허용하지 않는 로컬 요청')
        answer={'result':result}
    except Exception as exc:
        reason='timeout' if isinstance(exc,TimeoutError) else 'failed'
        answer={'error':'로컬 MCP 실행을 완료하지 못했습니다','diagnostics':{'kind':reason,'exit_code':None,'stderr_tail':''}}
        mcp_error=exc.detail if isinstance(exc,McpError) else ''
        # Only to this PC's journal: a failure before the container starts left no cause anywhere (10-23 PJ1).
        # The runner's own ValueError messages carry no data; other exceptions keep their type only.
        detail=str(exc)[:200] if type(exc) is ValueError else ''
        if hasattr(exc,'code') and hasattr(exc,'read'):  # urllib HTTPError: the Gateway's own refusal sentence
            try:
                detail=f'{exc.code} '+exc.read()[:300].decode(errors='replace')
            except Exception:
                pass
        print(json.dumps({'local_runner':'job_failed','job':job['id'],'error':type(exc).__name__,'detail':detail},
                         ensure_ascii=False),flush=True)
    finally:
        cancelled.set()
        if isolation:
            answer['isolation']=isolation
        # Even an initialization failure has a durable started row and needs a stop receipt.
        if session:
            answer['stopped']=session.stop()
            if 'error' in answer and hasattr(session,'stderr_lock'):
                secrets=[*(config.get(k) for k in ('device_key','access_token','refresh_token','password')),
                         *(manifest.get('env') or {}).values()]
                diagnostic=session.diagnostic(secrets)
                if answer['diagnostics']['kind']=='timeout' and diagnostic['kind']!='permission':
                    diagnostic['kind']='timeout'
                if mcp_error:
                    # The same masking as stderr: the MCP's message can echo arguments or file contents.
                    diagnostic['mcp_error']=masked_stderr(mcp_error.encode(),secrets)
                answer['diagnostics']=diagnostic
        elif engine is None:
            answer['stopped']=True  # 엔진 준비 실패 전에는 컨테이너 생성 자체를 시도하지 않았다.
        else:
            listed=subprocess.run(engine+['ps','-a','--filter',f"name=^mcpgw-local-{job['id']}$",'--format','{{.ID}}'],
                                  capture_output=True,timeout=3,env=ENGINE_ENV,check=True)
            answer['stopped']=not listed.stdout.strip()
    return answer


def recover(config, request):
    jobs=request(config,'/api/endpoint/local-jobs/recovery').get('jobs',[])
    for job in jobs:
        identity=str(uuid.UUID(job['id']))
        name='mcpgw-local-'+identity
        engines=0
        for engine in ('podman','docker'):
            if not os.path.isfile('/usr/bin/'+engine):
                continue
            engines+=1
            args=engine_argv(engine)
            subprocess.run(args+['rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=3,env=ENGINE_ENV)
            listed=subprocess.run(args+['ps','-a','--filter',f'name=^{name}$','--format','{{.ID}}'],
                                  capture_output=True,timeout=3,env=ENGINE_ENV,check=True)
            if listed.stdout.strip():
                raise OSError('이전 로컬 컨테이너 정지가 확인되지 않았습니다')
        if not engines:
            raise OSError('컨테이너 엔진 정지를 확인할 수 없습니다')
        request(config,f'/api/endpoint/local-jobs/{identity}',{'error':'실행기 재연결 후 정지 확인','stopped':True})


# 승인된 로컬 서버의 폴더·이미지를 첫 호출 전에 준비한 결과. 서비스가 읽어 `mcpgw-status`에 싣는다.
# ready·total이 None이면 아직 게이트웨이에서 목록을 받지 못한 것이다(활성화 대기 등).
preparation={'ready':None,'total':None,'note':'','documents':[]}


def prepare_reason(exc):
    # 러너 자신의 ValueError 문장은 데이터를 담지 않는다. 그 밖의 예외는 종류만 말한다.
    if isinstance(exc,TimeoutError):
        return '이미지 수신 기한이 지났습니다'
    if type(exc) is ValueError:
        return str(exc)[:60]
    if isinstance(exc,(KeyError,TypeError,AttributeError)):
        return '승인 정보 형식이 올바르지 않습니다'
    if isinstance(exc,subprocess.SubprocessError):
        return '컨테이너 엔진을 사용할 수 없습니다'
    return '폴더 또는 엔진 준비에 실패했습니다'


def ensure_mounts(manifest, account, documents):
    """승인 폴더를 첫 호출 전에 만든다. 소유·권한·링크 거부는 실행 때와 같은 PinnedMounts가 정한다(D-223·D-224)."""
    mounts=PinnedMounts(manifest,account.pw_dir,(account.pw_uid,account.pw_gid),documents)
    try:
        return list(mounts.readable)
    finally:
        mounts.close()


def prepare_once(config, request, log, account, done, folders, failed):
    """한 바퀴: 승인 목록을 받아 새 서버만 준비하고, 다음 확인까지 기다릴 초를 돌려준다.
    done·folders·failed는 바퀴를 넘겨 쓰는 기억이다. 준비한 서버는 다시 열어 보지 않는다(엔진에서 이미지를 지웠다면
    첫 호출이 같은 함수로 다시 받는다)."""
    try:
        entries=request(config,'/api/endpoint/local-manifests').get('servers',[])
    except Exception as exc:
        # 활성화 전 장치(401·403·409)와 이 경로를 모르는 이전 게이트웨이(404·405)는 오류가 아니라 기다림이다.
        status=getattr(exc,'code',None)
        preparation.update(ready=None,total=None,note='',documents=[])
        if status not in (401,403,404,405,409):
            log({'local_runner':'prepare_error','error':type(exc).__name__})
        return PREPARE_WAITING if status in (401,403,409) else PREPARE_EVERY
    documents=employee_documents(config)
    current={(entry['server_id'],entry['manifest_sha256']) for entry in entries}
    for memory in (folders,failed):
        for key in set(memory)-current:
            del memory[key]
    done.intersection_update(current)
    preparation.update(ready=len(done),total=len(entries),note='',documents=sorted({d for key in folders for d in folders[key]}))
    for entry in entries:
        key=(entry['server_id'],entry['manifest_sha256'])
        if key in done:
            continue
        name=str(entry['server_id'])[:64]
        if key in failed and failed[key][0]>time.monotonic():
            continue
        try:
            manifest=entry['manifest']
            verify_manifest(config,manifest,entry['signature'],entry['manifest_sha256'],entry['server_id'])
            if iso(manifest['approval']['expires_at']).timestamp()<=time.time():
                raise ValueError('승인 기한이 지났습니다')
            folders[key]=ensure_mounts(manifest,account,documents)
            preparation.update(note='이미지 받는 중: '+name,documents=sorted({d for k in folders for d in folders[k]}))
            engine_configuration(config,manifest,seconds=PREFETCH_SECONDS)
            done.add(key)
            failed.pop(key,None)
            preparation.update(ready=len(done),note='')
            log({'local_runner':'prepared','server':name})
        except Exception as exc:
            reason=prepare_reason(exc)
            if failed.get(key,(0,''))[1]!=reason:
                log({'local_runner':'prepare_failed','server':name,'reason':reason})
            failed[key]=(time.monotonic()+PREPARE_RETRY,reason)
    preparation['note']=next((reason for key,(_,reason) in failed.items() if key in current),'')
    return PREPARE_EVERY


def prepare(config, request, log):
    """서비스가 별도 스레드로 돌린다. 작업 수령 루프(run)와 섞이지 않아 이미지를 받는 동안에도 호출이 막히지 않는다."""
    import pwd
    account=pwd.getpwnam(config['username'])
    done,folders,failed=set(),{},{}
    while True:
        time.sleep(prepare_once(config,request,log,account,done,folders,failed))


def run(config, request, log):
    import pwd
    account=pwd.getpwnam(config['username'])
    failures,last=0,None
    while True:
        try:
            recover(config,request)
            job=request(config,'/api/endpoint/local-jobs?wait=5').get('job')
            if last is not None:
                log({'local_runner':'ready'})
            failures,last=0,None
            if not job:
                continue
            try:
                answer=execute_job(config,job,request,account)
            except Exception as exc:
                # No start grant was accepted, or the outcome is unknown; never retry a claimed job.
                answer={'error':type(exc).__name__,'stopped':False}
            request(config,f"/api/endpoint/local-jobs/{job['id']}",answer)
        except Exception as exc:
            # The Gateway refuses a device that is not active (pending activation, quarantined): that is waiting, not a
            # fault. Say it once per change and back off, instead of an error line every second (D-217).
            status=getattr(exc,'code',None)
            kind=('waiting',status) if status in (401,403,409) else ('error',type(exc).__name__)
            if kind!=last:
                log({'local_runner':kind[0],**({'status':status} if kind[0]=='waiting' else {'error':kind[1]})})
            last=kind
            failures+=1
            time.sleep(min(30,2**min(failures,5)) if kind[0]=='waiting' else 1)

