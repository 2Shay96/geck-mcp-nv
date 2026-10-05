"""tools/creature_skeleton.py: where the game Data folder comes from (fix 8). Runs without PyFFI."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import creature_skeleton as cs  # noqa: E402


class DataFolder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def profile(self):
        path = self.root / 'mod.json'
        path.write_text(json.dumps({'project_id': 'mod', 'launcher': 'native', 'game_root': 'game',
                                    'plugin': 'Mod.esp', 'state_dir': 'state', 'helper': 'helper.exe',
                                    'spec': 'mod.spec.json'}))
        return path

    def test_explicit_data_wins(self):
        self.assertEqual(cs.data_folder(self.root / 'Data', self.profile()), self.root / 'Data')

    def test_project_profile_game_root(self):
        self.assertEqual(cs.data_folder(None, self.profile()), (self.root / 'game').resolve() / 'Data')

    def test_fnv_data_then_os_default(self):
        with mock.patch.dict(os.environ, {'FNV_DATA': str(self.root / 'EnvData')}):
            self.assertEqual(cs.data_folder(), self.root / 'EnvData')
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('FNV_DATA', None)
            self.assertEqual(cs.data_folder(), cs.default_data())
            self.assertEqual(cs.data_folder().name, 'Data')

    def test_missing_data_folder_is_a_clear_error(self):
        done = subprocess.run([sys.executable, str(ROOT / 'tools' / 'creature_skeleton.py'), '--source',
                               'creatures\\mistergutsy', '--name', 'Test', '--out', str(self.root / 'out'),
                               '--data', str(self.root / 'NoData')], capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn('Data folder not found', done.stderr)
        self.assertFalse((self.root / 'out').exists())


if __name__ == '__main__':
    unittest.main()
