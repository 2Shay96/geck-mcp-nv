"""Subrecord-level diff of two plugins: python3 tools/esp_diff.py A.esp B.esp"""
import sys
sys.path.insert(0, '.')
from geck_mcp.esp import codec
def load(p):
    out = {}
    for rec, _ in codec.iter_records(open(p, 'rb').read()):
        out[(rec.type, rec.form_id)] = rec
    return out
a, b = load(sys.argv[1]), load(sys.argv[2])
for key in sorted(set(a) | set(b)):
    ra, rb = a.get(key), b.get(key)
    if not ra or not rb:
        print('only in', 'A' if ra else 'B', key[0], '%08X' % key[1]); continue
    sa = [(s.tag, s.data) for s in ra.subrecords]; sb = [(s.tag, s.data) for s in rb.subrecords]
    hdr = (ra.flags, ra.form_version) != (rb.flags, rb.form_version)
    if sa != sb or hdr:
        print('==', key[0], '%08X' % key[1], ra.editor_id, 'hdr A', hex(ra.flags), ra.form_version, 'B', hex(rb.flags), rb.form_version)
        print('   A tags', [t for t, _ in sa]); print('   B tags', [t for t, _ in sb])
        da = dict(); db = dict()
        for t, d in sa: da.setdefault(t, []).append(d)
        for t, d in sb: db.setdefault(t, []).append(d)
        for t in sorted(set(da) | set(db)):
            if da.get(t) != db.get(t):
                print('   ', t, 'A', [x.hex()[:120] for x in da.get(t, [])], '\n     B', [x.hex()[:120] for x in db.get(t, [])])
