"""Compile the actual Probe.cs together with a synthetic Win32 control host."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.name == 'nt', 'native Win32 controls require Windows')
class NativeReliabilityTests(unittest.TestCase):
    def test_full_ansi_richedit_source_and_hidden_root_restore(self):
        root = Path(__file__).resolve().parents[1]
        compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework/v4.0.30319/csc.exe'
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'reliability-host.exe'
            build = subprocess.run([str(compiler), '/nologo', '/platform:x86', '/main:ReliabilityHost',
                                    '/out:' + str(exe), str(root / 'Probe.cs'),
                                    str(root / 'native/tests/reliability_host.cs')], capture_output=True, text=True, timeout=60)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn('full-source 131000 verified', run.stdout)
            self.assertIn('hidden-root restore verified', run.stdout)
            self.assertIn('hidden retained script editor verified closed', run.stdout)
