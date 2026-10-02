"""Offline validation of a generated plugin (tiers 1 and 2 of plan.md).

Tier 1 structural: group labels match contents, interior block rules, cell-children
labels, HEDR record count and next-object-ID, unique FormIDs and EditorIDs,
reference targets exist (our records, or master records via the index).
Tier 2 assets: every model exists (loose or in a BSA); every texture a model uses exists.
Returns {'ok', 'errors', 'warnings', 'checked'}; never raises for content problems.
"""
import struct

from . import codec
from .assets import AssetError, nif_textures
from .build import interior_block


def validate(data, index=None, assets=None, masters_expected=None):
    errors, warnings, checked = [], [], {'records': 0, 'groups': 0, 'references': 0, 'models': 0, 'textures': 0}
    try:
        plugin = codec.parse(data, lazy=False)
    except codec.FormatError as e:
        return {'ok': False, 'errors': ['structure: %s' % e], 'warnings': [], 'checked': checked}

    masters = [codec.cstring(s.data) for s in plugin.header.subrecords if s.tag == 'MAST']
    if masters_expected is not None and masters != list(masters_expected):
        errors.append('header: masters %s, expected %s' % (masters, masters_expected))
    self_byte = len(masters)
    hedr = plugin.header.get('HEDR')
    if not hedr or len(hedr) != 12:
        errors.append('header: HEDR missing or wrong size')
        hedr = struct.pack('<fII', 0, 0, 0)
    _version, count, next_id = struct.unpack('<fII', hedr)

    own, edids, max_local = {}, {}, 0

    def walk(items, parent):
        for item in items:
            if isinstance(item, codec.Group):
                checked['groups'] += 1
                check_group(item, parent)
                walk(item.children, item)
            else:
                checked['records'] += 1
                check_record(item, parent)

    def check_group(group, parent):
        where = 'group %r' % group
        if group.group_type == 0:
            label = group.label.decode('ascii', 'replace')
            bad = [c for c in group.children if isinstance(c, codec.Record) and c.type != label]
            if bad:
                errors.append('%s holds %s records' % (where, sorted({c.type for c in bad})))
        elif group.group_type in (2, 3):
            number = struct.unpack('<i', group.label)[0]
            for cell in (c for c in iter_cells(group)):
                block, sub = interior_block(cell.form_id & 0xFFFFFF)
                if (group.group_type == 2 and number != block) or (group.group_type == 3 and number != sub):
                    errors.append('cell %s (%08X) is in %s but belongs in block %d sub-block %d'
                                  % (cell.editor_id, cell.form_id, where, block, sub))
        elif group.group_type in (6, 8, 9):
            label = struct.unpack('<I', group.label)[0]
            if group.group_type == 6:
                siblings = parent.children if parent else []
                index_in = siblings.index(group)
                prev = siblings[index_in - 1] if index_in else None
                if not isinstance(prev, codec.Record) or prev.type != 'CELL' or prev.form_id != label:
                    errors.append('%s does not follow its CELL %08X' % (where, label))
            elif parent is None or struct.unpack('<I', parent.label)[0] != label:
                errors.append('%s label differs from its cell-children group' % where)

    def check_record(rec, parent):
        nonlocal max_local
        key = rec.form_id
        if key in own:
            errors.append('duplicate FormID %08X (%s and %s)' % (key, own[key].type, rec.type))
        own[key] = rec
        if key >> 24 == self_byte:
            max_local = max(max_local, key & 0xFFFFFF)
        elif rec.type != 'TES4':
            warnings.append('%s %08X overrides a master record' % (rec.type, key))
        edid = rec.editor_id
        if edid:
            if edid.lower() in edids:
                errors.append('duplicate EditorID %s' % edid)
            edids[edid.lower()] = rec

    walk(plugin.groups, None)
    total = checked['records'] + checked['groups']
    if count != total:
        errors.append('header: HEDR record count %d, file has %d records+groups' % (count, total))
    if own and next_id <= max_local:
        errors.append('header: next object ID %06X not above highest local ID %06X' % (next_id, max_local))

    by_form = {}
    if index is not None:
        for hits in index.entries.values():
            for pos, rtype, form, _full, model, edid in hits:
                by_form[(index.masters[pos], form & 0xFFFFFF)] = (rtype, edid, model)
    from .records import ACTOR_PLACEMENT
    for rec in own.values():
        if rec.type not in ('REFR', 'ACHR', 'ACRE'):
            continue
        checked['references'] += 1
        base = struct.unpack('<I', rec.get('NAME'))[0] if rec.get('NAME') else None
        where = '%s %08X' % (rec.type, rec.form_id)
        if base is None:
            errors.append('%s has no base (NAME)' % where)
        elif base >> 24 == self_byte:
            if base not in own:
                errors.append('%s points at %08X, which is not in this plugin' % (where, base))
            elif own[base].type in ('CELL', 'REFR', 'ACHR', 'ACRE', 'TES4'):
                errors.append('%s base %08X is a %s' % (where, base, own[base].type))
            elif ACTOR_PLACEMENT.get(own[base].type, 'REFR') != rec.type:
                errors.append('%s places a %s; that must be a %s record'
                              % (where, own[base].type, ACTOR_PLACEMENT.get(own[base].type, 'REFR')))
        elif base >> 24 < self_byte:
            master = masters[base >> 24]
            if index is None or master not in index.masters:
                warnings.append('%s base %08X in %s not checked (no index)' % (where, base, master))
            elif (master, base & 0xFFFFFF) not in by_form:
                errors.append('%s base %08X not found in %s index' % (where, base, master))
            else:
                base_type = by_form[(master, base & 0xFFFFFF)][0]
                wanted = ACTOR_PLACEMENT.get(base_type, 'REFR')
                if wanted != rec.type:
                    errors.append('%s places a %s; that must be a %s record' % (where, base_type, wanted))
        else:
            errors.append('%s base %08X has an invalid load-order byte' % (where, base))
        if rec.get('DATA') is None or len(rec.get('DATA')) != 24:
            errors.append('%s DATA must be 24 bytes' % where)

    if assets is not None:
        for rec in own.values():
            model = rec.get('MODL')
            if not model:
                continue
            rel = 'meshes\\' + codec.cstring(model)
            checked['models'] += 1
            hit = assets.find(rel)
            where = '%s %s' % (rec.type, rec.editor_id)
            if hit is None:
                errors.append('%s model missing: Data\\%s' % (where, rel))
                continue
            if hit['where'] != 'loose':
                continue
            try:
                with open(hit['path'], 'rb') as stream:
                    textures = nif_textures(stream.read())
            except (AssetError, OSError) as e:
                errors.append('%s model unreadable: %s' % (where, e))
                continue
            if not textures:
                warnings.append('%s model references no .dds textures' % where)
            for tex in textures:
                checked['textures'] += 1
                if assets.find(tex) is None:
                    errors.append('%s texture missing: Data\\%s (used by %s)' % (where, tex, rel))
    return {'ok': not errors, 'errors': errors, 'warnings': warnings, 'checked': checked}


def iter_cells(group):
    for child in group.children:
        if isinstance(child, codec.Record) and child.type == 'CELL':
            yield child
        elif isinstance(child, codec.Group) and child.group_type in (2, 3):
            yield from iter_cells(child)
