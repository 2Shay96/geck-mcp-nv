"""Print the raw group/record tree of a plugin with size checks: python3 tools/esp_tree.py FILE"""
import struct, sys
data = open(sys.argv[1], 'rb').read()
def walk(off, end, depth):
    while off < end:
        tag = data[off:off+4].decode('latin1')
        size = struct.unpack_from('<I', data, off+4)[0]
        if tag == 'GRUP':
            label = data[off+8:off+12]; gtype = struct.unpack_from('<i', data, off+12)[0]
            lab = label.decode('latin1') if gtype == 0 else label[::-1].hex()
            bad = '' if off + size <= end else '  !! OVERRUNS PARENT'
            print('  ' * depth + 'GRUP type=%d label=%s size=%d%s' % (gtype, lab, size, bad))
            walk(off + 24, off + size, depth + 1)
            off += size
        else:
            flags, fid = struct.unpack_from('<II', data, off+8)
            print('  ' * depth + '%s %08X flags=%x size=%d' % (tag, fid, flags, size))
            off += 24 + size
    if off != end:
        print('  ' * depth + '!! misaligned: ended at %d, expected %d' % (off, end))
walk(0, len(data), 0)
