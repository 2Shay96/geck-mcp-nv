"""Native Windows capture of GECK's Render Window (geck_render_capture on Windows).

Finds the one visible top-level `MonitorClass` window owned by GECK.exe and copies its client area with
PrintWindow(PW_CLIENTONLY | PW_RENDERFULLCONTENT), which also works when other windows cover it. If that
yields a flat image, it falls back to copying the window's screen area, but only when no other window covers
the Render Window (a screen copy of a covered window shows the covering window). No clicks, no focus change.
Standard library ctypes only; Pillow + NumPy write and check the PNG.
"""
import ctypes
from ctypes import wintypes
from pathlib import Path
import time

from .imaging import ImagingError, _np

PW_CLIENTONLY, PW_RENDERFULLCONTENT = 0x1, 0x2
SRCCOPY, CAPTUREBLT = 0x00CC0020, 0x40000000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', wintypes.DWORD), ('biWidth', wintypes.LONG), ('biHeight', wintypes.LONG),
                ('biPlanes', wintypes.WORD), ('biBitCount', wintypes.WORD), ('biCompression', wintypes.DWORD),
                ('biSizeImage', wintypes.DWORD), ('biXPelsPerMeter', wintypes.LONG),
                ('biYPelsPerMeter', wintypes.LONG), ('biClrUsed', wintypes.DWORD),
                ('biClrImportant', wintypes.DWORD)]


def _api():
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    dwmapi = ctypes.WinDLL('dwmapi')
    H = wintypes.HANDLE
    sig = [
        (user32.EnumWindows, wintypes.BOOL, [ctypes.c_void_p, wintypes.LPARAM]),
        (user32.GetWindowThreadProcessId, wintypes.DWORD, [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]),
        (user32.GetClassNameW, ctypes.c_int, [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]),
        (user32.GetWindowTextW, ctypes.c_int, [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]),
        (user32.IsWindowVisible, wintypes.BOOL, [wintypes.HWND]),
        (user32.GetParent, wintypes.HWND, [wintypes.HWND]),
        (user32.GetClientRect, wintypes.BOOL, [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]),
        (user32.ClientToScreen, wintypes.BOOL, [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]),
        (user32.GetDC, wintypes.HDC, [wintypes.HWND]),
        (user32.ReleaseDC, ctypes.c_int, [wintypes.HWND, wintypes.HDC]),
        (user32.PrintWindow, wintypes.BOOL, [wintypes.HWND, wintypes.HDC, wintypes.UINT]),
        (user32.WindowFromPoint, wintypes.HWND, [wintypes.POINT]),
        (user32.SetThreadDpiAwarenessContext, ctypes.c_void_p, [ctypes.c_void_p]),
        (user32.GetWindow, wintypes.HWND, [wintypes.HWND, wintypes.UINT]),
        (user32.RedrawWindow, wintypes.BOOL, [wintypes.HWND, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]),
        (user32.IsIconic, wintypes.BOOL, [wintypes.HWND]),
        (user32.GetWindowLongW, ctypes.c_long, [wintypes.HWND, ctypes.c_int]),
        (dwmapi.DwmGetWindowAttribute, ctypes.c_long, [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]),
        (user32.GetAncestor, wintypes.HWND, [wintypes.HWND, wintypes.UINT]),
        (gdi32.CreateCompatibleDC, wintypes.HDC, [wintypes.HDC]),
        (gdi32.CreateCompatibleBitmap, wintypes.HBITMAP, [wintypes.HDC, ctypes.c_int, ctypes.c_int]),
        (gdi32.SelectObject, wintypes.HGDIOBJ, [wintypes.HDC, wintypes.HGDIOBJ]),
        (gdi32.DeleteObject, wintypes.BOOL, [wintypes.HGDIOBJ]),
        (gdi32.DeleteDC, wintypes.BOOL, [wintypes.HDC]),
        (gdi32.BitBlt, wintypes.BOOL, [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                       wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]),
        (gdi32.GetDIBits, ctypes.c_int, [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                                         ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]),
        (kernel32.OpenProcess, H, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]),
        (kernel32.CloseHandle, wintypes.BOOL, [H]),
        (kernel32.QueryFullProcessImageNameW, wintypes.BOOL, [H, wintypes.DWORD, wintypes.LPWSTR,
                                                              ctypes.POINTER(wintypes.DWORD)]),
    ]
    for fn, restype, argtypes in sig:
        fn.restype, fn.argtypes = restype, argtypes
    user32.DwmGetWindowAttribute = dwmapi.DwmGetWindowAttribute      # one handle for the window helpers below
    return user32, gdi32, kernel32


def _process_image(kernel32, pid):
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        return buf.value if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)) else None
    finally:
        kernel32.CloseHandle(handle)


def geck_windows(class_name=None):
    """Top-level windows of GECK.exe processes: [{hwnd, pid, class, title, visible}]."""
    user32, _, kernel32 = _api()
    rows, images = [], {}

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in images:
            images[pid.value] = _process_image(kernel32, pid.value)
        image = images[pid.value] or ''
        if Path(image).name.lower() != 'geck.exe':
            return True
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if class_name and cls.value != class_name:
            return True
        title = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title, 512)
        rows.append({'hwnd': hwnd, 'pid': pid.value, 'class': cls.value, 'title': title.value,
                     'visible': bool(user32.IsWindowVisible(hwnd))})
        return True

    user32.EnumWindows(ctypes.cast(visit, ctypes.c_void_p), 0)
    return rows


def render_window():
    rows = geck_windows('MonitorClass')
    pids = {r['pid'] for r in rows}
    if len(pids) > 1:
        raise ImagingError('RENDER_WINDOW_NOT_UNIQUE', 'More than one GECK process is running')
    visible = [r for r in rows if r['visible']]
    if len(visible) != 1:
        raise ImagingError('RENDER_WINDOW_NOT_UNIQUE' if visible else 'RENDER_WINDOW_HIDDEN',
                           'Expected one visible Render Window, found %d (%d hidden); try geck_show_windows'
                           % (len(visible), len(rows) - len(visible)),
                           {'windows': [{k: r[k] for k in ('class', 'title', 'visible')} for r in rows]})
    return visible[0]


def _visible_bounds(user32, h):
    rect = wintypes.RECT()
    if user32.DwmGetWindowAttribute(h, 9, ctypes.byref(rect), ctypes.sizeof(rect)) != 0:   # EXTENDED_FRAME_BOUNDS
        user32.GetWindowRect(h, ctypes.byref(rect))
    return rect


def covering_windows(user32, hwnd, width, height):
    """Visible, uncloaked windows above the Render Window in z-order that overlap its client area (toasts,
    other apps, GECK dialogs). WindowFromPoint alone misses windows that do not take mouse input."""
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    left, top, right, bottom = origin.x, origin.y, origin.x + width, origin.y + height
    rows, h, seen = [], user32.GetWindow(hwnd, 3), 0                  # GW_HWNDPREV: the window above
    while h and seen < 2000:
        seen += 1
        cloaked = wintypes.DWORD(0)
        user32.DwmGetWindowAttribute(h, 14, ctypes.byref(cloaked), 4)  # DWMWA_CLOAKED
        if (user32.IsWindowVisible(h) and not user32.IsIconic(h) and not cloaked.value
                and not user32.GetWindowLongW(h, -20) & 0x20):          # WS_EX_TRANSPARENT: click-through overlay
            r = _visible_bounds(user32, h)
            if r.left < right and r.right > left and r.top < bottom and r.bottom > top and r.right > r.left:
                cls, title = ctypes.create_unicode_buffer(128), ctypes.create_unicode_buffer(128)
                user32.GetClassNameW(h, cls, 128)
                user32.GetWindowTextW(h, title, 128)
                rows.append({'class': cls.value, 'title': title.value[:60]})
        h = user32.GetWindow(h, 3)
    return rows


def unobscured(user32, hwnd, width, height):
    """True when the window itself is on top at the centre and near the corners of its client area."""
    for fx, fy in ((0.5, 0.5), (0.05, 0.05), (0.95, 0.05), (0.05, 0.95), (0.95, 0.95)):
        point = wintypes.POINT(int(width * fx), int(height * fy))
        user32.ClientToScreen(hwnd, ctypes.byref(point))
        hit = user32.WindowFromPoint(point)
        if not hit or user32.GetAncestor(hit, 2) != hwnd:        # GA_ROOT
            return False
    return True


def _bitmap_bytes(gdi32, memdc, bitmap, width, height):
    header = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=width, biHeight=-height,
                              biPlanes=1, biBitCount=32, biCompression=0)
    info = (ctypes.c_byte * (ctypes.sizeof(BITMAPINFOHEADER) + 16))()
    ctypes.memmove(info, ctypes.byref(header), ctypes.sizeof(BITMAPINFOHEADER))
    buf = ctypes.create_string_buffer(width * height * 4)
    if gdi32.GetDIBits(memdc, bitmap, 0, height, buf, info, 0) != height:
        raise ImagingError('CAPTURE_FAILED', 'GetDIBits failed')
    return buf.raw


def image_stats(image):
    np, _ = _np()
    rgb = np.asarray(image.convert('RGB')).astype(np.float32)
    return {'mean': round(float(rgb.mean()), 2), 'stdev': round(float(rgb.std()), 2),
            'distinctColours': int(len(np.unique(rgb.reshape(-1, 3)[::max(1, rgb.size // 3 // 20000)], axis=0)))}


def is_blank(stats):
    """A (nearly) uniform image, e.g. black, white or the window background, is not a rendered cell."""
    return stats['stdev'] < 6 or stats['distinctColours'] < 8


def _dpi_context(user32, context):
    """Switch this thread's DPI awareness; returns the previous context (None if unsupported)."""
    try:
        return user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(context))
    except AttributeError:          # before Windows 10 1607
        return None


def capture(window, out_path, repaint=False):
    """PNG of the window's client area. Returns {path, size, client, method, stats, blank, attempts}.

    1. PrintWindow in the Render Window's own DPI context: GECK is DPI-unaware, so this gives the image at the
       size GECK renders it (the client size GECK reports), even when other windows cover it.
    2. If that is blank: a screen copy in per-monitor-aware context (physical pixels, so on a scaled display it
       is larger), only when nothing covers the Render Window. A DPI-unaware screen copy on a scaled display
       copies the wrong area (job 052 got GECK's toolbar).
    """
    _, Image = _np()
    user32, _, _ = _api()
    hwnd = window['hwnd']
    try:
        user32.GetWindowDpiAwarenessContext.restype = ctypes.c_void_p
        user32.GetWindowDpiAwarenessContext.argtypes = [wintypes.HWND]
        own = user32.GetWindowDpiAwarenessContext(hwnd)
    except AttributeError:
        own = None
    attempts, image, stats = [], None, None
    if repaint:
        # PrintWindow can return only the window background (flat grey) for GECK's Direct3D view (jobs 054/055);
        # ask GECK to repaint and give it time to draw before the next try.
        user32.RedrawWindow(hwnd, None, None, 0x0001 | 0x0100 | 0x0080)    # INVALIDATE | UPDATENOW | ALLCHILDREN
        time.sleep(1.5)
    for method, context in (('PrintWindow', own), ('screen', -4)):      # -4: PER_MONITOR_AWARE_V2
        previous = _dpi_context(user32, context) if context else None
        try:
            got = _grab(hwnd, method)
        finally:
            if previous:
                _dpi_context(user32, previous)
        attempts.append(got['attempt'])
        if got['image'] is not None:
            image, stats, client = got['image'], got['attempt']['stats'], got['client']
            if not is_blank(stats):
                break
    if image is None:
        raise ImagingError('CAPTURE_FAILED', 'PrintWindow and screen copy both failed', {'attempts': attempts})
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)
    return {'path': str(out_path), 'size': [image.width, image.height], 'client': client,
            'method': attempts[-1]['method'], 'attempts': attempts, 'stats': stats, 'blank': is_blank(stats)}


def _grab(hwnd, method):
    """One capture attempt in the calling thread's DPI context: {image, client, attempt}."""
    _, Image = _np()
    user32, gdi32, _ = _api()
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise ImagingError('CAPTURE_FAILED', 'GetClientRect failed')
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width < 8 or height < 8:
        raise ImagingError('RENDER_WINDOW_EMPTY', 'Render Window client area is %dx%d' % (width, height))
    attempt = {'method': method, 'client': [width, height]}
    if method == 'screen':
        covered = covering_windows(user32, hwnd, width, height)
        if covered or not unobscured(user32, hwnd, width, height):
            # A screen copy would show whatever covers the Render Window (seen: the Claude app, a toast).
            attempt.update(ok=False, skipped='Render Window is covered', coveredBy=covered[:5])
            return {'image': None, 'client': [width, height], 'attempt': attempt}
    screen = user32.GetDC(None)
    memdc = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
    old = gdi32.SelectObject(memdc, bitmap)
    try:
        if method == 'PrintWindow':
            ok = user32.PrintWindow(hwnd, memdc, PW_CLIENTONLY | PW_RENDERFULLCONTENT)
        else:
            origin = wintypes.POINT(0, 0)
            user32.ClientToScreen(hwnd, ctypes.byref(origin))
            ok = gdi32.BitBlt(memdc, 0, 0, width, height, screen, origin.x, origin.y, SRCCOPY | CAPTUREBLT)
        image = None
        if ok:
            raw = _bitmap_bytes(gdi32, memdc, bitmap, width, height)
            image = Image.frombuffer('RGB', (width, height), raw, 'raw', 'BGRX', 0, 1)
            attempt['stats'] = image_stats(image)
        attempt['ok'] = bool(ok)
    finally:
        gdi32.SelectObject(memdc, old)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(None, screen)
    return {'image': image, 'client': [width, height], 'attempt': attempt}
