"""Offline resolver/scanner boundary checks; wheel fixtures are data, never MCP implementations."""
import hashlib
import json
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
if sys.version_info < (3, 11):
    from pip._vendor import tomli
    sys.modules.setdefault('tomllib', tomli)
spec = importlib.util.spec_from_file_location('dependency_locks', ROOT / 'full_stack_lab/supply_chain/dependency_locks.py')
locks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(locks)


class Dependencies(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.checkout = self.base / 'checkout'
        self.checkout.mkdir()
        (self.checkout / 'pyproject.toml').write_text('[project]\nname="approved"\nversion="1"\ndependencies=["example>=1"]\n')
        self.reports = self.base / 'reports'
        self.reports.mkdir()
        self.request = {'repository_url':'https://github.com/example/approved', 'repository_path':''}
        self.calls, self.wheels = [], {}

    def run_tool(self, args, timeout):
        self.calls.append(args)
        if args[0] == 'uv':
            Path(args[args.index('--output-file') + 1]).write_text('example==1 --hash=sha256:' + 'a'*64)
        else:
            directory = Path(args[args.index('--dest') + 1])
            wheel = directory / 'example-1-py3-none-any.whl'
            with zipfile.ZipFile(wheel, 'w') as archive:
                archive.writestr('example-1.dist-info/METADATA', 'Metadata-Version: 2.1\nName: example\nVersion: 1\n')
                archive.writestr('example.py', '# fixture package data\n')
            self.wheels[directory.name] = wheel.read_bytes()
        return SimpleNamespace(returncode=0)

    def test_platform_wheels_hashes_and_scanner_set_match(self):
        source, scan = locks.generate(self.checkout, self.request, 'a'*40, self.reports, self.run_tool)
        self.assertEqual(set(source['locks']), {'win_amd64','linux_x86_64'})
        self.assertEqual(source['commit'], 'a'*40)
        for target, record in source['locks'].items():
            content = (self.reports / f"dependency-{record['sha256']}.lock").read_bytes()
            self.assertEqual(hashlib.sha256(content).hexdigest(), record['sha256'])
            self.assertIn(hashlib.sha256(self.wheels[target]).hexdigest().encode(), content)
            self.assertTrue((scan / target / 'example/example-1.dist-info/METADATA').is_file())
            self.assertEqual(record['packages'],1)
            self.assertEqual((scan/target/'requirements.txt').read_bytes(),content)
        self.assertEqual((scan/'source/pyproject.toml').read_bytes(), (self.checkout/'pyproject.toml').read_bytes())
        for args in self.calls:
            if args[0]=='uv':
                self.assertIn('--no-build',args)
                self.assertIn('--python-platform',args)
            else:
                self.assertIn('--require-hashes',args)
                self.assertIn('--only-binary=:all:',args)
                self.assertIn('--no-deps',args)

    def test_sbom_must_include_every_locked_name_and_version(self):
        source, scan=locks.generate(self.checkout,self.request,'a'*40,self.reports,self.run_tool)
        sbom=self.base/'sbom.json'
        sbom.write_text(json.dumps({'components':[{'name':'example','version':'1'}]}))
        locks.verify_sbom(sbom,source,self.reports)
        for inventory in ([],[{'name':'example','version':'2'}]):
            sbom.write_text(json.dumps({'components':inventory}))
            with self.assertRaisesRegex(ValueError,'집합'):locks.verify_sbom(sbom,source,self.reports)
        record=source['locks']['win_amd64']
        (self.reports/f"dependency-{record['sha256']}.lock").write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'잠금 변경'):locks.verify_sbom(sbom,source,self.reports)

    def test_missing_wheel_or_resolver_failure_does_not_publish_lock(self):
        with self.assertRaisesRegex(ValueError,'wheel'):
            locks.generate(self.checkout, self.request, 'a'*40, self.reports,
                           lambda *a,**kw:SimpleNamespace(returncode=1))
        self.assertFalse(list(self.reports.iterdir()))

    def test_dynamic_and_direct_url_dependencies_refused(self):
        for declaration in ('dynamic=["dependencies"]','dependencies=["example @ https://example.org/pkg.whl"]'):
            (self.checkout/'pyproject.toml').write_text('[project]\nname="approved"\nversion="1"\n'+declaration)
            with self.assertRaises(ValueError):locks.requirements([self.checkout])

    def test_monorepo_server_package_and_its_same_commit_dependency_without_repository_rules(self):
        # MarkItDown 구조(packages/markitdown, packages/markitdown-mcp). 저장소 주소와 무관하게 같은 결과여야 한다.
        (self.checkout/'pyproject.toml').unlink()  # 실제 저장소처럼 최상위에는 pyproject가 없다
        core, server = self.checkout/'packages/markitdown', self.checkout/'packages/markitdown-mcp'
        for folder in (core, server/'src/markitdown_mcp'):folder.mkdir(parents=True)
        (core/'pyproject.toml').write_text('[project]\nname="markitdown"\nversion="1"\ndependencies=["base>=1"]\n[project.optional-dependencies]\nall=["document>=2"]\n')
        (server/'pyproject.toml').write_text('[project]\nname="markitdown-mcp"\nversion="1"\ndependencies=["markitdown[all]>=1","mcp>=1"]\n')
        (server/'src/markitdown_mcp/__main__.py').write_text('')
        for url in ('https://github.com/microsoft/markitdown', 'https://example.org/any/repo'):
            for subpath in ('', 'packages/markitdown-mcp'):
                folders, entry = locks.projects(self.checkout, url, subpath)
                self.assertEqual(sorted(folders), sorted([core, server]))
                self.assertEqual(locks.requirements(folders),['base>=1','document>=2','mcp>=1'])
                self.assertEqual(entry,'packages/markitdown-mcp/src/markitdown_mcp/__main__.py')
        # MCP 서버 패키지가 둘이면 경로 없이 고르지 않는다.
        other=self.checkout/'packages/other-mcp'; other.mkdir(parents=True)
        (other/'pyproject.toml').write_text('[project]\nname="other-mcp"\nversion="1"\ndependencies=["mcp>=1"]\n')
        self.assertEqual(locks.projects(self.checkout,'https://example.org/any/repo',''),([self.checkout],''))

    def test_hatch_dynamic_version_is_read_as_data_without_importing(self):
        about=self.checkout/'about.py'
        about.write_text('raise RuntimeError("must not execute")\n__version__="0.1.9"\n')
        (self.checkout/'pyproject.toml').write_text('[project]\nname="approved"\ndynamic=["version"]\ndependencies=[]\n[tool.hatch.version]\npath="about.py"\n')
        self.assertEqual(locks.requirements([self.checkout]),[])

    def test_wheel_path_traversal_is_refused(self):
        run=self.run_tool
        def malicious(args,timeout):
            result=run(args,timeout)
            if args[0]!='uv':
                path=next(Path(args[args.index('--dest')+1]).glob('*.whl'))
                with zipfile.ZipFile(path,'a') as archive:archive.writestr('../escape','no')
            return result
        with self.assertRaisesRegex(ValueError,'경로'):
            locks.generate(self.checkout,self.request,'a'*40,self.reports,malicious)
        self.assertFalse((self.base/'escape').exists())


if __name__=='__main__':unittest.main(verbosity=2)
