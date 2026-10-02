"""Typed builders for the FNV record types CoolWorld needs: TES4, STAT, LIGH, CELL, REFR.

Layouts follow FNVEdit (https://tes5edit.github.io/fopdoc/FalloutNV/Records.html) and
were checked against records GECK saved itself (tests/test_records.py). Defaults are
the values GECK writes for a new record. Builders validate their inputs and raise
SpecError with the offending field; they never guess.
"""
import math
import re
import struct

from .codec import Record, Subrecord, zstring

EDID_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,127}$')
HEDR_VERSION = 1.34                  # FNV plugin format version, as GECK writes it
BRUS_NONE = 0xFF                     # STAT passthrough sound: none
FLT_MAX = struct.unpack('<f', b'\xff\xff\x7f\x7f')[0]  # XCLW "no water"
GECK_LNAM_DEFAULT = 0x9F             # inherit flags GECK writes for a new interior cell
# Bounds GECK assigns to a light without a model (the light-marker box; vanilla lights use it too).
LIGHT_MARKER_BOUNDS = [-38, -40, -74, 38, 40, 48]

LIGHT_FLAGS = {
    'dynamic': 0x001, 'can_carry': 0x002, 'negative': 0x004, 'flicker': 0x008,
    'off_by_default': 0x020, 'flicker_slow': 0x040, 'pulse': 0x080, 'pulse_slow': 0x100,
    'spot_light': 0x200, 'spot_shadow': 0x400,
}
CELL_FLAGS = {
    'interior': 0x01, 'has_water': 0x02, 'invert_fast_travel': 0x04, 'no_lod_water': 0x08,
    'public': 0x20, 'hand_changed': 0x40, 'behave_like_exterior': 0x80,
}
# Lighting-template inherit bits (LNAM). A bit set = take that value from the template.
LIGHTING_INHERIT = {
    'ambient': 0x001, 'directional': 0x002, 'fog_color': 0x004, 'fog_near': 0x008,
    'fog_far': 0x010, 'directional_rotation': 0x020, 'directional_fade': 0x040,
    'clip_distance': 0x080, 'fog_power': 0x100,
}


class SpecError(ValueError):
    def __init__(self, where, message):
        super().__init__('%s: %s' % (where, message))
        self.where = where


# -- field helpers -------------------------------------------------------------------

def check_edid(edid, where):
    if not isinstance(edid, str) or not EDID_RE.match(edid):
        raise SpecError(where, 'EditorID must match %s' % EDID_RE.pattern)
    return edid


def text(value, where, max_len=512):
    if not isinstance(value, str):
        raise SpecError(where, 'expected text')
    try:
        encoded = zstring(value)
    except UnicodeEncodeError:
        raise SpecError(where, 'text must be representable in Windows-1252')
    if len(encoded) > max_len:
        raise SpecError(where, 'text longer than %d bytes' % max_len)
    return encoded


def model_path(value, where):
    if not isinstance(value, str) or not value:
        raise SpecError(where, 'model path required')
    path = value.replace('/', '\\')
    parts = path.split('\\')
    if (path.startswith('\\') or ':' in path or '..' in parts or
            parts[0].lower() == 'meshes' or not path.lower().endswith('.nif')):
        raise SpecError(where, 'model must be a .nif path relative to Data\\meshes (got %r)' % value)
    return text(path, where, 260)


def number(value, where, lo=None, hi=None, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or \
            (integer and not isinstance(value, int)) or \
            (isinstance(value, float) and not math.isfinite(value)):
        raise SpecError(where, 'expected %s' % ('an integer' if integer else 'a finite number'))
    if lo is not None and value < lo or hi is not None and value > hi:
        raise SpecError(where, 'must be between %s and %s' % (lo, hi))
    return value


def vector(value, where, n=3, lo=None, hi=None, integer=False):
    if not isinstance(value, (list, tuple)) or len(value) != n:
        raise SpecError(where, 'expected a list of %d numbers' % n)
    return [number(v, '%s[%d]' % (where, i), lo, hi, integer) for i, v in enumerate(value)]


def color(value, where):
    """[r, g, b] 0-255 -> 4 bytes r g b 0 (FNV colour layout)."""
    r, g, b = vector(value, where, 3, 0, 255, integer=True)
    return bytes((r, g, b, 0))


def flags(names, table, where):
    if not isinstance(names, (list, tuple)):
        raise SpecError(where, 'expected a list of flag names')
    bits = 0
    for name in names:
        if name not in table:
            raise SpecError(where, 'unknown flag %r (known: %s)' % (name, ', '.join(sorted(table))))
        bits |= table[name]
    return bits


def bounds(value, where):
    """Object bounds [x1, y1, z1, x2, y2, z2] as int16."""
    b = vector(value, where, 6, -32768, 32767, integer=True)
    if any(b[i] > b[i + 3] for i in range(3)):
        raise SpecError(where, 'each minimum must be <= its maximum')
    return struct.pack('<6h', *b)


def form(value):
    return struct.pack('<I', value)


def sub(tag, data):
    return Subrecord(tag, data)


def record(rtype, form_id, subs, vc1=0):
    return Record(rtype, form_id, flags=0, vc1=vc1, form_version=15, vc2=0,
                  _subrecords=[s for s in subs if s is not None])


# -- record builders -----------------------------------------------------------------

def tes4(masters, record_count, next_object_id, author='DEFAULT', description=None):
    """File header. record_count counts every record and group after TES4 (as GECK does)."""
    if not masters:
        raise SpecError('masters', 'at least one master is required')
    subs = [sub('HEDR', struct.pack('<fII', HEDR_VERSION, record_count, next_object_id)),
            sub('CNAM', text(author, 'author', 512))]
    if description:
        subs.append(sub('SNAM', text(description, 'description', 512)))
    for master in masters:
        if not isinstance(master, str) or not master.lower().endswith(('.esm', '.esp')):
            raise SpecError('masters', 'master must be a .esm/.esp filename: %r' % (master,))
        subs += [sub('MAST', text(master, 'masters')), sub('DATA', b'\0' * 8)]
    return record('TES4', 0, subs)


def stat(form_id, edid, spec, where=None, vc1=0):
    where = where or 'records.%s' % edid
    check_edid(edid, where)
    allowed = {'type', 'model', 'bounds', 'passthrough_sound'}
    unknown = set(spec) - allowed
    if unknown:
        raise SpecError(where, 'unknown STAT field(s): %s' % ', '.join(sorted(unknown)))
    brus = spec.get('passthrough_sound', -1)
    number(brus, where + '.passthrough_sound', -1, 254, integer=True)
    return record('STAT', form_id, [
        sub('EDID', zstring(edid)),
        sub('OBND', bounds(spec.get('bounds', [0, 0, 0, 0, 0, 0]), where + '.bounds')),
        sub('MODL', model_path(spec.get('model'), where + '.model')),
        sub('BRUS', bytes((brus & 0xFF,))),
    ], vc1)


def ligh(form_id, edid, spec, where=None, vc1=0):
    """Light. DATA: time i32, radius u32, colour rgba, flags u32, falloff f32, fov f32, value u32, weight f32."""
    where = where or 'records.%s' % edid
    check_edid(edid, where)
    allowed = {'type', 'name', 'model', 'bounds', 'radius', 'color', 'flags', 'falloff',
               'fov', 'fade', 'time', 'value', 'weight'}
    unknown = set(spec) - allowed
    if unknown:
        raise SpecError(where, 'unknown LIGH field(s): %s' % ', '.join(sorted(unknown)))
    data = struct.pack('<iI4sIffIf',
                       number(spec.get('time', -1), where + '.time', -1, 2**31 - 1, integer=True),
                       number(spec.get('radius', 256), where + '.radius', 0, 65535, integer=True),
                       color(spec.get('color', [255, 255, 255]), where + '.color'),
                       flags(spec.get('flags', []), LIGHT_FLAGS, where + '.flags'),
                       number(spec.get('falloff', 1.0), where + '.falloff', 0, 100),
                       number(spec.get('fov', 90.0), where + '.fov', 0, 180),
                       number(spec.get('value', 0), where + '.value', 0, 2**31 - 1, integer=True),
                       number(spec.get('weight', 0.0), where + '.weight', 0, 1000))
    return record('LIGH', form_id, [
        sub('EDID', zstring(edid)),
        sub('OBND', bounds(spec.get('bounds', [0, 0, 0, 0, 0, 0] if 'model' in spec else LIGHT_MARKER_BOUNDS),
                           where + '.bounds')),
        sub('MODL', model_path(spec['model'], where + '.model')) if 'model' in spec else None,
        sub('FULL', text(spec['name'], where + '.name')) if 'name' in spec else None,
        sub('DATA', data),
        sub('FNAM', struct.pack('<f', number(spec.get('fade', 1.0), where + '.fade', 0, 100))),
    ], vc1)


def xcll(lighting, where):
    """Interior lighting, 40 bytes. Unspecified values use GECK's defaults."""
    allowed = {'ambient', 'directional', 'fog_color', 'fog_near', 'fog_far',
               'directional_rotation', 'directional_fade', 'clip_distance', 'fog_power'}
    unknown = set(lighting) - allowed
    if unknown:
        raise SpecError(where, 'unknown lighting field(s): %s' % ', '.join(sorted(unknown)))
    rot = vector(lighting.get('directional_rotation', [0, 0]), where + '.directional_rotation', 2,
                 -360, 360, integer=True)
    return (color(lighting.get('ambient', [0, 0, 0]), where + '.ambient') +
            color(lighting.get('directional', [0, 0, 0]), where + '.directional') +
            color(lighting.get('fog_color', [0, 0, 0]), where + '.fog_color') +
            struct.pack('<ffiifff',
                        number(lighting.get('fog_near', 0.0), where + '.fog_near', 0, 1e6),
                        number(lighting.get('fog_far', 0.0), where + '.fog_far', 0, 1e6),
                        rot[0], rot[1],
                        number(lighting.get('directional_fade', 1.0), where + '.directional_fade', 0, 100),
                        number(lighting.get('clip_distance', 0.0), where + '.clip_distance', 0, 1e6),
                        number(lighting.get('fog_power', 1.0), where + '.fog_power', 0, 100)))


def cell_interior(form_id, edid, spec, where=None, lighting_template=0, vc1=0):
    """Interior CELL. Lighting values given in the spec are not inherited from the template."""
    where = where or 'cells.%s' % edid
    check_edid(edid, where)
    allowed = {'name', 'flags', 'lighting', 'objects', 'inherit'}
    unknown = set(spec) - allowed
    if unknown:
        raise SpecError(where, 'unknown CELL field(s): %s' % ', '.join(sorted(unknown)))
    cell_flags = flags(spec.get('flags', []), CELL_FLAGS, where + '.flags') | CELL_FLAGS['interior']
    lighting = spec.get('lighting', {})
    if not isinstance(lighting, dict):
        raise SpecError(where + '.lighting', 'expected an object')
    if 'inherit' in spec:
        inherit = flags(spec['inherit'], LIGHTING_INHERIT, where + '.inherit')
    else:
        inherit = GECK_LNAM_DEFAULT
        for key in lighting:
            inherit &= ~LIGHTING_INHERIT.get(key, 0)
    return record('CELL', form_id, [
        sub('EDID', zstring(edid)),
        sub('FULL', text(spec['name'], where + '.name')) if 'name' in spec else None,
        sub('DATA', bytes((cell_flags,))),
        sub('XCLL', xcll(lighting, where + '.lighting')),
        sub('LTMP', form(lighting_template)),
        sub('LNAM', struct.pack('<I', inherit)),
        sub('XCLW', struct.pack('<f', FLT_MAX)),
        sub('XNAM', b'\0'),
    ], vc1)


# Base record type -> placed record type (FNV: NPCs are ACHR, creatures ACRE, everything else REFR).
ACTOR_PLACEMENT = {'NPC_': 'ACHR', 'LVLN': 'ACHR', 'CREA': 'ACRE', 'LVLC': 'ACRE'}
NOT_PLACEABLE = {'CELL', 'WRLD', 'REFR', 'ACHR', 'ACRE', 'TES4', 'DIAL', 'INFO', 'QUST', 'SCPT', 'GLOB',
                 'GMST', 'FACT', 'CLAS', 'RACE', 'PACK', 'IDLE', 'FLST', 'PERK', 'SPEL', 'ENCH', 'MGEF',
                 'SOUN', 'LVLI', 'COBJ', 'RCPE', 'IMAD', 'IMGS', 'WTHR', 'CLMT', 'REGN', 'LSCR', 'MESG'}


def placement_type(base_type, where):
    """Record type for placing a base of base_type (None = unknown, treated as REFR)."""
    if base_type in NOT_PLACEABLE:
        raise SpecError(where, 'a %s record cannot be placed in a cell' % base_type)
    return ACTOR_PLACEMENT.get(base_type, 'REFR')


def refr(form_id, base_form, spec, where, vc1=0, record_type='REFR'):
    """Placed reference (REFR, or ACHR/ACRE for actors). Rotation in degrees, stored in radians."""
    allowed = {'ref_id', 'base', 'position', 'rotation', 'scale', 'editor_id', 'persistent', 'disabled'}
    unknown = set(spec) - allowed
    if unknown:
        raise SpecError(where, 'unknown object field(s): %s' % ', '.join(sorted(unknown)))
    pos = vector(spec.get('position', [0, 0, 0]), where + '.position', 3, -1e6, 1e6)
    rot = [math.radians(v) for v in vector(spec.get('rotation', [0, 0, 0]), where + '.rotation', 3, -360, 360)]
    scale = number(spec.get('scale', 1.0), where + '.scale', 0.01, 10.0)
    edid = spec.get('editor_id')
    for key in ('persistent', 'disabled'):
        if not isinstance(spec.get(key, False), bool):
            raise SpecError(where + '.' + key, 'expected true or false')
    rec = record(record_type, form_id, [
        sub('EDID', zstring(check_edid(edid, where + '.editor_id'))) if edid else None,
        sub('NAME', form(base_form)),
        sub('XSCL', struct.pack('<f', scale)) if scale != 1.0 else None,
        sub('DATA', struct.pack('<6f', *pos, *rot)),
    ], vc1)
    # Record flags: 0x400 persistent reference (scripts can address it by EditorID from anywhere),
    # 0x800 initially disabled.
    rec.flags = (0x400 if spec.get('persistent') else 0) | (0x800 if spec.get('disabled') else 0)
    return rec


def mstt(form_id, edid, spec, where=None, vc1=0):
    """Moveable static: an animated/Havok static (vanilla fire effects, flags, fans).
    Layout from FalloutNV.esm: EDID, OBND, MODL, DATA (1 byte, 0). The optional looping
    sound (SNAM) is not supported yet."""
    where = where or 'records.%s' % edid
    check_edid(edid, where)
    allowed = {'type', 'model', 'bounds', 'name'}
    unknown = set(spec) - allowed
    if unknown:
        raise SpecError(where, 'unknown MSTT field(s): %s' % ', '.join(sorted(unknown)))
    return record('MSTT', form_id, [
        sub('EDID', zstring(edid)),
        sub('OBND', bounds(spec.get('bounds', [0, 0, 0, 0, 0, 0]), where + '.bounds')),
        sub('FULL', text(spec['name'], where + '.name')) if 'name' in spec else None,
        sub('MODL', model_path(spec.get('model'), where + '.model')),
        sub('DATA', b'\0'),
    ], vc1)


BUILDERS = {'STAT': stat, 'LIGH': ligh, 'MSTT': mstt}
