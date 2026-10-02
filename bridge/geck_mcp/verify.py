"""Tier-3 checks: compare what GECK shows against a build receipt.

`cell.refs` returns Cell View's reference list as rows of column texts. GECK's
column layout is discovered at runtime, so matching is by value: a row belongs to
a reference when one of its cells parses as that reference's FormID (hex).
"""


def _hex(cell):
    cell = (cell or '').strip()
    if not 3 <= len(cell) <= 8:
        return None
    try:
        return int(cell, 16)
    except ValueError:
        return None


def match_cell_references(receipt, cell_id, cell_refs):
    """Return {'ok', 'expected', 'shown', 'matched', 'missing', 'unexpected', 'baseMismatches', 'columns'}."""
    expected = {int(r['formId'], 16): r for r in receipt['references'].get(cell_id, [])}
    rows = cell_refs.get('rows', [])
    columns = cell_refs.get('columns', [])
    matched, unexpected, base_mismatch = {}, [], []
    for row in rows:
        hits = [v for v in (_hex(c) for c in row) if v in expected]
        if len(set(hits)) == 1:
            form = hits[0]
            if form in matched:
                unexpected.append({'row': row, 'reason': 'duplicate row for %08X' % form})
                continue
            matched[form] = row
            spec_base = expected[form]['baseSpec']
            if spec_base.startswith('@'):
                name = spec_base[1:].lower()
                # GECK appends ' *' to names of records from the active plugin.
                texts = [c.strip().rstrip('*').strip().lower() for c in row]
                base_hex = int(expected[form]['base'], 16)
                # A reference with its own EditorID is listed under that name instead of the base's.
                ref_name = (expected[form].get('editorId') or '').lower()
                if name not in texts and base_hex not in [_hex(c) for c in row] and \
                        not (ref_name and ref_name in texts):
                    base_mismatch.append({'formId': '%08X' % form, 'expectedBase': spec_base, 'row': row})
        else:
            unexpected.append({'row': row, 'reason': 'no single receipt FormID in row'})
    missing = ['%08X' % f for f in expected if f not in matched]
    return {'ok': not missing and not unexpected and not base_mismatch and len(rows) == len(expected),
            'expected': len(expected), 'shown': len(rows), 'matched': len(matched),
            'missing': missing, 'unexpected': unexpected, 'baseMismatches': base_mismatch,
            'columns': columns}
