"""Decode/encode Appearance theme 'pxm#' resources (version 3, 32-bit).

Layout: 24-byte header (u16 version, u16 flags, Rect top/left/bottom/right,
u16 depth, 6 bytes ?, u16 count), then one shared or `count` 1-bit masks
(rowbytes = 2*ceil(w/16)), then `count` images of w*h RGBA bytes.
"""
import struct
from PIL import Image


def header(d):
    ver, flags, top, left, bot, right, depth = struct.unpack_from('>HH4hH', d, 0)
    count = struct.unpack_from('>H', d, 22)[0]
    return dict(ver=ver, flags=flags, w=right-left, h=bot-top, depth=depth, count=count)


def _geom(d):
    h = header(d); w, ht, n = h['w'], h['h'], h['count']
    # 32-bit RGBA pixels (flags bit 2); the header's depth field isn't
    # reliable (AsyncArrows says 16 but stores 32-bit pixels), so we check
    # the layout by size instead.
    assert h['flags'] & 4, 'only 32-bit (flags & 4) pxm# supported'
    rb = ((w + 15) // 16) * 2
    msize, isize = rb * ht, w * ht * 4
    nmask = n if 24 + n*msize + n*isize == len(d) else 1
    assert 24 + nmask*msize + n*isize == len(d), 'pxm# size mismatch'
    return w, ht, n, rb, msize, isize, nmask


def decode(d):
    """-> (images, masks): raw RGBA images and mode-'1' masks (1 or count)."""
    w, ht, n, rb, msize, isize, nmask = _geom(d)
    masks = []
    for k in range(nmask):
        m = Image.new('1', (w, ht)); px = m.load(); mo = 24 + k*msize
        for y in range(ht):
            for x in range(w):
                px[x, y] = (d[mo + y*rb + x//8] >> (7 - x % 8)) & 1
        masks.append(m)
    images = []
    for k in range(n):
        po = 24 + nmask*msize + k*isize
        images.append(Image.frombytes('RGBA', (w, ht), bytes(d[po:po+isize])))
    return images, masks


def visible(images, masks):
    """Apply masks to alpha, for viewing."""
    out = []
    for k, im in enumerate(images):
        m = masks[min(k, len(masks)-1)]
        a = Image.composite(im.getchannel('A'), Image.new('L', im.size, 0), m)
        v = im.copy(); v.putalpha(a); out.append(v)
    return out


def encode_mask(m):
    """1-bit mask image -> pxm# mask rows (rowbytes = 2*ceil(w/16))."""
    w, ht = m.size; rb = ((w + 15) // 16) * 2
    mb = bytearray(rb * ht); px = m.load()
    for y in range(ht):
        for x in range(w):
            if px[x, y]: mb[y*rb + x//8] |= 0x80 >> (x % 8)
    return bytes(mb)


def encode(template, images, masks):
    w, ht, n, rb, msize, isize, nmask = _geom(template)
    assert len(images) == n and len(masks) == nmask
    out = bytearray(template[:24])
    for m in masks:
        mb = bytearray(msize); px = m.load()
        for y in range(ht):
            for x in range(w):
                if px[x, y]: mb[y*rb + x//8] |= 0x80 >> (x % 8)
        out += mb
    for im in images:
        out += im.convert('RGBA').tobytes()
    assert len(out) == len(template)
    return bytes(out)


def sheet(images, scale=4, bg=(255, 0, 255, 255)):
    """Side-by-side preview on magenta, so transparency is obvious."""
    w = sum(i.width for i in images) + 4*(len(images)-1); h = max(i.height for i in images)
    s = Image.new('RGBA', (w, h), bg); x = 0
    for i in images:
        s.alpha_composite(i, (x, 0)); x += i.width + 4
    return s.resize((w*scale, h*scale), Image.NEAREST)
