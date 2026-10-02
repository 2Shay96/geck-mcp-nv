"""Helper command lines for the three launchers (crossover tested live; wine/native only here)."""
from pathlib import Path
import tempfile
import unittest

from geck_mcp.config import Project


def project(**extra):
    root = Path(tempfile.mkdtemp())
    base = dict(project_id='t', game_root=root / 'game', plugin='T.esp', state_dir=root / 'state',
                helper=root / 'Probe.Mcp.exe', spec=root / 't.spec.json')
    base.update(extra)
    return Project(**base), root


class LauncherTests(unittest.TestCase):
    def test_crossover_command_and_env(self):
        p, root = project(launcher='crossover', wine=Path('/cx/wine'), bottle=Path('/b/Steam'))
        self.assertEqual(p.helper_command('status'),
                         ['/cx/wine', '--bottle', 'Steam', '--no-update', '--cx-app',
                          'Z:' + str(root / 'Probe.Mcp.exe').replace('/', '\\'), 'status'])
        self.assertEqual(p.helper_env(), {'WINEPREFIX': '/b/Steam'})
        self.assertEqual(p.lock_root, Path('/b/Steam'))

    def test_wine_command_uses_prefix(self):
        p, root = project(launcher='wine', wine=Path('/proton/bin/wine'), bottle=Path('/pfx'))
        self.assertEqual(p.helper_command('inspect', 5)[0], '/proton/bin/wine')
        self.assertTrue(p.helper_command('inspect', 5)[1].startswith('Z:\\'))
        self.assertEqual(p.helper_command('inspect', 5)[2:], ['inspect', '5'])
        self.assertEqual(p.helper_env(), {'WINEPREFIX': '/pfx'})

    def test_native_runs_helper_directly(self):
        p, root = project(launcher='native')
        self.assertEqual(p.helper_command('serve'), [str(root / 'Probe.Mcp.exe'), 'serve'])
        self.assertEqual(p.helper_env(), {})
        self.assertEqual(p.lock_root, root / 'game')

    def test_wine_launchers_need_wine_and_bottle(self):
        with self.assertRaises(ValueError):
            project(launcher='wine')
        with self.assertRaises(ValueError):
            project(launcher='crossover', wine=Path('/cx/wine'))


if __name__ == '__main__':
    unittest.main()
