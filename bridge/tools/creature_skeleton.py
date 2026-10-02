"""Give a creature its own skeleton + animation folder, copied from a vanilla creature, so its
animations can be changed without touching the vanilla creature (and other mods that use it).

    /usr/bin/python3 tools/creature_skeleton.py --source creatures\\mistergutsy --name SalvatoreGanacci \
        --replace-sound NPCRobotMrHandyAttackSaw=FXSwingMedium --hit-sound WPNPowerFistFire3D \
        --body build/salvmod/meshes/creatures/mistergutsy/salvatorebody.nif --out build/salvmod

Copies skeleton.nif and every .kf under meshes\\<source>\\ (incl. specialanims\\, idleanims\\) from the
game's BSAs into <out>\\meshes\\creatures\\<name>\\. KFs whose text keys change are rewritten with PyFFI;
all other files are copied byte-for-byte. Body-part NIFs listed with --body are copied in beside the
skeleton (the CREA NIFZ list is relative to the skeleton folder). Writes <name>.manifest.json with
source hashes and every text-key change. Then point the CREA's MODL at creatures\\<name>\\skeleton.nif.

Text-key edits:
  --replace-sound OLD=NEW   change "Sound: OLD" keys to "Sound: NEW" (NEW may be "-" to delete the key)
  --hit-sound SOUN          add "Sound: SOUN" at each "Hit" key of attack animations
  --speed GROUP=MULT        scale the timing of animations whose file name contains GROUP (e.g. attack=3)
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import time

time.clock = time.perf_counter                       # vendored PyFFI predates Python 3.8
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
for vendor in (ROOT.parent / 'vendor',):
    if vendor.exists():
        sys.path.insert(0, str(vendor))
from geck_mcp.esp.assets import bsa_extract, bsa_names  # noqa: E402

DATA = Path.home() / ('Library/Application Support/CrossOver/Bottles/Steam/drive_c/'
                      'Program Files (x86)/Steam/steamapps/common/Fallout New Vegas/Data')


def sha(b):
    return hashlib.sha256(b).hexdigest()


def edit_kf(raw, replace, hit_sound, speed):
    """Return (new_bytes or None if unchanged, [change notes])."""
    from pyffi.formats.nif import NifFormat as N
    data = N.Data()
    data.read(io.BytesIO(raw))
    notes = []
    for blk in data.blocks:
        if isinstance(blk, N.NiTextKeyExtraData):
            keys = [(k.time, k.value.decode('latin1')) for k in blk.text_keys]
            new = []
            for t, v in keys:
                if v.startswith('Sound: ') and v[7:] in replace:
                    target = replace[v[7:]]
                    notes.append('%.3f %r -> %r' % (t, v, None if target == '-' else 'Sound: ' + target))
                    if target != '-':
                        new.append((t, 'Sound: ' + target))
                    continue
                new.append((t, v))
            if hit_sound:
                hits = [t for t, v in new if v.lower() == 'hit']
                for t in hits:
                    new.append((t, 'Sound: ' + hit_sound))
                    notes.append('%.3f + Sound: %s' % (t, hit_sound))
            if speed != 1.0:
                new = [(t / speed, v) for t, v in new]
            if new != keys:
                new.sort(key=lambda kv: kv[0])
                blk.num_text_keys = len(new)
                blk.text_keys.update_size()
                for k, (t, v) in zip(blk.text_keys, new):
                    k.time = t
                    k.value = v.encode('latin1')
    if speed != 1.0:
        for blk in data.blocks:
            if isinstance(blk, N.NiControllerSequence):
                blk.frequency = blk.frequency * speed
                notes.append('sequence %s frequency x%.3f' % (blk.name.decode('latin1'), speed))
    if not notes:
        return None, []
    out = io.BytesIO()
    data.write(out)
    return out.getvalue(), notes


def check_roundtrip(raw):
    from pyffi.formats.nif import NifFormat as N
    data = N.Data()
    data.read(io.BytesIO(raw))
    out = io.BytesIO()
    data.write(out)
    return out.getvalue() == raw


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--source', required=True, help='vanilla folder under meshes, e.g. creatures\\mistergutsy')
    ap.add_argument('--name', required=True, help='new folder name under meshes\\creatures')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--replace-sound', action='append', default=[])
    ap.add_argument('--hit-sound')
    ap.add_argument('--speed', action='append', default=[])
    ap.add_argument('--body', action='append', default=[], type=Path)
    ap.add_argument('--data', type=Path, default=DATA)
    args = ap.parse_args()
    replace = dict(r.split('=', 1) for r in args.replace_sound)
    speeds = [(g.split('=', 1)[0].lower(), float(g.split('=', 1)[1])) for g in args.speed]
    prefix = ('meshes\\' + args.source.strip('\\') + '\\').lower()
    found = {}
    for bsa in sorted(args.data.glob('*.bsa')):
        for n in bsa_names(bsa):
            if n.lower().startswith(prefix) and (n.lower().endswith('.kf') or n.lower() == prefix + 'skeleton.nif'):
                found.setdefault(n.lower(), bsa)          # first archive wins, as the game resolves names
    if prefix + 'skeleton.nif' not in found:
        raise SystemExit('no skeleton.nif under ' + prefix)
    dest = args.out / 'meshes' / 'creatures' / args.name.lower()
    manifest = {'source': args.source, 'name': args.name, 'files': {}, 'textKeyChanges': {}}
    by_bsa = {}
    for n, bsa in found.items():
        by_bsa.setdefault(bsa, set()).add(n)
    for bsa, names in by_bsa.items():
        for n, raw in sorted(bsa_extract(bsa, names).items()):
            rel = n[len(prefix):]
            target = dest / rel.replace('\\', '/')
            target.parent.mkdir(parents=True, exist_ok=True)
            out, notes = raw, []
            if rel.endswith('.kf'):
                speed = 1.0
                for g, m in speeds:
                    if g in rel.split('\\')[-1]:
                        speed = m
                hit = args.hit_sound if 'attack' in rel and replace and any(
                    ('Sound: ' + k).encode() in raw for k in replace) else None
                edited, notes = edit_kf(raw, replace, hit, speed)
                if edited is not None:
                    if not check_roundtrip(raw):
                        notes.append('NOTE: PyFFI does not round-trip this file byte-for-byte')
                    out = edited
            target.write_bytes(out)
            manifest['files'][rel] = {'archive': bsa.name, 'sourceSha256': sha(raw), 'sha256': sha(out),
                                      'edited': bool(notes)}
            if notes:
                manifest['textKeyChanges'][rel] = notes
    for body in args.body:
        b = body.read_bytes()
        (dest / body.name.lower()).write_bytes(b)
        manifest['files'][body.name.lower()] = {'copiedFrom': str(body), 'sha256': sha(b), 'edited': False}
    (dest / (args.name.lower() + '.manifest.json')).write_text(json.dumps(manifest, indent=1))
    print(json.dumps({'dest': str(dest), 'files': len(manifest['files']),
                      'edited': sorted(manifest['textKeyChanges']), 'changes': manifest['textKeyChanges']}, indent=1))


if __name__ == '__main__':
    main()
