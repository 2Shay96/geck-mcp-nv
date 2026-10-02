"""Read-only research on a master file: script function usage, creature summaries, record dumps.

    python3 tools/esm_research.py funcs  FalloutNV.esm AddItemHealthPercent OnDrop ...
    python3 tools/esm_research.py creatures FalloutNV.esm
    python3 tools/esm_research.py dump FalloutNV.esm OUT.json EDID [EDID ...]
    python3 tools/esm_research.py types FalloutNV.esm OUT.json CREA WEAP ...   (all records of types)

Standard library only (uses geck_mcp.esp.codec). Script evidence comes from the SCTX source text
Bethesda shipped inside FalloutNV.esm, so a function that appears there is known to compile and run
in vanilla FNV.
"""
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from geck_mcp.esp import codec  # noqa: E402

from esm_index import default_data  # noqa: E402

DATA = default_data()


def load(name):
    path = Path(name)
    if not path.exists():
        path = DATA / name
    return path.read_bytes()


def text(sub):
    return sub.rstrip(b'\0').decode('cp1252', 'replace') if sub else None


def funcs(data, names):
    hits = {n: [] for n in names}
    patterns = {n: re.compile(r'(?i)(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])' % re.escape(n)) for n in names}
    for rec, _ in codec.iter_records(data, types={'SCPT'}):
        src = text(rec.get('SCTX'))
        if not src:
            continue
        for n, pat in patterns.items():
            for line in src.splitlines():
                if pat.search(line) and not line.strip().startswith(';'):
                    hits[n].append((rec.editor_id, line.strip()[:140]))
    for n in names:
        rows = hits[n]
        scripts = sorted({r[0] for r in rows})
        print('%-24s %4d lines in %3d scripts' % (n, len(rows), len(scripts)))
        for script, line in rows[:4]:
            print('      %-32s %s' % (script, line))


CREATURE_TYPES = ['Animal', 'Mutated Animal', 'Mutated Insect', 'Abomination', 'Super Mutant',
                  'Feral Ghoul', 'Robot', 'Giant']


def creatures(data):
    for rec, _ in codec.iter_records(data, types={'CREA'}):
        d = rec.get('DATA') or b''
        ctype = CREATURE_TYPES[d[0]] if d and d[0] < len(CREATURE_TYPES) else '?'
        acbs = rec.get('ACBS') or b''
        speed = struct.unpack_from('<H', acbs, 16)[0] if len(acbs) >= 18 else None
        health = struct.unpack_from('<h', d, 4)[0] if len(d) >= 6 else None
        nifz = rec.get('NIFZ')
        parts = [p.decode('cp1252', 'replace') for p in nifz.split(b'\0') if p] if nifz else []
        print('%-34s %08X %-14s hp=%-5s spd=%-4s %s | %s | %s' % (
            rec.editor_id, rec.form_id, ctype, health, speed, text(rec.get('FULL')),
            text(rec.get('MODL')), ';'.join(parts)[:120]))


def dump_record(rec, path):
    subs = []
    for s in rec.subrecords:
        entry = {'tag': s.tag, 'size': len(s.data), 'hex': s.data.hex()}
        if s.tag in ('EDID', 'FULL', 'MODL', 'ICON', 'MICO', 'SCTX', 'NIFZ', 'DESC', 'FNAM', 'ANAM', 'NAM0', 'NAM1'):
            try:
                entry['text'] = s.data.rstrip(b'\0').decode('cp1252')
            except UnicodeDecodeError:
                pass
        subs.append(entry)
    return {'type': rec.type, 'formId': '%08X' % rec.form_id, 'flags': rec.flags, 'vc1': rec.vc1,
            'formVersion': rec.form_version, 'vc2': rec.vc2, 'groups': path, 'subrecords': subs}


def dump(data, out, edids=None, types=None):
    wanted = set(edids or [])
    found = {}
    for rec, groups in codec.iter_records(data, types=set(types) if types else None):
        try:
            edid = rec.editor_id
        except Exception:
            edid = None
        if types or edid in wanted:
            key = edid or '%s:%08X' % (rec.type, rec.form_id)
            found[key] = dump_record(rec, [[label.hex(), gtype] for label, gtype in groups])
    Path(out).write_text(json.dumps(found, indent=1))
    print('dumped', len(found), 'records to', out, '| missing:', sorted(wanted - set(found)))


if __name__ == '__main__':
    cmd, master = sys.argv[1], sys.argv[2]
    data = load(master)
    if cmd == 'funcs':
        funcs(data, sys.argv[3:])
    elif cmd == 'creatures':
        creatures(data)
    elif cmd == 'dump':
        dump(data, sys.argv[3], edids=sys.argv[4:])
    elif cmd == 'types':
        dump(data, sys.argv[3], types=sys.argv[4:])
    elif cmd == 'having':      # having OUT.json TYPE TAG [LIMIT]: first records of TYPE that carry TAG
        out, rtype, tag = sys.argv[3], sys.argv[4], sys.argv[5]
        limit = int(sys.argv[6]) if len(sys.argv) > 6 else 10
        found = {}
        for rec, groups in codec.iter_records(data, types={rtype}):
            if rec.get(tag) is not None:
                found[rec.editor_id or '%08X' % rec.form_id] = dump_record(rec, [[l.hex(), t] for l, t in groups])
                if len(found) >= limit:
                    break
        Path(out).write_text(json.dumps(found, indent=1))
        print('having', rtype, tag, len(found))
    else:
        raise SystemExit(__doc__)
