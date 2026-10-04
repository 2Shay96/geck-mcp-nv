"""One advisory lock for every cooperating bridge process that targets the same GECK install.

macOS/Linux use flock; Windows uses msvcrt.locking (used in the Windows 11 run).
"""
from contextlib import contextmanager
import getpass
import hashlib
import os
from pathlib import Path
import tempfile

try:
    import fcntl
except ImportError:          # Windows
    fcntl = None
    import msvcrt


def _user():
    try:
        return str(os.getuid())
    except AttributeError:
        return getpass.getuser()


@contextmanager
def bottle_lock(root):
    key = hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()[:24]
    path = Path(tempfile.gettempdir()) / ('geck-bridge-%s-%s.lock' % (_user(), key))
    flags = os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    try:
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except (BlockingIOError, PermissionError, OSError) as error:
            raise RuntimeError('EDITOR_BUSY: another bridge operation holds the bottle lock') from error
        yield
    finally:
        os.close(fd)
