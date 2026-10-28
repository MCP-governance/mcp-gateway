"""Resolve wheels without executing repository code; scan exactly the downloaded installation set."""
import hashlib
import ast
import json
from pathlib import Path
import re
import shutil
import sys
import tomllib
import zipfile
from email.parser import BytesParser

from packaging.requirements import Requirement


TARGETS = {
    'win_amd64': ('3.13', 'x86_64-pc-windows-msvc', ['win_amd64']),
    'linux_x86_64': ('3.12', 'x86_64-unknown-linux-gnu',
                     [f'manylinux_2_{minor}_x86_64' for minor in range(28, 16, -1)] + ['manylinux2014_x86_64']),
}


def normalized(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def projects(checkout, repository, subpath):
    if repository.rstrip('/').removesuffix('.git').lower() == 'https://github.com/microsoft/markitdown':
        return [checkout / 'packages/markitdown', checkout / 'packages/markitdown-mcp'], 'packages/markitdown-mcp/src/markitdown_mcp/__main__.py'
    folder = checkout / subpath if subpath else checkout
    return [folder], ''


def requirements(folders):
    data = []
    for folder in folders:
        document = tomllib.loads((folder / 'pyproject.toml').read_text(encoding='utf-8'))
        project = document['project']
        if 'version' in project.get('dynamic', []):
            relative = document.get('tool', {}).get('hatch', {}).get('version', {}).get('path', '')
            if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_./-]*', relative) or any(p in ('', '.', '..') for p in relative.split('/')):
                raise ValueError('정적 판본 파일 경로가 필요합니다')
            module = ast.parse((folder / relative).read_text(encoding='utf-8'))
            values = [node.value.value for node in module.body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == '__version__' for target in node.targets)
                      and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)]
            if len(values) != 1:
                raise ValueError('실행 없이 소스 판본을 확인할 수 없습니다')
            project['version'] = values[0]
        data.append(project)
    local = {normalized(project['name']): project for project in data}
    result, visited = set(), set()

    def collect(project, extras=()):
        key = (project['name'], tuple(sorted(extras)))
        if key in visited:
            return
        visited.add(key)
        if 'dependencies' in project.get('dynamic', []):
            raise ValueError('동적 의존성은 실행 없이 확인할 수 없습니다')
        dependencies = list(project.get('dependencies', []))
        for extra in extras:
            dependencies += project.get('optional-dependencies', {}).get(extra, [])
        for text in dependencies:
            requirement = Requirement(text)
            if requirement.url:
                raise ValueError('패키지 인덱스 외 의존성은 지원하지 않습니다')
            if normalized(requirement.name) in local:
                dependency = local[normalized(requirement.name)]
                if requirement.specifier and (not dependency.get('version') or dependency['version'] not in requirement.specifier):
                    raise ValueError('동일 커밋 내부 패키지 판본 불일치')
                collect(dependency, requirement.extras)
            else:
                result.add(str(requirement))
    for project in data:
        collect(project)
    return sorted(result)


def generate(checkout, request, commit, report_dir, run):
    folders, entrypoint = projects(checkout, request['repository_url'], request.get('repository_path') or '')
    if not all((folder / 'pyproject.toml').is_file() for folder in folders):
        return None, checkout
    dependencies = requirements(folders)
    work = checkout.parent / (checkout.name + '-dependencies')
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    scan = work / 'scan'
    shutil.copytree(checkout, scan / 'source', symlinks=True)
    source = {'runtime': 'python', 'entrypoint': entrypoint, 'commit': commit, 'locks': {}}
    inputs = work / 'requirements.in'
    inputs.write_text('\n'.join(dependencies) + '\n', encoding='utf-8')
    for target, (version, platform, wheel_platforms) in TARGETS.items():
        resolved = work / (target + '.resolved')
        compiled = run(['uv', '--no-config', '--no-python-downloads', 'pip', 'compile', str(inputs), '--python-version', version,
                        '--python-platform', platform, '--no-build', '--no-sources', '--generate-hashes',
                        '--no-annotate', '--no-header', '--default-index', 'https://pypi.org/simple',
                        '--output-file', str(resolved)], timeout=600)
        if compiled.returncode or not resolved.is_file():
            raise ValueError(f'{target}: wheel 의존성 해석 실패(소스 빌드 불가)')
        wheels = work / target
        wheels.mkdir()
        args = [sys.executable, '-I', '-m', 'pip', '--isolated', 'download', '--require-hashes',
                '--only-binary=:all:', '--no-deps', '--python-version', version, '--implementation', 'cp',
                '--abi', 'cp' + version.replace('.', ''), '--index-url', 'https://pypi.org/simple',
                '--dest', str(wheels), '-r', str(resolved)]
        for wheel_platform in wheel_platforms:
            args += ['--platform', wheel_platform]
        if dependencies and run(args, timeout=600).returncode:
            raise ValueError(f'{target}: 설치할 wheel이 없습니다(소스 빌드 불가)')
        locked = {}
        for wheel in sorted(wheels.iterdir()):
            if wheel.suffix != '.whl':
                raise ValueError('wheel 외 배포 파일 거부')
            with zipfile.ZipFile(wheel) as archive:
                metadata = [name for name in archive.namelist() if name.endswith('.dist-info/METADATA')]
                if len(metadata) != 1:
                    raise ValueError('wheel 메타데이터 불일치')
                package = BytesParser().parsebytes(archive.read(metadata[0]))
                name, version_id = normalized(package['Name']), package['Version']
                if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', name) or not re.fullmatch(r'[A-Za-z0-9_.+!-]+', version_id) or name in locked:
                    raise ValueError('wheel 패키지 식별자 중복 또는 오류')
                # Metadata and package bytes are the SBOM/SCA inputs; none are imported.
                destination = scan / target / name
                if len(archive.infolist()) > 10000 or sum(item.file_size for item in archive.infolist()) > 512 << 20:
                    raise ValueError('wheel 압축 해제 상한')
                for item in archive.infolist():
                    path = Path(item.filename)
                    if path.is_absolute() or '..' in path.parts or '\\' in item.filename or ':' in item.filename or (item.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError('안전하지 않은 wheel 경로')
                    if item.file_size > 128 << 20:
                        raise ValueError('wheel 파일 크기 상한')
                archive.extractall(destination)
            locked[name] = f'{name}=={version_id} --hash=sha256:{hashlib.sha256(wheel.read_bytes()).hexdigest()}'
        if dependencies and not locked:
            raise ValueError('설치 집합이 비었습니다')
        content = ('\n'.join(locked[name] for name in sorted(locked)) + '\n').encode()
        digest = hashlib.sha256(content).hexdigest()
        path = report_dir / f'dependency-{digest}.lock'
        path.write_bytes(content)
        (scan / target).mkdir(exist_ok=True)
        (scan / target / 'requirements.txt').write_bytes(content)
        source['locks'][target] = {'python': TARGETS[target][0], 'sha256': digest,
                                   'packages': len(locked)}
    source.update(lock='requirements.lock', lock_sha256=source['locks']['win_amd64']['sha256'])
    return source, scan


def verify_sbom(path, source, report_dir):
    document = json.loads(path.read_text(encoding='utf-8'))
    actual = {(normalized(item.get('name', '')), str(item.get('version', '')))
              for item in document.get('components', []) if isinstance(item, dict)}
    for lock in source['locks'].values():
        content = (report_dir / f"dependency-{lock['sha256']}.lock").read_bytes()
        if hashlib.sha256(content).hexdigest() != lock['sha256']:
            raise ValueError('SBOM 검사 중 의존성 잠금 변경')
        expected = {tuple(line.split(' --hash=', 1)[0].split('==', 1))
                    for line in content.decode().splitlines() if line.strip()}
        if len(expected) != lock['packages'] or not expected <= actual:
            raise ValueError('Syft SBOM과 설치할 의존성 집합이 다릅니다')
