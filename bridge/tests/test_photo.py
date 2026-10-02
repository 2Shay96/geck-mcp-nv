"""Photo workflow: cut-out, framing loop, studio spec and subject resolution (no GECK needed)."""
import gzip
import json
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from geck_mcp import imaging
from geck_mcp.config import Project
from geck_mcp.esp import build as builder
from geck_mcp.photo import PhotoStudio, CELL
from geck_mcp.transport import BridgeError


def studio(root, entries=None):
    (root / 'state' / 'index').mkdir(parents=True)
    with gzip.open(root / 'state' / 'index' / 'FalloutNV.esm.json.gz', 'wt') as s:
        json.dump({'master': 'FalloutNV.esm', 'entries': entries or {
            'GSSunnySmiles': ['NPC_', '00104E84', 'Sunny Smiles', 'Characters\\_Male\\Skeleton.NIF'],
            'SunnySmilesFaction': ['FACT', '001691EA', 'Sunny Smiles Faction', None],
            'XMarker': ['STAT', '0000003B', None, 'MarkerX.nif'],
            'VNPCGuardA': ['NPC_', '00000A01', 'Guard', None],
            'VNPCGuardB': ['NPC_', '00000A02', 'Guard', None],
            'Cheyenne': ['CREA', '00104E85', 'Cheyenne', None]}}, s)
    p = Project(project_id='main', wine=root / 'wine', bottle=root / 'bottle', game_root=root / 'game',
                plugin='Main.esp', state_dir=root / 'state', helper=root / 'helper', spec=root / 'x.json')
    return PhotoStudio(p, lambda project: None)


class ResolveAndSpec(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = studio(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_editor_id_and_display_name(self):
        self.assertEqual(self.s.resolve('GSSunnySmiles')['formId'], '00104E84')
        self.assertEqual(self.s.resolve('sunny smiles')['editorId'], 'GSSunnySmiles')
        self.assertEqual(self.s.resolve('Cheyenne')['type'], 'CREA')

    def test_non_actor_and_ambiguous(self):
        with self.assertRaises(BridgeError) as e:
            self.s.resolve('XMarker')
        self.assertEqual(e.exception.code, 'SUBJECT_NOT_FOUND')
        with self.assertRaises(BridgeError) as e:
            self.s.resolve('Guard')
        self.assertEqual(e.exception.code, 'SUBJECT_AMBIGUOUS')

    def test_spec_is_valid_and_isolated(self):
        spec = self.s.spec_for('GSSunnySmiles', 180)
        builder.check_spec(spec)
        self.assertEqual(spec['plugin'], 'GeckPhotoStudio.esp')
        self.assertEqual(spec['masters'], ['FalloutNV.esm'])
        obj = spec['cells'][CELL]['objects'][0]
        self.assertEqual((obj['base'], obj['rotation']), ('@GSSunnySmiles', [0, 0, 180]))
        self.assertEqual(self.s.project.plugin, 'GeckPhotoStudio.esp')
        self.assertEqual(self.s.project.state_dir, self.s.main.state_dir)


def synthetic(path, bg=(110, 110, 110)):
    a = np.zeros((300, 200, 3), np.uint8)
    a[:] = bg
    yy, xx = np.mgrid[0:300, 0:200]
    ring = (np.hypot(xx - 100, yy - 150) < 80)
    a[ring] = (118, 104, 100)                        # faint reddish glow halo
    a[80:220, 70:130] = (40, 35, 30)                 # dark subject
    a[60:80, 85:115] = (170, 110, 80)                # skin-toned head
    a[140:200, 20:40] = bg                           # pocket of background (should stay clear)
    Image.fromarray(a).save(path)


class CutoutTests(unittest.TestCase):
    def test_subject_opaque_background_and_halo_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / 'a.png', Path(tmp) / 'a-cutout.png'
            synthetic(src)
            info = imaging.cutout(src, dst, pad=5)
            out = np.asarray(Image.open(dst))
            self.assertEqual(out.shape[2], 4)
            self.assertEqual(info['background'], [110, 110, 110])
            # crop box: head top 60 - pad, subject bottom 220 + pad; x 70-5 .. 130+5
            self.assertEqual(info['cropBox'], [65, 55, 135, 225])
            x0, y0 = info['cropBox'][:2]
            self.assertEqual(out[150 - y0, 100 - x0, 3], 255)   # subject centre opaque
            self.assertEqual(out[70 - y0, 100 - x0, 3], 255)    # head opaque
            self.assertEqual(out[2, 2, 3], 0)                   # halo corner transparent

    def test_bbox_and_title_bar(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'a.png'
            synthetic(src)
            rgb, _ = imaging.load_rgb(src)
            box, bg = imaging.subject_bbox(rgb)
            self.assertEqual(box, (70, 60, 130, 220))
        self.assertEqual(imaging.title_bar_pixels(1500, 722, 2880, 1440), 56)
        self.assertEqual(imaging.title_bar_pixels(1444, 722, 2880, 1440), 0)


class CornerTests(unittest.TestCase):
    def test_transparent_window_corners_are_background(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'w.png'
            a = np.zeros((300, 200, 4), np.uint8)
            a[:] = (110, 110, 110, 255)
            a[80:220, 70:130] = (40, 35, 30, 255)
            a[-6:, :6] = (0, 0, 0, 0)            # rounded bottom-left corner of a macOS window capture
            a[-6:, -6:] = (0, 0, 0, 0)
            Image.fromarray(a, 'RGBA').save(src)
            rgb, _ = imaging.load_rgb(src)
            box, _ = imaging.subject_bbox(rgb)
            self.assertEqual(box, (70, 80, 130, 220))
            info = imaging.cutout(src, Path(tmp) / 'c.png', pad=0)
            self.assertEqual(info['cropBox'], [70, 80, 130, 220])


class FakeCamera:
    """Subject whose apparent size/position respond to zoom and pan with unknown gains."""
    def __init__(self, client, height, cx, cy, zoom_factor=1.19, pan_gain=(-0.6, -0.8)):
        self.client, self.h, self.cx, self.cy = client, height, cx, cy
        self.zoom_factor, self.pan_gain = zoom_factor, pan_gain

    def steps(self, text):
        for step in text.split(';'):
            op, *args = step.split(':')
            if op == 'zoom':
                # dolly: each tick moves the camera 12% of the ORIGINAL distance (sizes grow faster near)
                self.dist = getattr(self, 'dist', 1.0)
                new = max(0.05, self.dist - 0.12 * int(args[0]))
                f = self.dist / new
                self.dist = new
                mx, my = self.client[0] / 2, self.client[1] / 2
                self.h *= f
                self.cx, self.cy = mx + (self.cx - mx) * f, my + (self.cy - my) * f
            elif op == 'pan':
                self.cx += int(args[0]) * self.pan_gain[0]
                self.cy += int(args[1]) * self.pan_gain[1]

    def measure(self):
        H = self.h * self.client[1]
        y0, y1 = self.cy - H / 2, self.cy + H / 2
        x0, x1 = self.cx - H / 6, self.cx + H / 6
        cy0, cy1 = max(y0, 0), min(y1, self.client[1])
        if cy1 - cy0 < 3:
            return None
        return {'box': [x0, cy0, x1, cy1], 'background': [110] * 3, 'height': (cy1 - cy0) / self.client[1],
                'cx': (x0 + x1) / 2, 'cy': (cy0 + cy1) / 2,
                'touchesEdge': y0 <= 2 or y1 >= self.client[1] - 2}


class AutofitTests(unittest.TestCase):
    def test_converges_with_unknown_gains(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = studio(Path(tmp))
            cam = FakeCamera((1440, 722), 0.40, 720, 180)     # small, feet near centre, like GECK's look-at
            calls = []

            class Svc:
                def call(self, op, cell, text, session=None):
                    calls.append(text)
                    cam.steps(text)
                    return {}
            s._service = Svc()
            s._measure = lambda window, client, work, n: cam.measure()
            fit = s._autofit('sess', {'id': 1}, [1440, 722], 0.86, Path(tmp))
            final = cam.measure()
            self.assertTrue(fit['converged'], fit)
            self.assertTrue(0.6 <= final['height'] <= 0.86 * 1.08, fit)
            self.assertLessEqual(abs(final['cy'] - 361), 722 * 0.025, fit)
            self.assertLessEqual(abs(final['cx'] - 720), 1440 * 0.025, fit)
            self.assertLessEqual(len(calls), 16)


if __name__ == '__main__':
    unittest.main()
