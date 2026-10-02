"""Record-level comparison of two plugins (used for rebuild checks and the GECK oracle diff).

Records are matched by (type, FormID). Differences are reported per subrecord, so
"GECK added XCLW" and "DATA changed" are distinguishable. Record order, group
stamps and version-control fields can be ignored, since GECK rewrites them freely.
"""
from . import codec


def record_map(plugin):
    out = {}
    for rec, path in plugin.records():
        key = (rec.type, rec.form_id)
        out[key] = (rec, tuple((g.group_type, g.label) for g in path))
    return out


def subrecord_diff(a, b):
    """Compare subrecord lists by tag occurrence (tag, n-th occurrence)."""
    def keyed(rec):
        seen, rows = {}, {}
        for sub in rec.subrecords:
            n = seen.get(sub.tag, 0)
            seen[sub.tag] = n + 1
            rows[(sub.tag, n)] = sub.data
        return rows
    left, right = keyed(a), keyed(b)
    changes = []
    for key in sorted(set(left) | set(right), key=lambda k: (k[0], k[1])):
        tag = key[0] if key[1] == 0 else '%s#%d' % key
        if key not in right:
            changes.append({'subrecord': tag, 'change': 'only_in_a', 'a': left[key].hex()})
        elif key not in left:
            changes.append({'subrecord': tag, 'change': 'only_in_b', 'b': right[key].hex()})
        elif left[key] != right[key]:
            changes.append({'subrecord': tag, 'change': 'changed', 'a': left[key].hex(), 'b': right[key].hex()})
    order_a = [s.tag for s in a.subrecords]
    order_b = [s.tag for s in b.subrecords]
    if not changes and order_a != order_b:
        changes.append({'subrecord': '*', 'change': 'order', 'a': order_a, 'b': order_b})
    return changes


def diff(a_bytes, b_bytes, ignore_vc=True):
    """Return a list of differences between two plugins (empty list = equivalent)."""
    a, b = codec.parse(a_bytes), codec.parse(b_bytes)
    ma, mb = record_map(a), record_map(b)
    out = []
    for key in sorted(set(ma) | set(mb), key=lambda k: (k[0] != 'TES4', k[0], k[1])):
        label = '%s %08X' % key
        if key not in mb:
            out.append({'record': label, 'change': 'only_in_a', 'editorId': ma[key][0].editor_id})
            continue
        if key not in ma:
            out.append({'record': label, 'change': 'only_in_b', 'editorId': mb[key][0].editor_id})
            continue
        (ra, pa), (rb, pb) = ma[key], mb[key]
        entry = {'record': label, 'editorId': ra.editor_id, 'changes': []}
        if pa != pb:
            entry['changes'].append({'subrecord': '<group>', 'change': 'moved',
                                     'a': [(t, l.hex()) for t, l in pa], 'b': [(t, l.hex()) for t, l in pb]})
        if ra.flags != rb.flags:
            entry['changes'].append({'subrecord': '<flags>', 'change': 'changed',
                                     'a': '%08X' % ra.flags, 'b': '%08X' % rb.flags})
        if not ignore_vc and (ra.vc1, ra.vc2) != (rb.vc1, rb.vc2):
            entry['changes'].append({'subrecord': '<vc>', 'change': 'changed',
                                     'a': [ra.vc1, ra.vc2], 'b': [rb.vc1, rb.vc2]})
        entry['changes'] += subrecord_diff(ra, rb)
        if entry['changes']:
            out.append(entry)
    return out
