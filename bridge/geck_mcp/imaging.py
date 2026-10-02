"""macOS-side capture of GECK windows and background cut-outs (photo workflow).

The MCP server runs natively on macOS, so it can capture a single GECK window by its
CGWindowID with `screencapture -l` at full Retina resolution: no clicks, no focus change,
no UI overlays, and it works while other apps are in front. Needs Screen Recording
permission for the app hosting the server (Terminal, Codex or Claude).
"""
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
LISTER_SOURCE = ROOT / 'tools' / 'photo' / 'geck_windows.swift'
LISTER_BINARY = ROOT / 'tools' / 'photo' / 'bin' / 'geck_windows'


class ImagingError(RuntimeError):
    def __init__(self, code, message, evidence=None):
        super().__init__(message)
        self.code, self.evidence = code, evidence


def _lister_command():
    """Compiled window lister when possible (fast), else the Swift interpreter."""
    if LISTER_BINARY.exists() and LISTER_BINARY.stat().st_mtime >= LISTER_SOURCE.stat().st_mtime:
        return [str(LISTER_BINARY)]
    swiftc = shutil.which('swiftc')
    if swiftc:
        LISTER_BINARY.parent.mkdir(parents=True, exist_ok=True)
        done = subprocess.run([swiftc, '-O', '-o', str(LISTER_BINARY), str(LISTER_SOURCE)],
                              capture_output=True, text=True, timeout=120)
        if done.returncode == 0:
            return [str(LISTER_BINARY)]
    swift = shutil.which('swift')
    if not swift:
        raise ImagingError('NO_SWIFT', 'Neither swiftc nor swift is available to list windows')
    return [swift, str(LISTER_SOURCE)]


def list_geck_windows():
    done = subprocess.run(_lister_command(), capture_output=True, text=True, timeout=60)
    if done.returncode != 0:
        raise ImagingError('WINDOW_LIST_FAILED', 'Could not list GECK windows', {'stderr': done.stderr[-2000:]})
    return json.loads(done.stdout)


def render_window(cell=None):
    """The macOS window of GECK's Render Window (optionally the one showing `cell`)."""
    rows = list_geck_windows()
    if cell:
        hits = [w for w in rows if w['title'].startswith(cell + ' [')]
    else:
        hits = [w for w in rows if ' camera' in w['title'] or w['title'] == 'Render Window']
    hits = [w for w in hits if w.get('layer', 0) == 0]
    if len(hits) != 1:
        raise ImagingError('RENDER_WINDOW_NOT_UNIQUE', 'Expected one Render Window, found %d' % len(hits),
                           {'windows': [{'id': w['id'], 'title': w['title']} for w in rows]})
    return hits[0]


def capture_window(window_id, out_path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = subprocess.run(['/usr/sbin/screencapture', '-x', '-o', '-l%d' % int(window_id), str(out_path)],
                          capture_output=True, text=True, timeout=30)
    if done.returncode != 0 or not out_path.exists() or out_path.stat().st_size < 1000:
        raise ImagingError('CAPTURE_FAILED', 'screencapture failed (Screen Recording permission?)',
                           {'stderr': done.stderr[-1000:], 'returncode': done.returncode})
    return out_path


# -- pixel work (Pillow + NumPy) ------------------------------------------------------------
def _np():
    try:
        import numpy as np
        from PIL import Image
    except ImportError as e:
        raise ImagingError('MISSING_DEPENDENCY', 'Install pillow and numpy into the bridge venv') from e
    return np, Image


def load_rgb(path, top_crop=0):
    """RGB int16 array. Transparent pixels (a window capture's rounded corners) take the colour of
    the opaque bottom band, so they read as background instead of black subject pixels."""
    np, Image = _np()
    image = Image.open(path)
    if top_crop:
        image = image.crop((0, int(top_crop), image.width, image.height))
    if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
        rgba = np.asarray(image.convert('RGBA')).astype(np.int16)
        rgb, opaque = rgba[..., :3].copy(), rgba[..., 3] >= 250
        if not opaque.all():
            band = rgb[-max(2, rgb.shape[0] // 50):][opaque[-max(2, rgb.shape[0] // 50):]]
            fill = np.median(band.reshape(-1, 3), axis=0) if len(band) else np.median(rgb[opaque], axis=0)
            rgb[~opaque] = fill.astype(np.int16)
        return rgb, image
    return np.asarray(image.convert('RGB')).astype(np.int16), image


def title_bar_pixels(capture_height, client_height, capture_width, client_width):
    """Rows of macOS title bar above the client area in a `screencapture -l` image."""
    if not client_width or not client_height:
        return 0
    scale = capture_width / float(client_width)
    return max(0, int(round(capture_height - client_height * scale)))


def estimate_background(rgb):
    """Median colour of the image border (left, right and bottom bands)."""
    np, _ = _np()
    h, w, _c = rgb.shape
    band = max(2, min(h, w) // 50)
    border = np.concatenate([rgb[:, :band].reshape(-1, 3), rgb[:, -band:].reshape(-1, 3),
                             rgb[-band:, :].reshape(-1, 3)])
    return [int(v) for v in np.median(border, axis=0)]


def background_mask(rgb, bg, tolerance=30, chroma_tolerance=22):
    """True where a pixel is background: close to bg and with bg's hue balance (kills the glow halo)."""
    np, _ = _np()
    bg = np.array(bg, dtype=np.int16)
    distance = np.abs(rgb - bg).max(axis=2)
    tint = rgb - rgb.mean(axis=2, keepdims=True)
    bg_tint = bg - bg.mean()
    chroma = np.abs(tint - bg_tint).max(axis=2)
    return (distance < tolerance) & (chroma < chroma_tolerance), distance, chroma


def _shift_or(mask, radius):
    np, _ = _np()
    out = mask.copy()
    padded = np.pad(mask, radius)
    h, w = mask.shape
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            out |= padded[radius + dy:radius + dy + h, radius + dx:radius + dx + w]
    return out


def dilate(mask, radius=1):
    return _shift_or(mask, radius)


def erode(mask, radius=1):
    return ~_shift_or(~mask, radius)


def box_count(mask, radius):
    np, _ = _np()
    m = np.pad(mask.astype(np.int32), radius + 1)
    c = m.cumsum(0).cumsum(1)
    k = 2 * radius + 1
    h, w = mask.shape
    return (c[k:k + h, k:k + w] - c[:h, k:k + w] - c[k:k + h, :w] + c[:h, :w])


def subject_bbox(rgb, bg=None, tolerance=30, chroma_tolerance=22, min_neighbours=12):
    """Bounding box (x0, y0, x1, y1) of non-background pixels, ignoring isolated specks."""
    np, _ = _np()
    bg = bg or estimate_background(rgb)
    fg = ~background_mask(rgb, bg, tolerance, chroma_tolerance)[0]
    fg &= box_count(fg, 3) >= min_neighbours
    ys, xs = np.nonzero(fg)
    if len(xs) == 0:
        return None, bg
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1), bg


def cutout(src, dst, top_crop=0, bg=None, tolerance=30, chroma_tolerance=22, pad=10):
    """Write an RGBA PNG containing only the subject; background and glow become transparent."""
    np, Image = _np()
    rgb, _ = load_rgb(src, top_crop)
    bg = bg or estimate_background(rgb)
    bglike, distance, chroma = background_mask(rgb, bg, tolerance, chroma_tolerance)
    keep = ~bglike
    keep &= box_count(keep, 3) >= 12            # drop specks and JPEG-like noise
    keep = keep | (erode(dilate(keep, 1), 1) & ~bglike)   # close 1px cracks, never re-add background
    keep = keep | (box_count(keep, 3) >= 40)            # fill tiny interior holes (eye glints), not real gaps
    inner = erode(keep, 1)
    outer = dilate(keep, 1)
    score = np.clip(np.maximum((distance - tolerance / 2.0) / (tolerance * 1.3),
                               (chroma - chroma_tolerance / 2.0) / (chroma_tolerance)), 0, 1)
    alpha = np.where(inner, 1.0, np.where(keep, np.maximum(score, 0.6), np.where(outer, score * 0.8, 0.0)))
    a = alpha[..., None]
    bgv = np.array(bg, dtype=np.float64)
    colour = np.clip(np.where(a > 0, (rgb - (1 - a) * bgv) / np.maximum(a, 1e-3), 0), 0, 255)
    rgba = np.dstack([colour, alpha * 255]).astype(np.uint8)
    image = Image.fromarray(rgba, 'RGBA')
    box = image.getbbox()
    if box is None:
        raise ImagingError('EMPTY_CUTOUT', 'No subject pixels differ from the background', {'background': bg})
    box = (max(box[0] - pad, 0), max(box[1] - pad, 0), min(box[2] + pad, image.width), min(box[3] + pad, image.height))
    image = image.crop(box)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    image.save(dst)
    return {'path': str(dst), 'size': [image.width, image.height], 'background': bg,
            'cropBox': list(box), 'mode': 'RGBA'}


def crop_png(src, dst, box):
    _, Image = _np()
    image = Image.open(src)
    image.crop(tuple(int(v) for v in box)).save(dst)
    return {'path': str(dst), 'size': [int(box[2] - box[0]), int(box[3] - box[1])]}
