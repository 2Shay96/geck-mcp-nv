"""Startup source fingerprints differ from current on-disk installation identity."""
import hashlib
import os
from pathlib import Path
import sys
from . import __version__
ROOT = Path(__file__).resolve().parents[1]
STARTUP = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
           for p in (ROOT / 'geck_mcp').glob('*.py')}

def component_identity(project):
    current = {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() if (ROOT/name).exists() else None
               for name in STARTUP}
    return {'version':__version__, 'pythonPid':os.getpid(), 'pythonExecutable':sys.executable,
            'sourceRoot':str(ROOT), 'startupSourceSha256':STARTUP, 'sourceFilesUnchanged':current==STARTUP,
            'configuredHelper':str(project.helper), 'configuredHelperSha256':
                hashlib.sha256(project.helper.read_bytes()).hexdigest() if project.helper.exists() else None,
            'helperNote':'Configured file is not running-binary proof; inspect bridgeTransport.helperIdentity.'}
