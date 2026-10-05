"""Generic record building: clone a vanilla template record and apply field operations, or
assemble a record from explicit subrecords. Also builds SCPT records from script source files.

Spec form (inside "records"):

  "SalvatoreCreature": {
    "type": "CREA",
    "template": "REPCONMrHandy",            # state/templates/FalloutNV.esm/REPCONMrHandy.json
    "fields": [
      {"tag": "FULL", "text": "Salvatore"},
      {"tag": "NIFZ", "texts": ["salvatorebody.nif"]},
      {"tag": "SCRI", "form": "@SalvatoreCreatureScript"},
      {"tag": "CNTO", "remove": true},
      {"tag": "DATA", "patch": [[4, "<h", 1000]]},
      {"tag": "PKID", "form": "@SalvatoreFollowPackage", "after": "AIDT"},
      {"insert": [{"tag": "CSDT", "u32": 11}, {"tag": "CSDI", "form": "@SalvMusic"},
                  {"tag": "CSDC", "u8": 100}], "after": "NAM5"}
    ]
  }

Operations on a tag: a value ("text", "texts", "form", "forms", "hex", "u8", "u16", "u32",
"s32", "float", "pack"+"values", "empty") replaces the first subrecord with that tag, or is
inserted after the last subrecord tagged "after" (default: at the end) when absent.
"append": true always inserts. "remove": true deletes every subrecord with the tag. "patch"
edits bytes of the existing subrecord in place: [[offset, struct_format, value], ...].
"@EditorID" values anywhere are resolved to FormIDs (own records or indexed masters).

Templates are FNVEdit-style dumps written by tools/esm_research.py ("dump"); their FormIDs are
master-relative, so the template's master must be the plugin's first master. They are looked up in
the project's <state_dir>/templates first, then in this repo's state/templates (template_dirs()).

Scripts: {"type": "SCPT", "source": "scripts/X.gek", "script_type": "object"|"quest"|"effect"}.
The source text is stored in SCTX (CRLF). Compiled data (SCHR/SCDA/SLSD/SCVR/SCRO/SCRV) comes
from the script cache (compiled by GECK through the bridge, see scripts.py); without a cache hit
the script is emitted uncompiled (SCHR with zero counts) so GECK can compile it.
"""
import hashlib
import json
from pathlib import Path
import struct

from .codec import Subrecord, zstring
from .formids import FormIdError
from .records import SpecError, check_edid, record

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT / 'state' / 'templates'
GENERIC_TYPES = {'CREA', 'WEAP', 'ACTI', 'SOUN', 'QUST', 'PACK', 'MESG', 'FLST', 'MISC', 'GLOB', 'ALCH',
                 'FACT', 'CONT', 'SPEL', 'MGEF', 'ENCH', 'EXPL', 'PROJ', 'SCPT', 'VTYP'}
SCRIPT_TYPES = {'object': 0, 'quest': 1, 'effect': 0x100}
VALUE_KEYS = ('text', 'texts', 'form', 'forms', 'hex', 'u8', 'u16', 'u32', 's32', 'float', 'pack', 'empty')
COMPILED_TAGS = ('SCHR', 'SCDA', 'SCTX', 'SLSD', 'SCVR', 'SCRO', 'SCRV')


def template_dirs(state_dir=None):
    """Template folders in lookup order: <state_dir>/templates first, then the code root's state/templates."""
    dirs = []
    for folder in ([Path(state_dir) / 'templates'] if state_dir else []) + [TEMPLATE_DIR]:
        if all(folder.resolve() != d.resolve() for d in dirs):
            dirs.append(folder)
    return dirs


def load_template(name, master='FalloutNV.esm', dirs=None):
    if ':' in name:
        master, name = name.split(':', 1)
    tried = []
    for folder in dirs or [TEMPLATE_DIR]:
        path = Path(folder) / master / (name + '.json')
        if path.exists():
            return master, json.loads(path.read_text())
        tried.append(str(path))
    raise SpecError('template', 'no template dump %s (run tools/esm_research.py dump)' % ' or '.join(tried))


def _resolve(resolver, value, where):
    try:
        return resolver.resolve(value)
    except FormIdError as e:
        raise SpecError(where, str(e))


def make_value(op, resolver, where):
    keys = [k for k in VALUE_KEYS if k in op]
    if len(keys) != 1:
        raise SpecError(where, 'give exactly one value (%s)' % ', '.join(VALUE_KEYS))
    k = keys[0]
    v = op[k]
    if k == 'text':
        return zstring(v)
    if k == 'texts':
        return b''.join(zstring(t) for t in v)
    if k == 'form':
        return struct.pack('<I', _resolve(resolver, v, where))
    if k == 'forms':
        return b''.join(struct.pack('<I', _resolve(resolver, f, where)) for f in v)
    if k == 'hex':
        return bytes.fromhex(v)
    if k == 'empty':
        return b''
    if k == 'pack':
        values = [(_resolve(resolver, x, where) if isinstance(x, str) and x.startswith('@') else x)
                  for x in op.get('values', [])]
        try:
            return struct.pack(v, *values)
        except struct.error as e:
            raise SpecError(where, 'pack %s: %s' % (v, e))
    fmt = {'u8': '<B', 'u16': '<H', 'u32': '<I', 's32': '<i', 'float': '<f'}[k]
    try:
        return struct.pack(fmt, v)
    except struct.error as e:
        raise SpecError(where, '%s: %s' % (k, e))


def _insert_at(subs, after):
    if after is None:
        return len(subs)
    idx = [i for i, s in enumerate(subs) if s.tag == after]
    if not idx:
        raise SpecError('fields', 'cannot insert after %s: not present' % after)
    return idx[-1] + 1


def apply_fields(subs, fields, resolver, where):
    for n, op in enumerate(fields):
        w = '%s.fields[%d]' % (where, n)
        if not isinstance(op, dict):
            raise SpecError(w, 'expected an object')
        if 'insert' in op:
            items = [Subrecord(o['tag'], make_value(o, resolver, w)) for o in op['insert']]
            at = _insert_at(subs, op.get('after'))
            subs[at:at] = items
            continue
        tag = op.get('tag')
        if not isinstance(tag, str) or len(tag) != 4:
            raise SpecError(w, 'tag must be a 4-character subrecord signature')
        if op.get('remove'):
            subs[:] = [s for s in subs if s.tag != tag]
            continue
        if 'patch' in op:
            hits = [i for i, s in enumerate(subs) if s.tag == tag]
            if not hits:
                raise SpecError(w, 'cannot patch %s: not present' % tag)
            data = bytearray(subs[hits[0]].data)
            for offset, fmt, value in op['patch']:
                if isinstance(value, str) and value.startswith('@'):
                    value = _resolve(resolver, value, w)
                size = struct.calcsize(fmt)
                if offset < 0 or offset + size > len(data):
                    raise SpecError(w, 'patch %s at %d outside %d-byte %s' % (fmt, offset, len(data), tag))
                struct.pack_into(fmt, data, offset, value)
            subs[hits[0]] = Subrecord(tag, bytes(data))
            continue
        value = make_value(op, resolver, w)
        hits = [i for i, s in enumerate(subs) if s.tag == tag]
        if hits and not op.get('append'):
            subs[hits[0]] = Subrecord(tag, value)
        else:
            at = _insert_at(subs, op.get('after'))
            subs.insert(at, Subrecord(tag, value))
    return subs


def build_generic(form_id, edid, spec, resolver, where=None, masters=None, templates=None):
    where = where or 'records.%s' % edid
    check_edid(edid, where)
    rtype = spec['type']
    allowed = {'type', 'template', 'fields', 'flags'}
    unknown = set(spec) - allowed
    if unknown:
        raise SpecError(where, 'unknown field(s): %s' % ', '.join(sorted(unknown)))
    subs = []
    if spec.get('template'):
        master, tpl = load_template(spec['template'], dirs=templates)
        if tpl['type'] != rtype:
            raise SpecError(where + '.template', '%s is a %s, not a %s' % (spec['template'], tpl['type'], rtype))
        if masters is not None and (not masters or masters[0].lower() != master.lower()):
            raise SpecError(where + '.template', 'template master %s must be the first master' % master)
        subs = [Subrecord(s['tag'], bytes.fromhex(s['hex'])) for s in tpl['subrecords']]
    subs = [s for s in subs if s.tag != 'EDID']
    subs.insert(0, Subrecord('EDID', zstring(edid)))
    apply_fields(subs, spec.get('fields', []), resolver, where)
    rec = record(rtype, form_id, subs)
    rec.flags = int(spec.get('flags', 0))
    return rec


def script_text(base_dir, spec, edid, where):
    src = spec.get('source')
    if not isinstance(src, str):
        raise SpecError(where + '.source', 'script source file required')
    path = (Path(base_dir) / src) if base_dir else Path(src)
    if not path.exists():
        raise SpecError(where + '.source', 'not found: %s' % path)
    text = path.read_text(encoding='cp1252').replace('\r\n', '\n').replace('\n', '\r\n').rstrip() + '\r\n'
    first = text.split('\r\n', 1)[0].split(';')[0].split()
    if len(first) < 2 or first[0].lower() not in ('scn', 'scriptname') or first[1].lower() != edid.lower():
        raise SpecError(where + '.source', 'first line must be "scn %s"' % edid)
    return text.encode('cp1252')


def source_sha(text_bytes, stype):
    return hashlib.sha256(text_bytes + b'|type=%d' % stype).hexdigest()


def build_script(form_id, edid, spec, where=None, base_dir=None, cache=None):
    where = where or 'records.%s' % edid
    check_edid(edid, where)
    unknown = set(spec) - {'type', 'source', 'script_type'}
    if unknown:
        raise SpecError(where, 'unknown SCPT field(s): %s' % ', '.join(sorted(unknown)))
    stype = SCRIPT_TYPES.get(spec.get('script_type', 'object'))
    if stype is None:
        raise SpecError(where + '.script_type', 'one of %s' % ', '.join(SCRIPT_TYPES))
    text = script_text(base_dir, spec, edid, where)
    sha = source_sha(text, stype)
    entry = (cache or {}).get(edid)
    if entry and entry.get('sourceSha256') == sha and entry.get('formId') == '%08X' % form_id:
        subs = [Subrecord('EDID', zstring(edid))]
        for tag, hexdata in entry['compiled']:
            subs.append(Subrecord(tag, text if tag == 'SCTX' else bytes.fromhex(hexdata)))
        rec = record('SCPT', form_id, subs)
        rec.compiled = True
        return rec
    schr = struct.pack('<4sIIIHH', b'\0' * 4, 0, 0, 0, stype, 1)
    rec = record('SCPT', form_id, [Subrecord('EDID', zstring(edid)), Subrecord('SCHR', schr),
                                   Subrecord('SCTX', text)])
    rec.compiled = False
    return rec


def extract_compiled(plugin, cache_formids=None):
    """From a GECK-saved plugin: {edid: [(tag, hex), ...]} of each SCPT's compiled subrecords."""
    out = {}
    for rec, _ in plugin.records():
        if rec.type != 'SCPT':
            continue
        schr = rec.get('SCHR')
        if not schr or len(schr) < 20:
            continue
        compiled_size = struct.unpack_from('<I', schr, 8)[0]
        out[rec.editor_id] = {
            'formId': '%08X' % rec.form_id,
            'compiledSize': compiled_size,
            'compiled': [(s.tag, s.data.hex()) for s in rec.subrecords if s.tag in COMPILED_TAGS],
            'text': (rec.get('SCTX') or b''),
            'type': struct.unpack_from('<H', schr, 16)[0],
        }
    return out
