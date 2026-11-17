"""The sidebar divider's look: the column view's divider (as in Jaguar), a
15 px gray gradient with a || grip near its bottom, instead of Panther's
MetalSplitterDimple, a dark dot shaded as a hole in brushed metal.

The grip image is 'PNG ' 8800 in Finder.app/Contents/Resources/Finder.rsrc.
patch.py ('gap') makes the divider draw it from its bottom edge, clipped to
the divider, one column out on either side of its 13 px frame; so a 15 x 2048
image with the grip in its bottom rows paints the whole divider. Values are
measured from a column view divider on a running Panther Finder. The new PNG
is padded to the original's exact length, so the resource file is edited in
place.

usage: grip.py <Finder.rsrc> <out.rsrc> [preview.png]
"""
import sys, os, io, struct, zlib
sys.path.insert(0, os.path.dirname(__file__))
from rsrc import ResFile

GRIP_ID = 8800          # 'PNG ' MetalSplitterDimple
# The column view divider, left to right (Panther 10.3.9 and Jaguar alike).
GRADIENT = [212, 217, 222, 229, 233, 239, 243, 247, 250, 252, 253, 253, 251, 248, 245]
RIDGES = [(6, 121), (9, 126)]   # the grip: two 1px ridges (column, gray)
RIDGE_ROWS = 7                  # ridge length
RIDGE_GAP = 5                   # rows below the grip: 4 in the window, as in the column view, + the divider row below the window
HEIGHT = 2048                   # taller than any divider (clipped to it)


def chunk(kind, body):
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xffffffff)


def chunks(png):
    out, k = [], 8
    while k < len(png):
        n = struct.unpack_from('>I', png, k)[0]
        out.append((png[k + 4:k + 8], png[k + 8:k + 8 + n]))
        k += 12 + n
    return out


def divider_png(like):
    """The divider as an 8-bit gray PNG carrying `like`'s gAMA and pHYs chunks
    (the same treatment by CoreGraphics as the original), padded
    with a tEXt chunk to len(like) bytes."""
    w = len(GRADIENT)
    plain = bytes(GRADIENT)
    grip = bytearray(plain)
    for x, g in RIDGES:
        grip[x] = g
    rows = [plain] * (HEIGHT - RIDGE_GAP - RIDGE_ROWS) + [bytes(grip)] * RIDGE_ROWS + [plain] * RIDGE_GAP
    # 8-bit gray, opaque; filter 'Up' (2): rows equal to the one above are zeros
    raw, prev = b'', bytes(w)
    for r in rows:
        raw += b'\2' + bytes((a - b) & 0xff for a, b in zip(r, prev))
        prev = r
    # (cHRM, the primaries, is left out: it means nothing for gray, and the
    # image only fits the original's length without it)
    keep = [c for c in chunks(like) if c[0] in (b'pHYs', b'gAMA')]
    head = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, HEIGHT, 8, 0, 0, 0, 0))
    head += b''.join(chunk(k, b) for k, b in keep)
    tail = chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')
    pad = len(like) - len(head) - len(tail) - 12 - len(b'Comment\0')
    assert pad >= 0, 'divider PNG is %d bytes over the original' % -pad
    png = head + chunk(b'tEXt', b'Comment\0' + b' ' * pad) + tail
    assert len(png) == len(like)
    return png


def build(finder_rsrc):
    """Finder.rsrc bytes with the grip replaced (same length)."""
    rf = ResFile(finder_rsrc)
    like = rf.res[('PNG ', GRIP_ID)]['data']
    png = divider_png(like)
    out = rf.patched_in_place({('PNG ', GRIP_ID): png})
    assert ResFile(out).res[('PNG ', GRIP_ID)]['data'] == png
    return out


if __name__ == '__main__':
    out = build(open(sys.argv[1], 'rb').read())
    open(sys.argv[2], 'wb').write(out)
    if len(sys.argv) > 3:
        from PIL import Image
        Image.open(io.BytesIO(ResFile(out).res[('PNG ', GRIP_ID)]['data'])).save(sys.argv[3])
