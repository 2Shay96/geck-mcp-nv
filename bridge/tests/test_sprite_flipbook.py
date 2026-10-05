"""Billboard flipbook builder: layout, edge colours and the vanilla-matched NIF structure.

Needs Pillow and PyFFI; skipped where they are not importable (e.g. the Mac venv, whose vendored
Pillow is built for /usr/bin/python3 3.9 — run there with `/usr/bin/python3 -m unittest`).
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    import sprite_flipbook as sf
    from PIL import Image, ImageDraw
    from pyffi.formats.nif import NifFormat as N
except Exception as error:                     # pragma: no cover - environment dependent
    sf = None
    SKIP = str(error)
else:
    SKIP = ''


def collision_template(path, material=3):
    """A small clutter-style NIF: root -> bhkCollisionObject -> bhkRigidBody -> bhkConvexVerticesShape."""
    data = N.Data(version=0x14020007, user_version=11, user_version_2=34)
    data.header.endian_type = 1
    root = N.BSFadeNode()
    root.name = b'Template'
    root.flags = 14
    bsx = N.BSXFlags()
    bsx.name = b'BSX'
    bsx.integer_data = 2                                   # Havok
    root.add_extra_data(bsx)
    shape = N.bhkConvexVerticesShape()
    shape.radius = 0.1
    sf._set_shape_material(shape, material)
    body = N.bhkRigidBody()
    body.shape = shape
    body.mass = 2.0
    collision = N.bhkCollisionObject()
    collision.body = body
    collision.target = root
    root.collision_object = collision
    data.roots = [root]
    with open(path, 'wb') as stream:
        data.write(stream)
    return path


def frames(count=6, size=200):
    out = []
    for i in range(count):
        im = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse((60 + i, 30, 140, 190), fill=(240, 234, 231, 255))
        out.append(im)
    return out


@unittest.skipIf(sf is None, 'Pillow/PyFFI unavailable: %s' % SKIP)
class FlipbookTests(unittest.TestCase):
    def test_crop_and_layout_fit_power_of_two(self):
        box = sf.union_bbox(frames())
        self.assertEqual(box, (58, 28, 143, 193))
        layout = sf.plan_layout(70, (0, 0, 485, 905), 2048)
        self.assertEqual((layout['columns'], layout['rows'], layout['atlas']), (12, 6, [2048, 2048]))
        self.assertLessEqual(layout['columns'] * layout['cellW'], 2048)
        self.assertLessEqual(layout['rows'] * layout['cellH'], 2048)

    def test_transparent_texels_take_the_sprite_colour(self):
        tile = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
        ImageDraw.Draw(tile).rectangle((10, 10, 21, 21), fill=(240, 234, 231, 255))
        out = sf.bleed(tile)
        self.assertEqual(out.getpixel((5, 5)), (240, 234, 231, 0))     # colour bled, alpha kept
        self.assertEqual(out.getpixel((15, 15)), (240, 234, 231, 255))

    def build(self, animation):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'x.nif'
            layout = sf.plan_layout(6, (0, 0, 100, 160), 512)
            kinds = sf.build_nif(path, 6, 24, layout, (-20.0, 20.0, 0.0, 64.0), 'textures\\x.dds',
                                 root_name=b'Test', animation=animation)
            self.assertEqual((kinds['NiVisController'], kinds['NiTriShape'], kinds['NiNode']), (6, 6, 7))
            # Vanilla writes pose byte 2 on keyed NiBoolInterpolators; 1 freezes the frame (in-game bug).
            self.assertEqual(kinds['keyedBoolPose'], 2)
            raw = path.read_bytes()
            from geck_mcp.esp.assets import nif_block_types
            info = nif_block_types(raw)
            self.assertEqual({raw[o] for k, o in zip(info['blocks'], info['offsets'])
                              if k == 'NiBoolInterpolator'}, {2})
            data = N.Data()
            with open(path, 'rb') as stream:
                data.read(stream)
        return data, kinds

    def check_geometry_and_keys(self, data, bool_interpolator):
        keys = [(round(k.time, 4), k.value) for k in bool_interpolator.data.data.keys]
        self.assertEqual(keys, [(0.0, 0), (0.125, 1), (0.1667, 0), (0.25, 0)])
        self.assertEqual(bool_interpolator.data.data.interpolation, 5)
        billboard = [b for b in data.blocks if isinstance(b, N.NiBillboardNode)][0]
        self.assertEqual(billboard.billboard_mode, 5)
        shape = billboard.children[0].children[0]
        verts = [(v.x, v.y, v.z) for v in shape.data.vertices]
        self.assertTrue(all(y == 0 for _, y, _ in verts))                   # vertical XZ quad
        a, b, c = verts[0], verts[1], verts[2]
        normal_y = (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2])
        self.assertLess(normal_y, 0)                                         # front faces -Y

    def test_free_running_matches_vanilla_mstt_effects(self):
        data, kinds = self.build('free')
        self.assertNotIn('NiControllerManager', kinds)
        root = data.roots[0]
        self.assertIsNone(root.controller)
        nodes = [b for b in data.blocks if isinstance(b, N.NiNode) and b.name == b'Frame0003']
        controller = nodes[0].controller
        self.assertEqual((type(controller).__name__, controller.flags, controller.start_time,
                          round(controller.stop_time, 4), type(controller.interpolator).__name__),
                         ('NiVisController', 72, 0.0, 0.25, 'NiBoolInterpolator'))
        self.assertEqual(nodes[0].flags, 15)
        self.check_geometry_and_keys(data, controller.interpolator)

    def test_manager_variant_matches_vanilla_idle_meshes(self):
        data, _ = self.build('manager')
        root = data.roots[0]
        manager = root.controller
        sequence = manager.controller_sequences[0]
        self.assertEqual((manager.flags, sequence.name, sequence.cycle_type, sequence.target_name),
                         (76, b'Idle', 0, b'Test'))
        self.assertEqual(type(manager.next_controller).__name__, 'NiMultiTargetTransformController')
        self.assertIn(b'KFAccumRoot', b''.join(getattr(e, 'string_data', b'') or b'' for e in root.get_extra_datas()))
        link = sequence.controlled_blocks[3]
        self.assertEqual((link.controller.flags, link.controller.interpolator.unknown_short,
                          link.controller.interpolator.bool_value, link.controller.target.name),
                         (108, 513, 2, b'Frame0003'))
        self.check_geometry_and_keys(data, link.interpolator)

    def test_uv_flipbook_matches_vanilla_fire_texture_scroll(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'uv.nif'
            layout = sf.plan_layout(6, (0, 0, 100, 160), 512)
            kinds = sf.build_nif(path, 6, 24, layout, (-20.0, 20.0, 0.0, 64.0), 'textures\\x.dds',
                                 animation='uv', tint=(0.3, 1.0, 0.3))
            self.assertEqual((kinds['NiTriShape'], kinds['NiTextureTransformController']), (1, 2))
            data = N.Data()
            with open(path, 'rb') as stream:
                data.read(stream)
        texturing = [b for b in data.blocks if isinstance(b, N.NiTexturingProperty)][0]
        self.assertTrue(texturing.base_texture.has_texture_transform)
        self.assertEqual(texturing.base_texture.source.file_name, b'textures\\x.dds')
        u, v = texturing.controller, texturing.controller.next_controller
        self.assertEqual([(c.flags, c.operation, c.start_time) for c in (u, v)], [(72, 0, 0.0), (72, 1, 0.0)])
        self.assertLess(u.interpolator.float_value, -1e38)               # vanilla "use keys" value
        cell_u = layout['cellW'] / layout['atlas'][0]
        values = [round(k.value, 5) for k in u.interpolator.data.data.keys]
        su = sf.UV_SIGN[0]
        self.assertEqual(sf.UV_SIGN, (-1.0, 1.0))                        # confirmed in-game
        self.assertEqual(values[:6], [0.0, 0.0, round(su * cell_u, 5), round(su * cell_u, 5),
                                      round(2 * su * cell_u, 5), round(2 * su * cell_u, 5)])
        times = [k.time for k in u.interpolator.data.data.keys]
        self.assertTrue(all(b > a for a, b in zip(times, times[1:])))    # strictly increasing
        self.assertLess(times[2] - times[1], 1e-5)                         # near-instant jumps
        material = [b for b in data.blocks if isinstance(b, N.NiMaterialProperty)][0]
        self.assertAlmostEqual(material.emissive_color.r, 0.3, places=5)

    def test_fixed_variant_has_no_billboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'fixed.nif'
            layout = sf.plan_layout(6, (0, 0, 100, 160), 512)
            kinds = sf.build_nif(path, 6, 24, layout, (-20.0, 20.0, 0.0, 64.0), 'textures\\x.dds',
                                 billboard=False)
        self.assertNotIn('NiBillboardNode', kinds)
        self.assertEqual((kinds['NiNode'], kinds['NiVisController']), (8, 6))


    def test_havok_material_names(self):
        self.assertEqual(sf.havok_material('organic'), 6)
        self.assertEqual(sf.havok_material('Cloth'), 1)
        self.assertEqual(sf.havok_material('7'), 7)
        self.assertEqual(sf.havok_material(24), 24)
        with self.assertRaises(ValueError):
            sf.havok_material('jelly')

    def test_collision_material_keeps_or_replaces_the_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            template = collision_template(Path(tmp) / 'template.nif', material=sf.havok_material('glass'))
            self.assertEqual(sf.collision_material(template), 3)
            layout = sf.plan_layout(6, (0, 0, 100, 160), 512)
            for material, expected in ((None, 3), (sf.havok_material('organic'), 6)):
                path = Path(tmp) / ('m%s.nif' % material)
                kinds = sf.build_nif(path, 6, 24, layout, (-20.0, 20.0, 0.0, 64.0), 'textures\\x.dds',
                                     animation='uv', collision=(str(template), (12.0, 8.0, 10.0), material))
                self.assertEqual((kinds['bhkCollisionObject'], kinds['bhkConvexVerticesShape']), (1, 1))
                self.assertEqual(sf.collision_material(path), expected)
                data = N.Data()
                with open(path, 'rb') as stream:
                    data.read(stream)
                root = data.roots[0]
                shape = root.collision_object.body.shape
                xs = sorted({round(v.x * 7, 4) for v in shape.vertices})
                ys = sorted({round(v.y * 7, 4) for v in shape.vertices})
                zs = sorted({round(v.z * 7, 4) for v in shape.vertices})
                self.assertEqual((len(shape.vertices), xs, ys, zs), (8, [-12.0, 12.0], [-8.0, 8.0], [0.0, 10.0]))
                bsx = [e for e in root.get_extra_datas() if isinstance(e, N.BSXFlags)]
                self.assertEqual([e.integer_data for e in bsx], [3])        # Animated | Havok
            without = Path(tmp) / 'none.nif'
            sf.build_nif(without, 6, 24, layout, (-20.0, 20.0, 0.0, 64.0), 'textures\\x.dds', animation='uv')
            self.assertIsNone(sf.collision_material(without))

    def test_cli_output_does_not_depend_on_the_callers_hash_seed(self):
        # PyFFI writes the string table in set order; the script re-runs itself with PYTHONHASHSEED=0.
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'frames'
            source.mkdir()
            for i, im in enumerate(frames(4)):
                im.save(source / ('f%02d.png' % i))
            template = collision_template(Path(tmp) / 'template.nif')
            hashes = []
            for seed in ('1', '2', 'random'):
                out = Path(tmp) / ('out' + seed)
                done = subprocess.run([sys.executable, str(ROOT / 'sprite_flipbook.py'), '--frames', str(source),
                                       '--out', str(out), '--name', 'test/flip', '--max-side', '256',
                                       '--collision-template', str(template), '--collision-material', 'organic'],
                                      capture_output=True, text=True, env=dict(os.environ, PYTHONHASHSEED=seed))
                self.assertEqual(done.returncode, 0, done.stderr[-2000:])
                manifest = json.loads((out / 'meshes' / 'test' / 'flip.manifest.json').read_text())
                mesh = (out / 'meshes' / 'test' / 'flip.nif').read_bytes()
                self.assertEqual(manifest['meshSha256'], hashlib.sha256(mesh).hexdigest())
                self.assertEqual(manifest['collisionMaterial'], 6)
                hashes.append((manifest['meshSha256'], manifest['textureSha256']))
            self.assertEqual(len(set(hashes)), 1, hashes)


if __name__ == '__main__':
    unittest.main()
