"""Decode the bitmap in a QuickDraw PICT (version 2), enough for Jaguar's
Finder art: one DirectBitsRect (0x009A, 32-bit, planar or chunky) or
PackBitsRect (0x0098, indexed) per picture.

decode(data) -> PIL RGB image of the first bitmap.
"""
import struct
from PIL import Image


def _unpackbits(b, n):
    out, i = bytearray(), 0
    while len(out) < n and i < len(b):
        c = b[i]; i += 1
        if c < 128:
            out += b[i:i + c + 1]; i += c + 1
        elif c > 128:
            out += bytes([b[i]]) * (257 - c); i += 1
    return bytes(out[:n])


def _rows(d, p, rb, h, n, packed=True):
    """h PackBits rows of n bytes each (raw rows when rowBytes < 8 or unpacked)."""
    rows = []
    for _ in range(h):
        if rb < 8 or not packed:
            rows.append(d[p:p + rb]); p += rb
            continue
        if rb > 250:
            k = struct.unpack_from('>H', d, p)[0]; p += 2
        else:
            k = d[p]; p += 1
        rows.append(_unpackbits(d[p:p + k], n)); p += k
    return rows, p


def decode(d):
    p = 10                                     # picSize, picFrame
    assert d[p:p + 4] == b'\x00\x11\x02\xff', 'not a version 2 PICT'
    p += 4
    while p < len(d):
        p += p & 1
        op = struct.unpack_from('>H', d, p)[0]; p += 2
        if op == 0x0C00:                       # HeaderOp
            p += 24
        elif op in (0x0000, 0x001E):           # NOP, DefHilite
            pass
        elif op == 0x0001:                     # Clip region
            p += struct.unpack_from('>H', d, p)[0]
        elif op == 0x00A0:                     # ShortComment
            p += 2
        elif op == 0x00A1:                     # LongComment
            p += 4 + struct.unpack_from('>H', d, p + 2)[0]
        elif op == 0x009A:                     # DirectBitsRect
            p += 4                             # baseAddr
            rb, t, l, b, r = struct.unpack_from('>H4h', d, p); rb &= 0x3fff; p += 10
            _, packtype = struct.unpack_from('>hh', d, p); p += 16
            _, pixsize, cmpcount = struct.unpack_from('>hhh', d, p); p += 20
            assert pixsize == 32, 'only 32-bit direct pixels'
            p += 18                            # srcRect, dstRect, mode
            w, h = r - l, b - t
            n = w * cmpcount if packtype == 4 else rb
            rows, p = _rows(d, p, rb, h, n, packed=packtype != 1)   # 1: unpacked
            im = Image.new('RGB', (w, h)); px = im.load()
            for y, row in enumerate(rows):
                for x in range(w):
                    if packtype == 4:          # planar: (alpha), red, green, blue
                        o = (cmpcount - 3) * w
                        px[x, y] = (row[o + x], row[o + w + x], row[o + 2 * w + x])
                    else:                      # chunky xRGB
                        px[x, y] = tuple(row[4 * x + 1:4 * x + 4])
            return im
        elif op == 0x0098:                     # PackBitsRect (indexed PixMap)
            rb = struct.unpack_from('>H', d, p)[0]; p += 2
            assert rb & 0x8000, 'only PixMaps'
            rb &= 0x3fff
            t, l, b, r = struct.unpack_from('>4h', d, p); p += 8
            pixsize = struct.unpack_from('>h', d, p + 18)[0]; p += 36   # rest of the PixMap
            cnt = struct.unpack_from('>h', d, p + 6)[0]; p += 8   # ctSeed, ctFlags, ctSize
            pal = []
            for _ in range(cnt + 1):
                _, cr, cg, cb = struct.unpack_from('>4H', d, p); p += 8
                pal.append((cr >> 8, cg >> 8, cb >> 8))
            p += 18
            w, h = r - l, b - t
            rows, p = _rows(d, p, rb, h, rb)
            im = Image.new('RGB', (w, h)); px = im.load()
            per = 8 // pixsize
            for y, row in enumerate(rows):
                for x in range(w):
                    v = (row[x // per] >> ((per - 1 - x % per) * pixsize)) & ((1 << pixsize) - 1)
                    px[x, y] = pal[v]
            return im
        else:
            raise ValueError('PICT opcode %04x' % op)
    raise ValueError('no bitmap in PICT')
