"""Build an animated sprite ("billboard flipbook") for Fallout: New Vegas from PNG frames.

    python3 sprite_flipbook.py --frames DIR --out DATA_DIR --name salvatore/salvatore_flipbook
                               [--fps 24] [--frame-units 128] [--max-side 2048]

Writes <out>/textures/<name>.dds and <out>/meshes/<name>.nif. Design, from vanilla FNV meshes:
  * Animation (default "uv", confirmed working in-game): one quad; two free-running
    NiTextureTransformControllers (flags 72, as vanilla fire/mist MSTTs) step the base texture's
    U/V offset through the atlas cells with held linear keys. The per-frame NiVisController
    variants ("free", "manager") are kept for reference only: in-game they never advanced past
    their first evaluation, whatever the setup (billboard or not, STAT or MSTT, managed or free).
  * Orientation: an NiBillboardNode in mode 5 (BSROTATE_ABOUT_UP) with a vertical quad in the
    local XZ plane whose front face points -Y: exactly vanilla's fire sprites
    (effects\\fxfiremeshsmall.nif). It turns only about the vertical axis, so it stays upright.
    Mode 0 (ALWAYS_FACE_CAMERA) with an XY quad showed up sideways in-game.
  * Texture: alpha-weighted (premultiplied) resizing, colour bleeding into transparent texels,
    and a full DXT5 mipmap chain, so block compression and minification do not create coloured
    speckles or shimmering fringes around the silhouette.
Requires Pillow, PyFFI 2.2.3 and setuptools (PyFFI imports distutils, which Python 3.12 removed); all three
are in requirements.lock.txt. The script re-runs itself with PYTHONHASHSEED=0: PyFFI writes the NIF string
table in set order, so without a fixed hash seed the same frames give different (equally valid) NIF bytes.
"""
import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))                   # geck_mcp (NIF header parser)
for vendor in (ROOT.parent / 'vendor', Path('/home/claude/vendor')):
    if vendor.exists():
        sys.path.insert(0, str(vendor))
time.clock = time.perf_counter            # PyFFI 2.2.3 predates its removal
from PIL import Image, ImageChops, ImageFilter  # noqa: E402

BLEED_PASSES = 24
FLT_MAX = 3.4028234663852886e+38
KNOWN_ALPHA = 32


# -- texture ------------------------------------------------------------------------

def premultiplied_resize(image, size):
    """Resize RGBA without letting transparent pixels' RGB darken or tint the edges."""
    # Area averaging in premultiplied space: no ringing, no dark or tinted halo.
    return image.convert('RGBa').resize(size, Image.Resampling.BOX).convert('RGBA')


def bleed(image, passes=BLEED_PASSES):
    """Fill RGB of fully transparent pixels from their nearest visible neighbours.

    Alpha is untouched. This keeps DXT colour blocks on the silhouette uniform and makes
    bilinear/mipmap sampling pull the sprite's own colours instead of black. Each pass sets a
    newly reached pixel to the mean colour of its already-known 3x3 neighbours.
    """
    alpha = image.getchannel('A')
    # Colours of nearly transparent pixels are unreliable after resizing; rebuild them too.
    known = alpha.point(lambda v: 255 if v >= KNOWN_ALPHA else 0)
    bands = list(image.convert('RGB').split())
    kernel = ImageFilter.Kernel((3, 3), [1] * 9, scale=1)      # neighbour sum, no normalisation
    for _ in range(passes):
        ones = known.point(lambda v: 1 if v else 0)
        neighbours = ones.filter(kernel)                        # 0..9 known neighbours
        grown = neighbours.point(lambda v: 255 if v > 0 else 0)
        if grown.tobytes() == known.tobytes():
            break
        selectors = {n: neighbours.point(lambda v, n=n: 255 if v == n else 0) for n in range(1, 10)}
        new_bands = []
        for band in bands:
            masked = ImageChops.multiply(band, known)           # band where known, else 0
            # Exact mean of the n known neighbours: one kernel pass with scale=n per count n.
            filled = Image.new('L', band.size)
            for n in range(1, 10):
                mean = masked.filter(ImageFilter.Kernel((3, 3), [1] * 9, scale=n))
                filled = Image.composite(mean, filled, selectors[n])
            new_bands.append(Image.composite(band, filled, known))
        bands = new_bands
        known = grown
    out = Image.merge('RGB', bands)
    out.putalpha(alpha)
    return out


def union_bbox(frames, pad=2):
    """Bounding box of every non-transparent pixel across all frames (so frames stay aligned)."""
    box = None
    for frame in frames:
        b = frame.convert('RGBA').getchannel('A').getbbox()
        if b:
            box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    if box is None:
        raise ValueError('all frames are fully transparent')
    w, h = frames[0].size
    return (max(0, box[0] - pad), max(0, box[1] - pad), min(w, box[2] + pad), min(h, box[3] + pad))


def plan_layout(count, box, max_side=2048, gutter=2):
    """Largest cell (keeping the crop's aspect) whose grid fits a power-of-two atlas <= max_side."""
    bw, bh = box[2] - box[0], box[3] - box[1]
    best = None
    for cell_h in range(max_side, 15, -1):
        cell_w = max(8, round(cell_h * bw / bh))
        if cell_w > max_side:
            continue
        columns = min(count, max_side // cell_w)
        rows = math.ceil(count / columns)
        if rows * cell_h > max_side:
            continue
        width = 2 ** math.ceil(math.log2(columns * cell_w))
        height = 2 ** math.ceil(math.log2(rows * cell_h))
        best = {'cellW': cell_w, 'cellH': cell_h, 'columns': columns, 'rows': rows,
                'atlas': [width, height], 'gutter': gutter}
        break
    if best is None:
        raise ValueError('cannot fit %d frames in %d px' % (count, max_side))
    return best


def build_atlas(frames, layout, box):
    atlas = Image.new('RGBA', tuple(layout['atlas']), (0, 0, 0, 0))
    g, cw, ch = layout['gutter'], layout['cellW'], layout['cellH']
    for index, frame in enumerate(frames):
        sprite = premultiplied_resize(frame.convert('RGBA').crop(box), (cw - 2 * g, ch - 2 * g))
        tile = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
        tile.paste(sprite, (g, g))
        tile = bleed(tile)
        atlas.paste(tile, ((index % layout['columns']) * cw, (index // layout['columns']) * ch))
    return atlas


def mip_chain(atlas, smallest=4):
    levels = [atlas]
    while min(levels[-1].size) > smallest:
        w, h = levels[-1].size
        half = levels[-1].convert('RGBa').resize((max(1, w // 2), max(1, h // 2)),
                                                 Image.Resampling.BOX).convert('RGBA')
        levels.append(bleed(half, passes=4))
    return levels


def dxt5_payload(level):
    """DXT5 blocks for one level, using Pillow's encoder (header stripped)."""
    buffer = io.BytesIO()
    level.save(buffer, format='DDS', pixel_format='DXT5')
    data = buffer.getvalue()
    return data[128:]


def write_dds(path, levels):
    width, height = levels[0].size
    payloads = [dxt5_payload(level) for level in levels]
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000 | 0x80000          # CAPS HEIGHT WIDTH PIXELFORMAT MIPMAPCOUNT LINEARSIZE
    pixel_format = struct.pack('<II4s5I', 32, 0x4, b'DXT5', 0, 0, 0, 0, 0)
    caps = 0x1000 | 0x8 | 0x400000                                  # TEXTURE COMPLEX MIPMAP
    header = struct.pack('<4s7I44x', b'DDS ', 124, flags, height, width, len(payloads[0]), 0, len(levels))
    header += pixel_format + struct.pack('<5I', caps, 0, 0, 0, 0)
    assert len(header) == 128, len(header)
    Path(path).write_bytes(header + b''.join(payloads))
    return {'width': width, 'height': height, 'mipmaps': len(levels), 'bytes': 128 + sum(map(len, payloads))}


# -- mesh -----------------------------------------------------------------------------

INVALID_BOOL = 2


def mark_keyed_bool_interpolators(nif):
    """Set the pose byte of every keyed NiBoolInterpolator to 2 ("invalid": use the keys).

    Vanilla FNV writes 2 there whenever the interpolator has NiBoolData; 0/1 means a constant pose
    and the engine then ignores the keys, so the sprite never changes frame. PyFFI 2.2.3 stores the
    field as a Python bool and can only write 0/1, so the byte is patched after writing.
    """
    from geck_mcp.esp.assets import nif_block_types
    info = nif_block_types(nif)
    out = bytearray(nif)
    for kind, offset, size in zip(info['blocks'], info['offsets'], info['sizes']):
        if kind == 'NiBoolInterpolator':
            if size != 5:
                raise ValueError('unexpected NiBoolInterpolator size %d' % size)
            if struct.unpack_from('<i', out, offset + 1)[0] >= 0:
                out[offset] = INVALID_BOOL
    return bytes(out)


def _quad_shape(N, name, quad, uv_box, props):
    left, right, bottom, top = quad
    u0, v0, u1, v1 = uv_box
    shape = N.NiTriShape()
    shape.name = name
    shape.flags = 14
    for prop in props:
        shape.add_property(prop)
    geometry = N.NiTriShapeData()
    shape.data = geometry
    geometry.num_vertices = 4
    geometry.has_vertices = True
    geometry.vertices.update_size()
    # Vertical quad in the local XZ plane; +Z is up, the sprite faces local -Y.
    for vertex, xyz in zip(geometry.vertices, [(left, 0, bottom), (right, 0, bottom),
                                               (right, 0, top), (left, 0, top)]):
        vertex.x, vertex.y, vertex.z = xyz
    geometry.num_uv_sets = 1
    geometry.uv_sets.update_size()
    for uv, coords in zip(geometry.uv_sets[0], [(u0, v1), (u1, v1), (u1, v0), (u0, v0)]):
        uv.u, uv.v = coords
    geometry.set_triangles([(0, 1, 2), (0, 2, 3), (2, 1, 0), (3, 2, 0)])   # double-sided
    geometry.update_center_radius()
    return shape


HOLD = 1e-6    # seconds of linear ramp between frames; float32 keeps these distinct (ulp < 2.5e-7 at
               # t < 4 s). 1e-4 let an unlucky slow game frame sample mid-ramp: a misaligned frame.


def _float_track(N, values, fps, stop, hold=HOLD):
    """Linear NiFloatData holding each per-frame value, jumping within `hold` seconds.

    Vanilla FNV never uses step keys (type 5) on NiFloatData (scan of Fallout - Meshes.bsa:
    616 linear, 1781 quadratic, 6 TBC), so steps are emulated with near-vertical linear ramps.
    """
    data = N.NiFloatData()
    keys = []
    for index, value in enumerate(values):
        t0, t1 = index / float(fps), (index + 1) / float(fps)
        keys += [(t0, value), (t1 - hold, value)]
    keys.append((stop, values[0]))
    data.data.num_keys = len(keys)
    data.data.interpolation = 1                           # LINEAR (vanilla fire uses 1)
    data.data.keys.update_size()
    for key, (timestamp, value) in zip(data.data.keys, keys):
        key.time, key.value = timestamp, value
    interpolator = N.NiFloatInterpolator()
    interpolator.float_value = -FLT_MAX                   # vanilla "invalid": use the keys
    interpolator.data = data
    return interpolator


UV_SIGN = (-1.0, 1.0)  # (u, v) signs of the texture translation, confirmed in-game 2026-09-30:
                       # (-u, +v) plays cleanly (3ds Max "Offset" convention); (+u, +v) showed half
                       # cells, (-u, -v) played frames in the wrong order.


def reproducible_hash_seed():
    """Re-run this script with PYTHONHASHSEED=0 unless it already is (byte-identical NIFs for the same input)."""
    if os.environ.get('PYTHONHASHSEED') == '0':
        return
    raise SystemExit(subprocess.call([sys.executable, *sys.argv], env=dict(os.environ, PYTHONHASHSEED='0')))


# Fallout 3 / NV Havok materials (nif.xml "Fallout3HavokMaterial"): the shape's material picks the impact
# and scrape sounds. The vanilla ashtray template is glass-like; a sprite character wants something soft.
HAVOK_MATERIALS = {'stone': 0, 'cloth': 1, 'dirt': 2, 'glass': 3, 'grass': 4, 'metal': 5, 'organic': 6, 'skin': 7,
                   'water': 8, 'wood': 9, 'bottle': 24, 'rubber_ball': 31}


def havok_material(value):
    """'organic' / 'ORGANIC' / '6' / 6 -> 6. Raises ValueError for unknown names."""
    if isinstance(value, int):
        return value
    text = str(value).strip().lower()
    if text.isdigit():
        return int(text)
    if text not in HAVOK_MATERIALS:
        raise ValueError('unknown Havok material %r (one of %s or a number)' % (value, ', '.join(HAVOK_MATERIALS)))
    return HAVOK_MATERIALS[text]


def _set_shape_material(shape, material):
    """PyFFI 2.2.3 stores the shape material as a HavokMaterial struct (.material) or a bare enum."""
    holder = shape.material
    if hasattr(holder, 'material'):
        holder.material = material
        return int(holder.material)
    shape.material = material
    return int(shape.material)


def _get_shape_material(shape):
    holder = shape.material
    return int(holder.material) if hasattr(holder, 'material') else int(holder)


def collision_material(path):
    """Havok material of a NIF's root collision shape, read back from disk (None without collision)."""
    from pyffi.formats.nif import NifFormat as N
    data = N.Data()
    with open(path, 'rb') as stream:
        data.read(stream)
    collision = data.roots[0].collision_object
    return None if collision is None else _get_shape_material(collision.body.shape)


def box_collision(root, template_path, box, material=None):
    """Give `root` the Havok collision of a vanilla clutter NIF, resized to a box.

    template_path: a vanilla NIF whose root has bhkCollisionObject -> bhkRigidBody ->
    bhkConvexVerticesShape (e.g. clutter\\ashtray\\ashtray01.nif). box = (half_x, half_y, height)
    in game units, standing on z=0. Havok units are game units / 7 (FNV). Returns the template root's
    extra data list so its BSX (Havok) flags and UPB can be merged. material (Havok material number, see
    HAVOK_MATERIALS) replaces the template's, which sets the sound when the object is knocked about.
    """
    from pyffi.formats.nif import NifFormat as N
    tpl = N.Data()
    with open(template_path, 'rb') as stream:
        tpl.read(stream)
    troot = tpl.roots[0]
    collision = troot.collision_object
    if collision is None or not isinstance(collision.body.shape, N.bhkConvexVerticesShape):
        raise ValueError('template has no convex-vertices collision: %s' % template_path)
    body, shape = collision.body, collision.body.shape
    hx, hy, hz = (v / 7.0 for v in box)
    corners = [(x, y, z) for x in (-hx, hx) for y in (-hy, hy) for z in (0.0, hz)]
    shape.num_vertices = 8
    shape.vertices.update_size()
    for v, (x, y, z) in zip(shape.vertices, corners):
        v.x, v.y, v.z, v.w = x, y, z, 0.0
    planes = [(-1, 0, 0, -hx), (1, 0, 0, -hx), (0, -1, 0, -hy), (0, 1, 0, -hy), (0, 0, -1, 0.0), (0, 0, 1, -hz)]
    shape.num_normals = 6
    shape.normals.update_size()
    for n, (x, y, z, w) in zip(shape.normals, planes):
        n.x, n.y, n.z, n.w = x, y, z, w
    body.translation.x = body.translation.y = body.translation.z = 0.0
    body.center.x, body.center.y, body.center.z = 0.0, 0.0, hz / 2
    m = body.mass
    ixx, iyy, izz = (m / 12 * ((2 * hy) ** 2 + hz ** 2), m / 12 * ((2 * hx) ** 2 + hz ** 2),
                     m / 12 * ((2 * hx) ** 2 + (2 * hy) ** 2))
    inertia = body.inertia
    for name in ('m_11', 'm_12', 'm_13', 'm_14', 'm_21', 'm_22', 'm_23', 'm_24', 'm_31', 'm_32', 'm_33', 'm_34'):
        if hasattr(inertia, name):
            setattr(inertia, name, 0.0)
    inertia.m_11, inertia.m_22, inertia.m_33 = ixx, iyy, izz
    if material is not None:
        _set_shape_material(shape, material)
    collision.target = root
    root.collision_object = collision
    return [e for e in troot.get_extra_datas()]


def build_nif(path, count, fps, layout, quad, texture_rel, billboard_mode=5, root_name=b'SpriteFlipbook',
              animation='free', billboard=True, tint=None, uv_sign=UV_SIGN, prn=None, offset_z=0.0,
              collision=None):
    """quad = (left, right, bottom, top) in game units around the billboard pivot (feet at 0).

    animation: 'free' (per-frame NiVisControllers, flags 72), 'manager' (Idle sequence driving the
    same controllers) or 'uv' (one quad; free NiTextureTransformControllers step the texture offset
    through the atlas cells, the way vanilla fire/mist MSTTs animate their textures).
    billboard=False puts the frames under a plain NiNode (fixed, faces -Y) for diagnosis.
    tint=(r, g, b) in 0..1 sets the material colour, to tell test copies apart in-game.
    """
    from pyffi.formats.nif import NifFormat as N
    if animation not in ('free', 'manager', 'uv'):
        raise ValueError('animation must be free, manager or uv')
    atlas_w, atlas_h = layout['atlas']
    columns, cw, ch, g = layout['columns'], layout['cellW'], layout['cellH'], layout['gutter']
    data = N.Data(version=0x14020007, user_version=11, user_version_2=34)
    data.header.endian_type = 1
    root = N.BSFadeNode()
    root.name = root_name
    root.flags = 14
    bsx = N.BSXFlags()
    bsx.name = b'BSX'
    bsx.integer_data = 1                                  # Animated
    if collision:
        # Havok body from a vanilla clutter mesh; merge its BSX flags (Havok) and UPB string.
        for extra in box_collision(root, collision[0], collision[1], collision[2] if len(collision) > 2 else None):
            if isinstance(extra, N.BSXFlags):
                bsx.integer_data |= extra.integer_data
            elif isinstance(extra, N.NiStringExtraData):
                root.add_extra_data(extra)
    root.add_extra_data(bsx)
    if prn:
        # Creature body part: the engine parents this mesh to the skeleton bone named here.
        attach = N.NiStringExtraData()
        attach.name = b'Prn'
        attach.string_data = prn.encode('ascii')
        root.add_extra_data(attach)
    holder = N.NiBillboardNode() if billboard else N.NiNode()
    holder.name = b'SpriteBillboard' if billboard else b'SpriteFixed'
    holder.flags = 14
    holder.translation.z = offset_z
    if billboard:
        holder.billboard_mode = billboard_mode
    non_accum = N.NiNode()                                # vanilla: '<root> NonAccum' under the root
    non_accum.name = root.name + b' NonAccum'
    non_accum.flags = 14
    root.add_child(non_accum)
    non_accum.add_child(holder)

    shader = N.BSShaderNoLightingProperty()
    shader.flags = 1
    shader.shader_type = 33
    shader.shader_flags.sf_z_buffer_test = 1
    shader.shader_flags_2.sf_2_z_buffer_write = 1
    shader.file_name = texture_rel.encode('cp1252')
    shader.falloff_start_opacity = 1
    shader.falloff_stop_opacity = 1
    alpha = N.NiAlphaProperty()
    alpha.flags = 4845                                   # blend SRC_ALPHA/INV_SRC_ALPHA + test GREATER
    alpha.threshold = 64
    material = N.NiMaterialProperty()
    colour = tint or (1.0, 1.0, 1.0)
    for c in (material.diffuse_color, material.emissive_color):
        c.r, c.g, c.b = colour
    material.glossiness = 10.0
    material.alpha = 1.0

    def cell_uv(index):
        x, y = index % columns, index // columns
        return ((x * cw + g) / atlas_w, (y * ch + g) / atlas_h,
                (x * cw + cw - g) / atlas_w, (y * ch + ch - g) / atlas_h)

    stop = count / float(fps)
    palette_objects = [(root.name, root), (non_accum.name, non_accum), (holder.name, holder)]
    expected = {'NiTriShape': count, 'NiVisController': count, 'NiNode': count + 1 + (0 if billboard else 1)}

    if animation == 'uv':
        # Texture flipbook: NiTexturingProperty with a texture transform, as vanilla fire.
        texturing = N.NiTexturingProperty()
        texturing.flags = 4
        texturing.apply_mode = 0
        texturing.texture_count = 9
        texturing.has_base_texture = True
        base = texturing.base_texture
        source = N.NiSourceTexture()
        source.use_external = 1
        source.file_name = texture_rel.encode('cp1252')
        source.pixel_layout = 6
        source.use_mipmaps = 1
        source.alpha_format = 3
        source.is_static = 1
        source.direct_render = True
        base.source = source
        base.flags = 0x3200                              # vanilla fire: trilinear, wrap S/T
        base.ps_2_k = -75
        base.has_texture_transform = True
        base.tiling.u = base.tiling.v = 1.0
        base.transform_type = 1
        base.center_offset.u = base.center_offset.v = 0.5
        node = N.NiNode()
        node.name = b'Sprite'
        node.flags = 14
        shape = _quad_shape(N, b'Sprite:0', quad, cell_uv(0), (shader, alpha, material, texturing))
        node.add_child(shape)
        holder.add_child(node)
        u_first, v_first = cell_uv(0)[:2]
        tracks = [(0, [uv_sign[0] * (cell_uv(i)[0] - u_first) for i in range(count)]),  # TT_TRANSLATE_U
                  (1, [uv_sign[1] * (cell_uv(i)[1] - v_first) for i in range(count)])]  # TT_TRANSLATE_V
        previous = None
        for operation, values in tracks:
            controller = N.NiTextureTransformController()
            controller.flags = 72                         # vanilla fire value
            controller.frequency = 1.0
            controller.start_time = 0.0
            controller.stop_time = stop
            controller.target = texturing
            controller.texture_slot = 0
            controller.operation = operation
            controller.interpolator = _float_track(N, values, fps, stop)
            if previous is None:
                texturing.controller = controller
            else:
                previous.next_controller = controller
            previous = controller
        expected = {'NiTriShape': 1, 'NiTextureTransformController': 2, 'NiNode': 2 + (0 if billboard else 1)}
    else:
        if animation == 'manager':
            upb = N.NiStringExtraData()                   # vanilla managed meshes all carry this
            upb.name = b'UPB'
            upb.string_data = b'KFAccumRoot = \r\n'
            root.add_extra_data(upb)
            manager = N.NiControllerManager()
            manager.flags = 76                            # vanilla value (fxscorchnv.nif)
            manager.frequency = 1.0
            manager.start_time = FLT_MAX                  # vanilla managers carry an empty range
            manager.stop_time = -FLT_MAX
            manager.cumulative = False
            root.add_controller(manager)
            multi = N.NiMultiTargetTransformController()  # vanilla: always chained after the manager
            multi.flags = 108
            multi.frequency = 1.0
            multi.start_time = FLT_MAX
            multi.stop_time = -FLT_MAX
            multi.target = root
            manager.next_controller = multi
            sequence = N.NiControllerSequence()
            sequence.name = b'Idle'
            sequence.weight = 1.0
            sequence.cycle_type = 0                       # CYCLE_LOOP
            sequence.frequency = 1.0
            sequence.start_time = 0.0
            sequence.stop_time = stop
            sequence.manager = manager
            sequence.target_name = root.name
            sequence.unknown_int_1 = 1                    # vanilla values
            sequence.unknown_int_3 = 64
            text_keys = N.NiTextKeyExtraData()
            text_keys.num_text_keys = 2
            text_keys.text_keys.update_size()
            text_keys.text_keys[0].time, text_keys.text_keys[0].value = 0.0, b'start'
            text_keys.text_keys[1].time, text_keys.text_keys[1].value = stop, b'end'
            sequence.text_keys = text_keys
            manager.num_controller_sequences = 1
            manager.controller_sequences.update_size()
            manager.controller_sequences[0] = sequence
            palette = N.NiDefaultAVObjectPalette()
            manager.object_palette = palette
            sequence.num_controlled_blocks = count
            sequence.controlled_blocks.update_size()

        for index in range(count):
            node = N.NiNode()                             # vis target, as in vanilla
            node.name = ('Frame%04d' % index).encode()
            node.flags = 14 if index == 0 else 15         # frame 0 shows where nothing animates (GECK)
            shape = _quad_shape(N, node.name + b':0', quad, cell_uv(index), (shader, alpha, material))
            node.add_child(shape)
            holder.add_child(node)
            palette_objects += [(node.name, node), (shape.name, shape)]

            # Step keys: visible from frame start to frame end, hidden otherwise, with a closing key
            # at the loop end (vanilla data carries hold keys like this).
            t0, t1 = index / float(fps), (index + 1) / float(fps)
            values = {0.0: int(index == 0), t0: 1, t1: 0, stop: int(index == 0)}
            interpolator = N.NiBoolInterpolator()
            interpolator.bool_value = True                # patched to 2 after writing (see below)
            keys = N.NiBoolData()
            interpolator.data = keys
            keys.data.num_keys = len(values)
            keys.data.interpolation = 5                   # CONST (step)
            keys.data.keys.update_size()
            for key, (timestamp, value) in zip(keys.data.keys, sorted(values.items())):
                key.time, key.value = timestamp, value

            controller = N.NiVisController()
            controller.frequency = 1.0
            controller.start_time = 0.0
            controller.stop_time = stop
            controller.target = node
            node.add_controller(controller)
            if animation == 'free':
                # Free-running, as vanilla MSTT effects (effects\ambient\fxdustmeshtube01.nif):
                # flags 72 = active | 0x40, APP_TIME, loop; the interpolator sits on the controller.
                controller.flags = 72
                controller.interpolator = interpolator
            else:
                controller.flags = 108                    # vanilla managed value
                blend = N.NiBlendBoolInterpolator()
                blend.unknown_short = 513                 # vanilla values
                blend.unknown_int = 0
                blend.bool_value = 2                      # "invalid" until the manager blends
                controller.interpolator = blend
                block = sequence.controlled_blocks[index]
                block.interpolator = interpolator
                block.controller = controller
                block.priority = 0
                block.node_name = node.name
                block.controller_type = b'NiVisController'
                block.property_type = b''

        if animation == 'manager':
            palette.num_objs = len(palette_objects)
            palette.objs.update_size()
            for entry, (name, obj) in zip(palette.objs, palette_objects):
                entry.name = name
                entry.av_object = obj

    data.roots = [root]
    buffer = io.BytesIO()
    data.write(buffer)
    Path(path).write_bytes(mark_keyed_bool_interpolators(buffer.getvalue()))
    check = N.Data()
    with open(path, 'rb') as stream:
        check.read(stream)
    unique = {}
    for block in check.get_global_iterator():
        unique[id(block)] = block
    kinds = {}
    for b in unique.values():
        kinds[type(b).__name__] = kinds.get(type(b).__name__, 0) + 1
    expected['NiBillboardNode'] = 1 if billboard else 0
    expected['NiControllerManager'] = int(animation == 'manager')
    wrong = {k: (kinds.get(k, 0), v) for k, v in expected.items() if kinds.get(k, 0) != v}
    if wrong:
        raise ValueError('NIF round-trip check failed (got, expected): %s' % wrong)
    from geck_mcp.esp.assets import nif_block_types
    raw = Path(path).read_bytes()
    info = nif_block_types(raw)
    pose = [raw[o] for k, o in zip(info['blocks'], info['offsets']) if k == 'NiBoolInterpolator']
    if pose != [INVALID_BOOL] * len(pose):
        raise ValueError('keyed NiBoolInterpolator pose bytes must all be 2, got %s' % sorted(set(pose)))
    kinds['keyedBoolPose'] = INVALID_BOOL
    return kinds


def main():
    reproducible_hash_seed()
    parser = argparse.ArgumentParser()
    parser.add_argument('--frames', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='a Data-shaped folder (meshes/, textures/)')
    parser.add_argument('--name', default='salvatore/salvatore_flipbook')
    parser.add_argument('--fps', type=int, default=24)
    parser.add_argument('--frame-units', type=float, default=128.0,
                        help='game units covered by the full source frame height (sets the sprite size)')
    parser.add_argument('--max-side', type=int, default=2048)
    parser.add_argument('--billboard-mode', type=int, default=5)
    parser.add_argument('--no-billboard', action='store_true', help='fixed quad facing -Y (diagnosis)')
    parser.add_argument('--root-name', default='SalvatoreFlipbook')
    parser.add_argument('--animation', choices=('free', 'manager', 'uv'), default='uv',
                        help='free-running vis controllers, an Idle sequence, or a UV-offset flipbook')
    parser.add_argument('--uv-sign', default='%g,%g' % UV_SIGN, help='u,v signs of the UV offsets (+1/-1)')
    parser.add_argument('--prn', help='creature body part: skeleton bone to attach to (e.g. Bip01)')
    parser.add_argument('--offset-z', type=float, default=0.0, help='raise/lower the sprite (game units)')
    parser.add_argument('--collision-template', help='vanilla clutter NIF to borrow Havok collision from')
    parser.add_argument('--collision-box', default='12,12,10', help='collision box half-x,half-y,height')
    parser.add_argument('--collision-material', help='Havok material name or number (e.g. organic, cloth); '
                        'default: keep the template\'s')
    parser.add_argument('--tint', help='r,g,b in 0..1 material colour, e.g. 1,0.3,0.3')
    parser.add_argument('--reuse-texture', help='existing texture name (e.g. salvatore/salvatore_anim) '
                        'built from the same frames and --max-side; skips building a DDS')
    args = parser.parse_args()
    paths = sorted(args.frames.glob('*.png'))
    if not paths:
        raise SystemExit('no PNG frames in %s' % args.frames)
    frames = [Image.open(p) for p in paths]
    fw, fh = frames[0].size
    if any(f.size != (fw, fh) for f in frames):
        raise SystemExit('frames differ in size')
    box = union_bbox(frames)
    layout = plan_layout(len(frames), box, args.max_side)
    # Keep the source frame's scale and horizontal centre as the pivot; the crop's bottom edge
    # (the feet) sits on the reference's origin.
    unit = args.frame_units / fh
    quad = ((box[0] - fw / 2.0) * unit, (box[2] - fw / 2.0) * unit, 0.0, (box[3] - box[1]) * unit)
    mesh = args.out / 'meshes' / (args.name + '.nif')
    mesh.parent.mkdir(parents=True, exist_ok=True)
    texture_name = args.reuse_texture or args.name
    texture = args.out / 'textures' / (texture_name + '.dds')
    dds = None
    if not args.reuse_texture:
        texture.parent.mkdir(parents=True, exist_ok=True)
        atlas = build_atlas(frames, layout, box)
        dds = write_dds(texture, mip_chain(atlas))
        atlas.save(texture.with_suffix('.preview.png'))
    tint = tuple(float(v) for v in args.tint.split(',')) if args.tint else None
    kinds = build_nif(mesh, len(frames), args.fps, layout, quad,
                      'textures\\' + texture_name.replace('/', '\\') + '.dds',
                      args.billboard_mode, args.root_name.encode('ascii'), args.animation,
                      not args.no_billboard, tint, tuple(float(v) for v in args.uv_sign.split(',')),
                      args.prn, args.offset_z,
                      (args.collision_template, tuple(float(v) for v in args.collision_box.split(',')),
                       havok_material(args.collision_material) if args.collision_material else None)
                      if args.collision_template else None)
    bounds = [math.floor(min(quad[0], -quad[1])), math.floor(min(quad[0], -quad[1])), 0,
              math.ceil(max(-quad[0], quad[1])), math.ceil(max(-quad[0], quad[1])), math.ceil(quad[3])]
    manifest = {'frames': len(frames), 'fps': args.fps, 'loopSeconds': len(frames) / args.fps,
                'sourceSize': [fw, fh], 'crop': list(box), 'layout': layout, 'quadUnits': quad,
                'suggestedBounds': bounds, 'dds': dds, 'blocks': kinds, 'billboard': not args.no_billboard,
                'billboardMode': args.billboard_mode, 'animation': args.animation, 'tint': tint, 'uvSign': args.uv_sign,
                'texture': str(texture), 'mesh': str(mesh),
                'collisionMaterial': collision_material(mesh) if args.collision_template else None,
                'textureSha256': hashlib.sha256(texture.read_bytes()).hexdigest() if texture.exists() else None,
                'meshSha256': hashlib.sha256(mesh.read_bytes()).hexdigest(),
                'sourceSha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    (mesh.parent / (Path(args.name).name + '.manifest.json')).write_text(json.dumps(manifest, indent=1) + '\n')
    print(json.dumps({k: v for k, v in manifest.items() if k not in ('sourceSha256', 'blocks', 'layout')}))


if __name__ == '__main__':
    main()
