"""Compiled-script cache: GECK compiles, we keep the result.

The offline builder cannot compile GECK script source. The bridge loads the built plugin in GECK,
opens and saves each uncompiled script there (script.compile), and saves the plugin; this module
then lifts each script's compiled subrecords out of the GECK-saved plugin into
state/scripts/<project_id>.json, keyed by EditorID with the SHA-256 of the exact source text and the
script's FormID. Later builds reuse them byte for byte until the source changes.
"""
import json
import hashlib
import re
import struct
from pathlib import Path

from . import codec, generic


def cache_path(state_dir, project_id):
    return Path(state_dir) / 'scripts' / (project_id + '.json')


def load_cache(state_dir, project_id):
    path = cache_path(state_dir, project_id)
    return json.loads(path.read_text()) if path.exists() else {}


def normalized(text):
    """Only line endings are equivalent; whitespace and final newline remain significant."""
    return text.replace(b'\r\n', b'\n').replace(b'\r', b'\n')


def semantic_layout(compiled):
    # Format reference: TES5Edit Core/wbDefinitionsFNV.pas, wbSLSD/wbSCHRReq.
    # Independent reader: compare index/name/type, never the 19 unused SLSD bytes.
    out, pending = [], None
    for tag, raw in compiled:
        data = bytes.fromhex(raw)
        if tag == 'SLSD':
            if pending is not None or len(data) != 24:
                raise ValueError('Invalid SLSD variable data')
            pending = (struct.unpack_from('<I', data)[0], data[16])
        elif tag == 'SCVR':
            if pending is None:
                raise ValueError('SCVR without SLSD')
            out.append((data.rstrip(b'\0').decode('cp1252').casefold(), *pending))
            pending = None
    if pending is not None or len({v[0] for v in out}) != len(out) or len({v[1] for v in out}) != len(out):
        raise ValueError('Incomplete/duplicate variable layout')
    return sorted(out)


def verify_script(got, text, stype, formid, prior=None):
    if got is None or got['formId'] != formid or got['type'] != stype:
        raise ValueError('Missing script or wrong FormID/type')
    if normalized(got['text']) != normalized(text):
        raise ValueError('Saved full source differs')
    fields = {}
    for tag, raw in got['compiled']:
        fields.setdefault(tag, []).append(bytes.fromhex(raw))
    if any(len(fields.get(t, [])) != 1 for t in ('SCHR', 'SCDA', 'SCTX')):
        raise ValueError('Missing/duplicate SCHR/SCDA/SCTX')
    header = fields['SCHR'][0]
    if len(header) != 20 or not got['compiledSize'] or len(fields['SCDA'][0]) != got['compiledSize']:
        raise ValueError('SCDA size differs from SCHR or no bytecode')
    if struct.unpack_from('<I', header, 8)[0] != got['compiledSize'] or struct.unpack_from('<H', header, 16)[0] != stype:
        raise ValueError('SCHR compiled size/type differs')
    if normalized(fields['SCTX'][0]) != normalized(text):
        raise ValueError('Stored SCTX differs from source')
    layout = semantic_layout(got['compiled'])
    declarations = {}
    types = {'short': 1, 'long': 1, 'int': 1, 'float': 0, 'ref': 0, 'reference': 0,
             'string_var': 2, 'array_var': 3}
    for line in text.decode('cp1252').splitlines():
        match = re.fullmatch(r'\s*(short|long|int|float|ref|reference|string_var|array_var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*',
                             line.split(';', 1)[0], re.I)
        if match:
            declarations[match[2].casefold()] = types[match[1].lower()]
    if {name: kind for name, _, kind in layout} != declarations:
        raise ValueError('Semantic variable names/types differ from source')
    if struct.unpack_from('<I', header, 12)[0] != len(layout):
        raise ValueError('SCHR variable count differs')
    refs = [(tag, struct.unpack('<I', data)[0]) for tag in ('SCRO', 'SCRV') for data in fields.get(tag, [])]
    if struct.unpack_from('<I', header, 4)[0] != len(refs):
        raise ValueError('SCHR reference count differs')
    indices = {v[1] for v in layout}
    if any(value not in indices for tag, value in refs if tag == 'SCRV'):
        raise ValueError('SCRV references unknown local variable')
    if prior and semantic_layout(prior['compiled']) != layout:
        raise ValueError('Existing semantic variable indices changed')
    return {'layout': layout, 'references': refs,
            'bytecodeSha256': hashlib.sha256(fields['SCDA'][0]).hexdigest()}


def update_from_plugin(state_dir, spec, base_dir, saved_plugin_bytes, receipt_formids, provenance=None):
    """Adopt compiled scripts from a GECK-saved plugin. Returns {edid: status}."""
    cache = load_cache(state_dir, spec['project_id'])
    found = generic.extract_compiled(codec.parse(saved_plugin_bytes))
    report = {}
    for edid, rec_spec in spec.get('records', {}).items():
        if rec_spec.get('type') != 'SCPT':
            continue
        stype = generic.SCRIPT_TYPES[rec_spec.get('script_type', 'object')]
        text = generic.script_text(base_dir, rec_spec, edid, 'records.%s' % edid)
        got = found.get(edid)
        try:
            proof = verify_script(got, text, stype, receipt_formids.get(edid))
            if not provenance or edid not in provenance.get('scripts', {}):
                raise ValueError('No observed compile/saved-plugin provenance')
            if provenance.get('savedSha256') != hashlib.sha256(saved_plugin_bytes).hexdigest():
                raise ValueError('Saved-plugin provenance differs')
            expected = provenance['scripts'][edid]
            if any(json.dumps(expected.get(key), sort_keys=True) != json.dumps(value, sort_keys=True)
                   for key, value in proof.items()):
                raise ValueError('Observed compile proof differs from saved bytecode/layout/references')
        except ValueError as error:
            report[edid] = str(error)
            continue
        cache[edid] = {'sourceSha256': generic.source_sha(text, stype), 'formId': got['formId'],
                       'compiledSize': got['compiledSize'], 'compiled': got['compiled'],
                       'verification': proof, 'provenance': provenance}
        report[edid] = 'cached (%d bytes)' % got['compiledSize']
    if any(not status.startswith('cached (') for status in report.values()):
        return report  # whole batch is atomic; preserve the last-good cache on late failure
    from ..authoring import atomic_write
    path = cache_path(state_dir, spec['project_id'])
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, (json.dumps(cache, indent=1, sort_keys=True) + '\n').encode())
    return report
