"""Compiled-script cache: GECK compiles, we keep the result.

The offline builder cannot compile GECK script source. The bridge loads the built plugin in GECK,
opens and saves each uncompiled script there (script.compile), and saves the plugin; this module
then lifts each script's compiled subrecords out of the GECK-saved plugin into
state/scripts/<project_id>.json, keyed by EditorID with the SHA-256 of the exact source text and the
script's FormID. Later builds reuse them byte for byte until the source changes.
"""
import json
from pathlib import Path

from . import codec, generic


def cache_path(state_dir, project_id):
    return Path(state_dir) / 'scripts' / (project_id + '.json')


def load_cache(state_dir, project_id):
    path = cache_path(state_dir, project_id)
    return json.loads(path.read_text()) if path.exists() else {}


def update_from_plugin(state_dir, spec, base_dir, saved_plugin_bytes, receipt_formids):
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
        if got is None:
            report[edid] = 'missing from saved plugin'
            continue
        if got['formId'] != receipt_formids.get(edid):
            report[edid] = 'FormID changed (%s vs %s)' % (got['formId'], receipt_formids.get(edid))
            continue
        if got['text'].replace(b'\r\n', b'\n').strip() != text.replace(b'\r\n', b'\n').strip():
            report[edid] = 'saved text differs from source (edited in GECK?)'
            continue
        if not got['compiledSize']:
            report[edid] = 'not compiled'
            continue
        cache[edid] = {'sourceSha256': generic.source_sha(text, stype), 'formId': got['formId'],
                       'compiledSize': got['compiledSize'], 'compiled': got['compiled']}
        report[edid] = 'cached (%d bytes)' % got['compiledSize']
    path = cache_path(state_dir, spec['project_id'])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=1, sort_keys=True) + '\n')
    return report
