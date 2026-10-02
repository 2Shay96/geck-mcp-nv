"""Strict, bounded traversal of Fallout: New Vegas plugin containers (24-byte headers).

This is deliberately not a general plugin editor. Compressed placed records
and extended subrecords are rejected rather than edited speculatively.
"""
from __future__ import annotations

import struct


class PluginFormatError(ValueError):
    pass


def walk(data: bytes | bytearray):
    if len(data) < 24 or data[:4] != b"TES4":
        raise PluginFormatError("Expected a Fallout: New Vegas TES4 plugin header.")

    def region(start, end, cell=None, world=None, depth=0):
        if depth > 32:
            raise PluginFormatError("Excessive group nesting.")
        pos = start
        while pos < end:
            if end - pos < 24:
                raise PluginFormatError(f"Truncated header at {pos}.")
            sig = bytes(data[pos:pos + 4])
            if any(c not in b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for c in sig):
                raise PluginFormatError(f"Invalid signature at {pos}.")
            size = struct.unpack_from("<I", data, pos + 4)[0]
            finish = pos + size if sig == b"GRUP" else pos + 24 + size
            if finish > end or finish < pos + 24:
                raise PluginFormatError(f"Invalid size at {pos}.")
            if sig == b"GRUP":
                kind = struct.unpack_from("<i", data, pos + 12)[0]
                label = struct.unpack_from("<I", data, pos + 8)[0]
                next_cell = label if kind in (6, 8, 9, 10) else cell
                next_world = label if kind == 1 else world
                yield pos, sig, size, None, next_cell, next_world
                yield from region(pos + 24, finish, next_cell, next_world, depth + 1)
            else:
                form = struct.unpack_from("<I", data, pos + 12)[0]
                yield pos, sig, size, form, cell, world
            pos = finish

    yield from region(0, len(data))


def fields(data, off, size):
    flags = struct.unpack_from("<I", data, off + 8)[0]
    if flags & 0x00040000:
        raise PluginFormatError("Compressed records are not supported by direct editing.")
    pos, end = off + 24, off + 24 + size
    while pos < end:
        if end - pos < 6:
            raise PluginFormatError(f"Truncated subrecord at {pos}.")
        sig = bytes(data[pos:pos + 4])
        length = struct.unpack_from("<H", data, pos + 4)[0]
        if sig == b"XXXX":
            raise PluginFormatError("Extended XXXX subrecords are not supported by direct editing.")
        value = pos + 6
        if value + length > end:
            raise PluginFormatError(f"Subrecord exceeds record at {pos}.")
        yield sig, value, length
        pos = value + length


def validate(data):
    entries = list(walk(data))
    seen = set()
    for off, sig, size, form, _, _ in entries:
        if sig in (b"TES4", b"REFR", b"ACHR", b"ACRE"):
            list(fields(data, off, size))
        if sig != b"GRUP" and form:
            if form in seen:
                raise PluginFormatError(f"Duplicate FormID {form:08X}.")
            seen.add(form)
    return entries
