"""One advisory lock for every cooperating bridge process that targets the same GECK install.

macOS/Linux use flock; Windows uses msvcrt.locking (used in the Windows 11 run).
"""
from contextlib import contextmanager
import getpass
import hashlib
import json
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
    key = hashlib.sha256(os.path.normcase(str(Path(root).resolve())).encode()).hexdigest()[:24]
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


def reservation_path(root):
    """Companion to the existing advisory lock; survives a waiting client's exit."""
    key = hashlib.sha256(os.path.normcase(str(Path(root).resolve())).encode()).hexdigest()[:24]
    return Path(tempfile.gettempdir()) / ('geck-bridge-%s-%s.reservation.json' % (_user(), key))


def reservation(root, owner=None, release=False):
    """Read/set the active journal owner. Caller MUST hold bottle_lock(root).

    Empty metadata releases the reservation without deleting another process's file.
    A crashed client never silently releases an uncertain editor phase.
    """
    path = reservation_path(root)
    current = json.loads(path.read_text()) if path.exists() else None
    if owner is not None:
        if current and current != owner:
            raise RuntimeError('EDITOR_RESERVED: resume operation %s in %s' %
                               (current['operationId'], current['journal']))
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.')
        with os.fdopen(fd, 'w') as stream:
            json.dump(None if release else owner, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    return current
