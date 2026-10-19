"""Exercise source-download boundaries against a disposable Git repository."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location(
    'package_release', Path(__file__).resolve().parents[2] / 'tools/package_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Synthetic Test')
        self.git('config', 'user.email', 'test@example.invalid')
        for name, data in {
            'README.md': b'# Test (v0.3.0)',
            'LICENSE': b'Synthetic licence',
            'bridge/pyproject.toml': b'[project]\nversion="0.3.0"\n',
            'bridge/geck_mcp/__init__.py': b'__version__="0.3.0"\n',
            'bridge/native/runtime/companion.c': b'/* synthetic source */',
            'bridge/Probe.Mcp.exe': b'fake exe',
            'bridge/native/generated.dll': b'fake dll',
            'bridge/tests/fixtures/test.esp': b'fake plugin',
            'bridge/tests/test_build.py': b'fixture dependent',
            'bridge/projects/private.json': b'private profile',
            'bridge/projects/example-windows.json': b'{}',
            'bridge/state/raw.json': b'private evidence',
            'HANDOFF.md': b'coordination',
        }.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.git('add', '.')
        self.git('commit', '-qm', 'Synthetic source')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.DEVNULL)

    def test_archive_uses_committed_source_and_omits_private_and_binary_files(self):
        (self.repo / 'README.md').write_text('dirty working edit')
        (self.repo / 'bridge/untracked.py').write_text('not committed')
        output = self.root / 'one.zip'
        manifest = release.package(self.repo, 'HEAD', output)
        with zipfile.ZipFile(output) as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(z.read(release.PREFIX + 'README.md'), b'# Test (v0.3.0)')
            self.assertEqual(set(z.namelist()), {release.PREFIX + p for p in (
                'README.md', 'LICENSE', 'bridge/pyproject.toml', 'bridge/geck_mcp/__init__.py',
                'bridge/native/runtime/companion.c', 'bridge/projects/example-windows.json')})
        self.assertEqual(manifest, json.loads(output.with_suffix('.json').read_text()))
        self.assertEqual(manifest['sourceCommit'], self.git('rev-parse', 'HEAD').decode().strip())

    def test_reproducible_and_refuses_overwrite(self):
        first, second = self.root / 'one.zip', self.root / 'two.zip'
        release.package(self.repo, 'HEAD', first)
        release.package(self.repo, 'HEAD', second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with self.assertRaises(FileExistsError):
            release.package(self.repo, 'HEAD', first)

    def test_mismatched_versions_refused_before_output(self):
        (self.repo / 'bridge/geck_mcp/__init__.py').write_text('__version__="9.9.9"\n')
        self.git('add', 'bridge/geck_mcp/__init__.py')
        self.git('commit', '-qm', 'Synthetic mismatch')
        output = self.root / 'bad.zip'
        with self.assertRaisesRegex(ValueError, 'version markers'):
            release.package(self.repo, 'HEAD', output)
        self.assertFalse(output.exists())

    def test_unsafe_paths_refused(self):
        for name in ('../outside.py', '/outside.py', 'bridge/../../outside.py',
                     'bridge\\outside.py', 'bridge/file:stream.py'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                release.included(name)
