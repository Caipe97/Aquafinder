"""The sidebar divider's grip: Jaguar's Aqua splitter ridges instead of
Panther's MetalSplitterDimple, a dark dot shaded as a hole in brushed metal
that looks like a smudge on the Aqua Finder's white divider.

The grip is 'PNG ' 8800 in Finder.app/Contents/Resources/Finder.rsrc. The
divider centers the image by its own size (CGImageGetWidth/Height), so a
different size needs no code change. The new PNG is padded to the original's
exact length, so the resource file is edited in place.

usage: grip.py <Finder.rsrc> <jaguar Extras.rsrc> <out.rsrc> [preview.png]
"""
import sys, os, io, struct, zlib
sys.path.insert(0, os.path.dirname(__file__))
from rsrc import ResFile
import pxm

GRIP_ID = 8800          # 'PNG ' MetalSplitterDimple
RIDGES_ID = 4520        # Jaguar theme pxm# 'Pane Splitter Ridges V' (3x10), state 0 = active


def chunk(kind, body):
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xffffffff)


def chunks(png):
    out, k = [], 8
    while k < len(png):
        n = struct.unpack_from('>I', png, k)[0]
        out.append((png[k + 4:k + 8], png[k + 8:k + 8 + n]))
        k += 12 + n
    return out


def unpremultiply(im):
    im = im.convert('RGBA')
    p = im.load()
    for y in range(im.size[1]):
        for x in range(im.size[0]):
            r, g, b, a = p[x, y]
            if a:
                p[x, y] = tuple(min(255, c * 255 // a) for c in (r, g, b)) + (a,)
    return im


def ridges_png(jaguar_extras, like):
    """Jaguar's ridges as an 8-bit RGBA PNG carrying `like`'s colour chunks
    (gAMA, cHRM, pHYs: the same treatment by CoreGraphics as the original),
    padded with a tEXt chunk to len(like) bytes."""
    src = ResFile(open(jaguar_extras, 'rb').read())
    ims, _ = pxm.decode(src.res[('pxm#', RIDGES_ID)]['data'])
    im = unpremultiply(ims[0])                      # theme pixels are premultiplied
    w, h = im.size
    raw = b''.join(b'\0' + im.tobytes()[y * w * 4:(y + 1) * w * 4] for y in range(h))
    keep = [c for c in chunks(like) if c[0] in (b'pHYs', b'gAMA', b'cHRM')]
    head = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
    head += b''.join(chunk(k, b) for k, b in keep)
    tail = chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')
    pad = len(like) - len(head) - len(tail) - 12 - len(b'Comment\0')
    assert pad >= 0, 'ridges PNG is %d bytes over the original' % -pad
    png = head + chunk(b'tEXt', b'Comment\0' + b' ' * pad) + tail
    assert len(png) == len(like)
    return png, im


def build(finder_rsrc, jaguar_extras):
    """Finder.rsrc bytes with the grip replaced (same length)."""
    rf = ResFile(finder_rsrc)
    like = rf.res[('PNG ', GRIP_ID)]['data']
    png, _ = ridges_png(jaguar_extras, like)
    out = rf.patched_in_place({('PNG ', GRIP_ID): png})
    assert ResFile(out).res[('PNG ', GRIP_ID)]['data'] == png
    return out


if __name__ == '__main__':
    out = build(open(sys.argv[1], 'rb').read(), sys.argv[2])
    open(sys.argv[3], 'wb').write(out)
    if len(sys.argv) > 4:
        from PIL import Image
        Image.open(io.BytesIO(ResFile(out).res[('PNG ', GRIP_ID)]['data'])).save(sys.argv[4])
