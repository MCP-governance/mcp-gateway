"""Prepare an approved source tree; never execute installation hooks or accept ambient credentials."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import platform

LIMIT = 128 << 20
LOCK = threading.Lock()


def relative(value):
    if (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_./-]{0,255}', value)
            or any(p in ('', '.', '..') for p in value.split('/'))):
        raise ValueError('안전한 상대 경로가 아닙니다')
    return value


def unpack(spool, destination, expected):
    entries, names, roots, total = [], set(), set(), 0
    with tarfile.open(fileobj=spool, mode='r:gz') as archive:
        for index, item in enumerate(archive):
            if index >= 10000 or not (item.isfile() or item.isdir()):
                raise ValueError('소스 파일 형식 또는 수 상한')
            name = item.name.rstrip('/')
            parts = name.split('/')
            if (not name or name.startswith('/') or '\\' in name or ':' in name
                    or any(part in ('', '.', '..') for part in parts)
                    or any(ord(c)<32 or ord(c)==127 for c in name)):
                raise ValueError('안전한 소스 경로가 아닙니다')
            roots.add(parts[0])
            if name in names or len(roots) != 1:
                raise ValueError('중복 경로 또는 여러 최상위 폴더')
            names.add(name)
            if item.isdir():
                continue
            if len(parts) < 2 or ':' in name or any(p.split('.')[0].upper() in
                    {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(i) for i in range(10)), *('LPT'+str(i) for i in range(10))}
                    or p.endswith(('.', ' ')) for p in parts):
                raise ValueError('이식할 수 없는 소스 경로')
            total += item.size
            if total > LIMIT:
                raise ValueError('소스 크기 상한')
            target = destination.joinpath(*parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            with archive.extractfile(item) as reader, target.open('xb') as writer:
                for block in iter(lambda: reader.read(65536), b''):
                    digest.update(block)
                    writer.write(block)
            entries.append(('/'.join(parts[1:]), digest.hexdigest()))
    actual = hashlib.sha256(''.join(f'{digest}  {name}\n' for name, digest in sorted(entries)).encode()).hexdigest()
    if not entries or actual != expected:
        raise ValueError('승인 소스 다이제스트가 다릅니다')


def file_hash(path):
    digest=hashlib.sha256()
    with path.open('rb') as reader:
        for block in iter(lambda:reader.read(1<<20), b''):
            digest.update(block)
    return digest.hexdigest()


def inventory(folder):
    result = {}
    for path in folder.rglob('*'):
        if path.is_symlink():
            raise ValueError('실행기 폴더 링크 거부')
        if path.is_file() and path != folder / '.ready.json':
            result[path.relative_to(folder).as_posix()] = file_hash(path)
    return result


def environment(manifest):
    env = {'LANG': 'C.UTF-8'}
    if os.name == 'nt':
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        if not ctypes.windll.kernel32.GetWindowsDirectoryW(buffer, len(buffer)):
            raise OSError('Windows 시스템 경로 확인 실패')
        env['SystemRoot'] = buffer.value
    denied = re.compile(r'^(LD_|DYLD_|PYTHON|NODE_OPTIONS$|NODE_PATH$|SYSTEMROOT$|WINDIR$|COMSPEC$|PATHEXT$|BASH_ENV$|ENV$|PATH$|HOME$)')
    values = manifest.get('env')
    if not isinstance(values, dict) or len(values) > 32:
        raise ValueError('허용하지 않는 환경 변수')
    for key, value in values.items():
        if (not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', key) or denied.match(key)
                or not isinstance(value, str) or len(value) > 256 or '\0' in value):
            raise ValueError('허용하지 않는 환경 변수')
        env[key] = value
    return env


def prepare(config, manifest, request, check=None, seconds=1800):
    if os.name != 'nt' and sys.version_info < (3, 9):
        raise ValueError('프로세스 모드에는 Python 3.9 이상이 필요합니다')
    source = manifest['source']
    if (source['runtime'] not in ('python', 'node') or manifest['image'] or manifest['mounts']
            or not re.fullmatch(r'[0-9a-f]{40}', source['commit'])
            or any(not re.fullmatch(r'[0-9a-f]{64}', source[k]) for k in ('sha256', 'lock_sha256'))):
        raise ValueError('승인 소스 식별자가 아닙니다')
    relative(source['entrypoint']); relative(source['lock'])
    env = environment(manifest)
    selected = None
    if source.get('locks'):
        if platform.machine().lower() not in ('amd64', 'x86_64'):
            raise ValueError('승인된 x86_64 플랫폼이 아닙니다')
        target = 'win_amd64' if os.name == 'nt' else 'linux_x86_64' if sys.platform == 'linux' else ''
        selected = source['locks'].get(target)
        if not selected or selected['python'] != f'{sys.version_info.major}.{sys.version_info.minor}':
            raise ValueError('공급망 검사한 Python 판본의 잠금이 없습니다')
        if target == 'linux_x86_64':
            libc, version = platform.libc_ver()
            if libc != 'glibc' or tuple(int(part) for part in version.split('.')[:2]) < (2, 28):
                raise ValueError('검사한 Linux wheel에는 glibc 2.28 이상이 필요합니다')
    base = Path(config['source_root'])
    digest = hashlib.sha256(json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    folder = base / digest
    end = time.monotonic() + seconds
    def current():
        if check:
            check()
        if time.monotonic() >= end:
            raise TimeoutError('소스 준비 기한이 지났습니다')
    while not LOCK.acquire(timeout=.2):
        current()
    try:
        current()
        if not config['source_protected'](base):
            raise ValueError('실행기 폴더 보호 확인 실패')
        ready = folder / '.ready.json'
        if ready.is_file():
            if not config['source_protected'](folder):
                raise ValueError('준비 폴더 보호 확인 실패')
            if json.loads(ready.read_text(encoding='utf-8')) != inventory(folder):
                raise ValueError('준비한 실행 파일이 변경되었습니다')
            return command(folder, source, manifest, config), folder, env
        with tempfile.TemporaryDirectory(dir=base, prefix='prepare-') as temporary:
            stage = Path(temporary)
            tree = stage / 'source'
            tree.mkdir()
            with tempfile.SpooledTemporaryFile(max_size=4<<20) as spool:
                headers = request(config, f"/api/endpoint/local-sources/{manifest['server_id']}?manifest={digest}",
                                  download=spool, deadline=end)
                current()
                if headers.get('X-Content-SHA256') != source['sha256']:
                    raise ValueError('소스 응답 해시 불일치')
                spool.seek(0)
                unpack(spool, tree, source['sha256'])
            lock = tree / source['lock']
            if selected:
                lock = stage / 'requirements.lock'
                with lock.open('xb') as writer:
                    headers = request(config, f"/api/endpoint/local-sources/{manifest['server_id']}?manifest={digest}&lock={target}",
                                      download=writer, deadline=end)
                if headers.get('X-Content-SHA256') != selected['sha256']:
                    raise ValueError('의존성 잠금 응답 해시 불일치')
            if file_hash(lock) != (selected['sha256'] if selected else source['lock_sha256']):
                raise ValueError('의존성 잠금 해시 불일치')
            if not (tree / source['entrypoint']).is_file():
                raise ValueError('진입 파일이 없습니다')
            if source['runtime'] == 'python':
                pip = Path(__file__).with_name('pip.zip')
                if not pip.is_file():
                    raise ValueError('승인 pip 실행 파일이 없습니다')
                args = [sys.executable, '-I', '-S', str(pip), '--isolated', 'install', '--require-hashes',
                        '--only-binary=:all:', '--no-deps', '--no-compile', '--no-cache-dir', '--disable-pip-version-check',
                        '--index-url', 'https://pypi.org/simple', '--target', str(stage / 'packages'), '-r', str(lock)]
                # A lock may not add indexes, editable sources or command options; hashes pin every wheel.
                text = lock.read_text(encoding='utf-8')
                for line in text.replace('\\\n', ' ').splitlines():
                    line = line.strip()
                    if line and not line.startswith('#') and not re.fullmatch(
                            r'[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?==[A-Za-z0-9_.+!-]+(?:\s+--hash=sha256:[0-9a-f]{64})+', line):
                        raise ValueError('해시로 고정한 wheel 잠금만 허용합니다')
            else:
                if source['lock'] != 'package-lock.json':
                    raise ValueError('Node 잠금 파일 경로')
                locked = json.loads(lock.read_text(encoding='utf-8'))
                if locked.get('lockfileVersion') not in (2, 3) or not locked.get('packages'):
                    raise ValueError('Node 잠금 형식')
                for name, package in locked['packages'].items():
                    if name and (package.get('link') or not re.fullmatch(r'sha512-[A-Za-z0-9+/]+=*', package.get('integrity', ''))
                                 or not package.get('resolved', '').startswith('https://registry.npmjs.org/')):
                        raise ValueError('Node 잠금 무결성 또는 배포 주소')
                node = config.get('node_executable')
                npm = config.get('npm_cli')
                if not node or not npm or not Path(node).is_file() or not Path(npm).is_file():
                    raise ValueError('승인 Node 런타임이 없습니다')
                args = [node, npm, 'ci', '--ignore-scripts', '--bin-links=false', '--no-audit', '--no-fund', '--registry=https://registry.npmjs.org']
            current()
            # Installation output can contain repository text; it never enters a log or a tool response.
            process = subprocess.Popen(args, cwd=tree, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                while process.poll() is None:
                    current()
                    time.sleep(.1)
                if process.returncode:
                    raise ValueError('의존성 설치 실패')
            finally:
                if process.poll() is None:
                    process.kill(); process.wait(timeout=3)
            current()
            (stage / '.ready.json').write_text(json.dumps(inventory(stage), sort_keys=True), encoding='utf-8')
            if os.name != 'nt':
                for path in stage.rglob('*'):
                    path.chmod(0o755 if path.is_dir() else 0o644)
                stage.chmod(0o755)
            elif not config['source_seal'](stage):
                raise ValueError('직원 읽기·실행 권한 설정 실패')
            os.rename(stage, folder)
        current()
        return command(folder, source, manifest, config), folder, env
    finally:
        LOCK.release()


def command(folder, source, manifest, config):
    args = manifest['command']
    if (not isinstance(args, list) or len(args) > 32 or any(not isinstance(a, str) or not a or len(a)>512 or '\0' in a for a in args)):
        raise ValueError('허용하지 않는 명령')
    entry = folder / 'source' / relative(source['entrypoint'])
    if source['runtime'] == 'node':
        node = config.get('node_executable')
        if not node or not Path(node).is_file():
            raise ValueError('승인 Node 런타임이 없습니다')
        return [node, str(entry), *args]
    if not Path(sys.executable).is_file():
        raise ValueError('Python 런타임이 없습니다')
    paths = [folder / 'packages', entry.parent, folder / 'source']
    paths += sorted(p for p in (folder / 'source').rglob('src') if p.is_dir())
    if len(paths) > 64:
        raise ValueError('Python 소스 경로 수 상한')
    target, module = str(entry), False
    if entry.name == '__main__.py' and (entry.parent / '__init__.py').is_file():
        package, parent = [], entry.parent
        while (parent / '__init__.py').is_file():
            package.insert(0, parent.name)
            parent = parent.parent
        paths.append(parent)
        target, module = '.'.join(package), True
    script = "import sys,runpy,json;sys.path[:0]=json.loads(sys.argv[1]);p=sys.argv[3];m=sys.argv[2]=='module';sys.argv=sys.argv[3:];(runpy.run_module if m else runpy.run_path)(p,run_name='__main__')"
    return [sys.executable, '-I', '-S', '-B', '-c', script, json.dumps([str(p) for p in paths]),
            'module' if module else 'path', target, *args]
