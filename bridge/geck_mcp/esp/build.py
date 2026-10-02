"""Spec -> plugin bytes. Pure and deterministic: same spec + FormID map + index = same bytes.

Spec (JSON):
{
  "schema": 1, "project_id": "coolworld", "plugin": "CoolWorld.esp",
  "author": "2Shay", "description": "...", "masters": ["FalloutNV.esm"],
  "records": {"<EditorID>": {"type": "STAT"|"LIGH", ...fields}},
  "cells":   {"<EditorID>": {"name": ..., "lighting": {...},
              "objects": [{"ref_id": "salvatore", "base": "@EditorID"|"XXXXXXXX",
                           "position": [x,y,z], "rotation": [deg,deg,deg], "scale": 1.0}]}},
  "release": {}   # reserved for Milestone 3
}
Only interior cells in this version. Standard library only.
"""
import hashlib
import json
import re

from . import codec, records
from .codec import Group, Plugin
from .formids import FormIdError, FormIdMap, MasterIndex, Resolver
from .records import SpecError
from . import generic

SCHEMA = 1
GENERATED_MARK = '[geck-bridge generated: %s]'
# Top-level group order used by GECK/FalloutNV.esm (read from the master, 2026-09-29).
TOP_ORDER = ['GMST', 'TXST', 'MICN', 'GLOB', 'CLAS', 'FACT', 'HDPT', 'HAIR', 'EYES', 'RACE', 'SOUN',
             'ASPC', 'MGEF', 'SCPT', 'LTEX', 'ENCH', 'SPEL', 'ACTI', 'TACT', 'TERM', 'ARMO', 'BOOK',
             'CONT', 'DOOR', 'INGR', 'LIGH', 'MISC', 'STAT', 'SCOL', 'MSTT', 'PWAT', 'GRAS', 'TREE',
             'FURN', 'WEAP', 'AMMO', 'NPC_', 'CREA', 'LVLC', 'LVLN', 'KEYM', 'ALCH', 'IDLM', 'NOTE',
             'COBJ', 'PROJ', 'LVLI', 'WTHR', 'CLMT', 'REGN', 'NAVI', 'CELL', 'WRLD', 'DIAL', 'QUST',
             'IDLE', 'PACK', 'CSTY', 'LSCR', 'ANIO', 'WATR', 'EFSH', 'EXPL', 'DEBR', 'IMGS', 'IMAD',
             'FLST', 'PERK', 'BPTD', 'ADDN', 'AVIF', 'RADS', 'CAMS', 'CPTH', 'VTYP', 'IPCT', 'IPDS',
             'ARMA', 'ECZN', 'MESG', 'RGDL', 'DOBJ', 'LGTM', 'MUSC', 'IMOD', 'REPU', 'RCPE', 'RCCT',
             'CHIP', 'CSNO', 'LSCT', 'MSET', 'ALOC', 'CHAL', 'AMEF', 'CCRD', 'CMNY', 'CDCK', 'DEHY',
             'HUNG', 'SLPD']
REF_ID_RE = re.compile(r'^[A-Za-z0-9_.-]{1,64}$')
TOP_KEYS = {'schema', 'project_id', 'plugin', 'author', 'description', 'masters', 'records',
            'cells', 'release'}


def load_spec(text):
    try:
        spec = json.loads(text)
    except ValueError as e:
        raise SpecError('spec', 'invalid JSON: %s' % e)
    return check_spec(spec)


def check_spec(spec):
    if not isinstance(spec, dict):
        raise SpecError('spec', 'expected a JSON object')
    unknown = set(spec) - TOP_KEYS
    if unknown:
        raise SpecError('spec', 'unknown top-level field(s): %s' % ', '.join(sorted(unknown)))
    if spec.get('schema') != SCHEMA:
        raise SpecError('schema', 'must be %d' % SCHEMA)
    if not isinstance(spec.get('project_id'), str) or not re.match(r'^[a-z0-9][a-z0-9_-]{0,63}$', spec['project_id']):
        raise SpecError('project_id', 'lowercase letters, digits, - and _ only')
    plugin = spec.get('plugin')
    if not isinstance(plugin, str) or not re.match(r'^[A-Za-z0-9 _.-]{1,60}\.esp$', plugin):
        raise SpecError('plugin', 'must be a simple .esp filename')
    masters = spec.get('masters')
    if not isinstance(masters, list) or not masters or len(set(m.lower() for m in masters)) != len(masters):
        raise SpecError('masters', 'must be a non-empty list without duplicates')
    for field in ('records', 'cells'):
        if not isinstance(spec.get(field, {}), dict):
            raise SpecError(field, 'expected an object keyed by EditorID')
    seen = {}
    for field in ('records', 'cells'):
        for edid in spec.get(field, {}):
            records.check_edid(edid, '%s.%s' % (field, edid))
            if edid.lower() in seen:
                raise SpecError('%s.%s' % (field, edid), 'EditorID also used in %s' % seen[edid.lower()])
            seen[edid.lower()] = field
    for edid, rec in spec.get('records', {}).items():
        kinds = set(records.BUILDERS) | generic.GENERIC_TYPES
        if not isinstance(rec, dict) or rec.get('type') not in kinds:
            raise SpecError('records.%s.type' % edid, 'must be one of %s' % ', '.join(sorted(kinds)))
    for cell_id, cell in spec.get('cells', {}).items():
        if not isinstance(cell, dict):
            raise SpecError('cells.%s' % cell_id, 'expected an object')
        refs = set()
        objects = cell.get('objects', [])
        if not isinstance(objects, list):
            raise SpecError('cells.%s.objects' % cell_id, 'expected a list')
        for i, obj in enumerate(objects):
            where = 'cells.%s.objects[%d]' % (cell_id, i)
            if not isinstance(obj, dict) or 'base' not in obj:
                raise SpecError(where, 'each object needs a "base"')
            ref_id = obj.get('ref_id')
            if ref_id is not None:
                if not isinstance(ref_id, str) or not REF_ID_RE.match(ref_id):
                    raise SpecError(where + '.ref_id', 'letters, digits, . _ - only (max 64)')
                if ref_id in refs:
                    raise SpecError(where + '.ref_id', 'duplicate ref_id %r in this cell' % ref_id)
                refs.add(ref_id)
    return spec


def ref_key(cell_id, index, obj):
    return 'REFR:%s:%s' % (cell_id, obj['ref_id'] if obj.get('ref_id') else '#%d' % index)


def allocation_keys(spec):
    """Every FormID key in deterministic spec order: records, cells, then references."""
    keys = list(spec.get('records', {})) + list(spec.get('cells', {}))
    for cell_id, cell in spec.get('cells', {}).items():
        keys += [ref_key(cell_id, i, obj) for i, obj in enumerate(cell.get('objects', []))]
    return keys


def interior_block(local_id):
    """Interior cell block / sub-block: last and penultimate decimal digits of the object index."""
    return local_id % 10, (local_id // 10) % 10


def build(spec, formids, index=None, base_dir=None, script_cache=None):
    """Return (plugin_bytes, receipt). `formids` is a FormIdMap (updated in place, not saved).

    base_dir: folder that script "source" paths are relative to (the spec's folder).
    script_cache: {EditorID: compiled entry} from scripts.load_cache(); uncompiled otherwise.
    """
    spec = check_spec(spec)
    index = index or MasterIndex()
    masters = spec['masters']
    self_byte = len(masters) << 24
    warnings = []
    local = formids.sync(allocation_keys(spec))
    full = {k: self_byte | v for k, v in local.items()}
    own = {k: v for k, v in full.items() if not k.startswith('REFR:')}
    for edid in own:
        clash = [h for h in index.lookup(edid) if index.masters[h[0]] in masters]
        if clash:
            raise SpecError('records.%s' % edid, 'EditorID already exists in %s as %s %08X; pick a new name '
                            '(overriding master records is not supported yet)'
                            % (index.masters[clash[0][0]], clash[0][1], clash[0][2]))
    own_types = {k: v['type'] for k, v in spec.get('records', {}).items()}
    own_types.update({k: 'CELL' for k in spec.get('cells', {})})
    resolver = Resolver(masters, own, index, own_types)

    # Base records, grouped by type in GECK's top-group order.
    by_type = {}
    uncompiled = []
    for edid, rec_spec in spec.get('records', {}).items():
        rtype = rec_spec['type']
        if rtype == 'SCPT':
            rec = generic.build_script(full[edid], edid, rec_spec, base_dir=base_dir, cache=script_cache)
            if not rec.compiled:
                uncompiled.append(edid)
        elif rtype in records.BUILDERS and 'template' not in rec_spec and 'fields' not in rec_spec:
            rec = records.BUILDERS[rtype](full[edid], edid, rec_spec)
        else:
            rec = generic.build_generic(full[edid], edid, rec_spec, resolver, masters=masters)
        by_type.setdefault(rtype, []).append(rec)

    # Interior cells: CELL -> block -> sub-block -> [CELL, children(6) -> temporary(9) -> REFR*]
    blocks = {}
    references = {}
    for cell_id, cell_spec in spec.get('cells', {}).items():
        cell_form = full[cell_id]
        cell = records.cell_interior(cell_form, cell_id, {k: v for k, v in cell_spec.items()})
        refs = []
        references[cell_id] = []
        for i, obj in enumerate(cell_spec.get('objects', [])):
            where = 'cells.%s.objects[%d]' % (cell_id, i)
            key = ref_key(cell_id, i, obj)
            if not obj.get('ref_id'):
                warnings.append('%s has no ref_id; its FormID depends on list position' % where)
            try:
                base, base_type = resolver.resolve_typed(obj['base'])
            except FormIdError as e:
                raise SpecError(where + '.base', str(e))
            kind = records.placement_type(base_type, where + '.base')
            if base_type is None:
                warnings.append('%s base type unknown (raw FormID); placed as REFR' % where)
            refs.append(records.refr(full[key], base, obj, where, record_type=kind))
            references[cell_id].append({'refId': obj.get('ref_id'), 'formId': '%08X' % full[key],
                                        'base': '%08X' % base, 'baseSpec': obj['base'],
                                        'baseType': base_type, 'recordType': kind,
                                        'editorId': obj.get('editor_id')})
        refs.sort(key=lambda r: r.form_id)
        persistent = [r for r in refs if r.flags & 0x400]
        temporary = [r for r in refs if not r.flags & 0x400]
        children = []
        if refs:
            inner = []
            if persistent:
                inner.append(Group(struct_label(cell_form), 8, children=persistent))
            if temporary:
                inner.append(Group(struct_label(cell_form), 9, children=temporary))
            children = [Group(struct_label(cell_form), 6, children=inner)]
        block, sub_block = interior_block(cell_form & 0xFFFFFF)
        blocks.setdefault(block, {}).setdefault(sub_block, []).append((cell_form, [cell] + children))

    groups = []
    for rtype in TOP_ORDER:
        if rtype in by_type:
            groups.append(Group(rtype.encode('ascii'), 0,
                                children=sorted(by_type[rtype], key=lambda r: r.form_id)))
        elif rtype == 'CELL' and blocks:
            block_groups = []
            for block in sorted(blocks):
                subs = []
                for sub_block in sorted(blocks[block]):
                    items = []
                    for _form, content in sorted(blocks[block][sub_block], key=lambda x: x[0]):
                        items += content
                    subs.append(Group(int_label(sub_block), 3, children=items))
                block_groups.append(Group(int_label(block), 2, children=subs))
            groups.append(Group(b'CELL', 0, children=block_groups))

    count = sum(1 for g in groups for _ in walk(g))
    description = spec.get('description') or ''
    mark = GENERATED_MARK % spec['project_id']
    header = records.tes4(masters, count, formids.next_object_id,
                          author=spec.get('author', 'DEFAULT'),
                          description=(description + '\n' + mark).strip())
    data = codec.write(Plugin(header, groups))
    type_counts = {}
    for rec, _ in codec.parse(data).records():
        type_counts[rec.type] = type_counts.get(rec.type, 0) + 1
    receipt = {
        'plugin': spec['plugin'], 'projectId': spec['project_id'],
        'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data),
        'specSha256': hashlib.sha256(canonical(spec)).hexdigest(),
        'masters': masters, 'indexedMasters': index.masters,
        'recordCounts': type_counts, 'hedrCount': count,
        'nextObjectId': '%06X' % formids.next_object_id,
        'formIds': {k: '%08X' % v for k, v in full.items()},
        'references': references, 'warnings': warnings, 'uncompiledScripts': uncompiled,
    }
    return data, receipt


def walk(group):
    """Yield every group and record inside (and including) a group."""
    yield group
    for child in group.children:
        if isinstance(child, Group):
            yield from walk(child)
        else:
            yield child


def struct_label(form_id):
    return form_id.to_bytes(4, 'little')


def int_label(value):
    return value.to_bytes(4, 'little', signed=True)


def canonical(spec):
    return json.dumps(spec, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def is_generated(plugin_bytes, project_id=None):
    """True if the plugin carries our generated marker (for the given project, if any)."""
    header = codec.parse(plugin_bytes).header
    snam = header.get('SNAM')
    if not snam:
        return False
    text = codec.cstring(snam)
    return (GENERATED_MARK % project_id) in text if project_id else '[geck-bridge generated:' in text


def adopt_existing(formids, spec, plugin_bytes):
    """Seed a FormID map from a hand-built plugin so a first rebuild keeps its IDs.

    Base records and cells match by EditorID; references match by position within
    each cell, in ascending FormID order of the existing plugin.
    """
    spec = check_spec(spec)
    plugin = codec.parse(plugin_bytes)
    by_edid, refs_by_cell, cell_of = {}, {}, {}
    for rec, path in plugin.records():
        if rec.editor_id:
            by_edid[rec.editor_id.lower()] = rec
        if rec.type in ('REFR', 'ACHR', 'ACRE'):
            owner = [g for g in path if g.group_type in (8, 9)]
            if owner:
                refs_by_cell.setdefault(int.from_bytes(owner[-1].label, 'little'), []).append(rec)
    adopted = []
    for edid in list(spec.get('records', {})) + list(spec.get('cells', {})):
        rec = by_edid.get(edid.lower())
        if rec is not None:
            formids.seed(edid, rec.form_id & 0xFFFFFF)
            adopted.append(edid)
            cell_of[rec.form_id] = edid
    for cell_form, refs in refs_by_cell.items():
        cell_id = cell_of.get(cell_form)
        if cell_id is None:
            continue
        objects = spec['cells'].get(cell_id, {}).get('objects', [])
        for i, (obj, rec) in enumerate(zip(objects, sorted(refs, key=lambda r: r.form_id))):
            key = ref_key(cell_id, i, obj)
            formids.seed(key, rec.form_id & 0xFFFFFF)
            adopted.append(key)
    return adopted
