"""Write an invisible NIF (a lone NiNode + BSX 0) for sound emitters and other script-only objects:
    /usr/bin/python3 tools/empty_nif.py OUT.nif [RootName]
An editor marker such as MarkerX.nif on an activator shows in game as a red X; this shows nothing."""
import sys
import time
from pathlib import Path

time.clock = time.perf_counter
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent / 'vendor'))
from pyffi.formats.nif import NifFormat as N  # noqa: E402

out = Path(sys.argv[1])
data = N.Data(version=0x14020007, user_version=11, user_version_2=34)
data.header.endian_type = 1
root = N.BSFadeNode()
root.name = (sys.argv[2] if len(sys.argv) > 2 else 'EmptyEmitter').encode()
root.flags = 14
bsx = N.BSXFlags()
bsx.name = b'BSX'
bsx.integer_data = 0
root.add_extra_data(bsx)
data.roots = [root]
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, 'wb') as stream:
    data.write(stream)
check = N.Data()
with open(out, 'rb') as stream:
    check.read(stream)
print(out, out.stat().st_size, 'bytes', [type(b).__name__ for b in check.blocks])
