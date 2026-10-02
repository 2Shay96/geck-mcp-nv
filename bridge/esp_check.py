"""Read-only, strict FNV STAT/EDID/MODL verifier; never writes plugin bytes.
Format: https://tes5edit.github.io/fopdoc/FalloutNV/Records.html
        https://tes5edit.github.io/fopdoc/FalloutNV/Groups.html
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import time

MAX_BYTES = 32 * 1024 * 1024

def file_snapshot(path):
    path = Path(path).resolve(strict=True)
    stat = path.stat()
    if stat.st_size > MAX_BYTES:
        raise ValueError('plugin exceeds narrow verifier size limit')
    data = path.read_bytes()
    after = path.stat()
    if (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('plugin changed during read')
    return {'path': str(path), 'size': len(data), 'mtimeNs': after.st_mtime_ns,
            'sha256': hashlib.sha256(data).hexdigest()}, data

def cstring(data):
    if not data or data[-1:] != b'\0' or b'\0' in data[:-1]:
        raise ValueError('invalid terminated string')
    return data[:-1].decode('cp1252')

def subrecords(data):
    pos = 0
    while pos < len(data):
        if pos + 6 > len(data):
            raise ValueError('truncated subrecord header')
        tag, size = struct.unpack_from('<4sH', data, pos)
        pos += 6
        if tag == b'XXXX':
            raise ValueError('extended subrecords unsupported by narrow verifier')
        if pos + size > len(data):
            raise ValueError('subrecord exceeds record boundary')
        yield tag, data[pos:pos + size]
        pos += size

def read_model(data, editor_id):
    if data[:4] != b'TES4':
        raise ValueError('missing TES4 header')
    matches = []
    def records(start, end, depth=0):
        if depth > 12:
            raise ValueError('group nesting limit exceeded')
        pos = start
        while pos < end:
            if pos + 24 > end:
                raise ValueError('truncated record/group header at %d' % pos)
            tag, size = struct.unpack_from('<4sI', data, pos)
            if tag == b'GRUP':
                stop = pos + size
                if size < 24 or stop > end:
                    raise ValueError('invalid group boundary at %d' % pos)
                records(pos + 24, stop, depth + 1)
            else:
                stop = pos + 24 + size
                if stop > end:
                    raise ValueError('record %r at %d exceeds enclosing boundary %d (ends %d)' % (tag, pos, end, stop))
                if tag == b'STAT':
                    flags, form_id = struct.unpack_from('<II', data, pos + 8)
                    if flags & 0x40000:
                        raise ValueError('compressed STAT unsupported by narrow verifier')
                    fields = list(subrecords(data[pos + 24:stop]))
                    ids = [cstring(value) for key, value in fields if key == b'EDID']
                    if len(ids) != 1:
                        raise ValueError('STAT requires exactly one EDID')
                    if ids[0] == editor_id:
                        if flags & 0x20:
                            raise ValueError('target record is deleted')
                        models = [cstring(value) for key, value in fields if key == b'MODL']
                        if len(models) != 1:
                            raise ValueError('target requires exactly one MODL')
                        matches.append({'editorId': editor_id, 'formId': '%08X' % form_id,
                                        'recordType': 'STAT', 'modelPath': models[0], 'offset': pos})
            pos = stop
    records(0, len(data))
    if len(matches) != 1:
        raise ValueError('expected one matching STAT; found %d' % len(matches))
    return matches[0]

def read_cell_reference(data, cell_editor_id, base_form_id):
    """Return one live REFR to base_form_id scoped beneath the named CELL."""
    if data[:4] != b'TES4':
        raise ValueError('missing TES4 header')
    records_found = []
    def records(start, end, ancestors=(), depth=0):
        if depth > 12:
            raise ValueError('group nesting limit exceeded')
        pos = start
        while pos < end:
            if pos + 24 > end:
                raise ValueError('truncated record/group header at %d' % pos)
            tag, size = struct.unpack_from('<4sI', data, pos)
            if tag == b'GRUP':
                stop = pos + size
                if size < 24 or stop > end:
                    raise ValueError('invalid group boundary at %d' % pos)
                label, group_type = struct.unpack_from('<II', data, pos + 8)
                records(pos + 24, stop, ancestors + ((group_type, label),), depth + 1)
            else:
                stop = pos + 24 + size
                if stop > end:
                    raise ValueError('record exceeds enclosing boundary at %d' % pos)
                flags, form_id = struct.unpack_from('<II', data, pos + 8)
                if flags & 0x40000:
                    raise ValueError('compressed record unsupported by narrow verifier')
                records_found.append((tag, pos, form_id, flags,
                                      list(subrecords(data[pos + 24:stop])), ancestors))
            pos = stop
    records(0, len(data))
    cells = []
    for tag, pos, form_id, flags, fields, ancestors in records_found:
        if tag != b'CELL':
            continue
        ids = [cstring(value) for key, value in fields if key == b'EDID']
        if ids == [cell_editor_id] and not flags & 0x20:
            cells.append((pos, form_id))
    if len(cells) != 1:
        raise ValueError('expected one matching CELL; found %d' % len(cells))
    cell_offset, cell_form_id = cells[0]
    refs = []
    for tag, pos, form_id, flags, fields, ancestors in records_found:
        if tag != b'REFR' or flags & 0x20 or (6, cell_form_id) not in ancestors:
            continue
        names = [struct.unpack('<I', value)[0] for key, value in fields
                 if key == b'NAME' and len(value) == 4]
        if names == [base_form_id]:
            placements = [struct.unpack('<6f', value) for key, value in fields
                          if key == b'DATA' and len(value) == 24]
            if len(placements) != 1:
                raise ValueError('target REFR requires exactly one 24-byte DATA')
            refs.append({'formId': '%08X' % form_id, 'recordType': 'REFR',
                         'baseFormId': '%08X' % base_form_id, 'offset': pos,
                         'position': dict(zip(('x', 'y', 'z'), placements[0][:3])),
                         'rotation': dict(zip(('x', 'y', 'z'), placements[0][3:]))})
    if len(refs) != 1:
        raise ValueError('expected one matching REFR in target CELL; found %d' % len(refs))
    return {'cellEditorId': cell_editor_id, 'cellFormId': '%08X' % cell_form_id,
            'cellOffset': cell_offset, 'reference': refs[0]}

def inspect(path, editor_id):
    snapshot, data = file_snapshot(path)
    return {'file': snapshot, 'record': read_model(data, editor_id)}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plugin')
    parser.add_argument('editor_id')
    parser.add_argument('--expect-model')
    args = parser.parse_args()
    start = time.monotonic()
    result = {'ok': False, 'operation': 'esp.verify', 'target': args.plugin,
              'before': None, 'after': None, 'elapsedMs': 0, 'error': None}
    try:
        snapshot, data = file_snapshot(args.plugin)
        result['before'] = snapshot
        result['after'] = read_model(data, args.editor_id)
        if args.expect_model is not None and result['after']['modelPath'] != args.expect_model:
            raise ValueError('persisted model path differs from expected value')
        result['ok'] = True
    except (OSError, ValueError, struct.error) as error:
        result['error'] = str(error)
    result['elapsedMs'] = round((time.monotonic() - start) * 1000)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['ok'] else 1)
