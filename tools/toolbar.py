"""Jaguar's Finder toolbar buttons for Panther: round Back and Forward
buttons and the capsule-shaped View control, instead of Panther's square
ones.

Panther 10.3.9 draws each button from a finished PNG in Finder.rsrc
(button and symbol together, one per state): 'PNG ' 8900-8907 for Back and
Forward, 8600-8614 for the View control's three segments, each drawn into a
26x25 slot. (Panther's own Back images are 27 px wide and get squeezed into
theirs; the new ones are 26, so they draw 1:1.) Jaguar 10.2.8's Finder has the same buttons as PICTs in
English.lproj/Localized.rsrc:

  7600 / 7610      Back / Forward mask (black = opaque)
  7606 / 7614      the same at 50%, for a disabled button
  7607 / 7615      normal
  7601 / 7611      pressed (Aqua)
  7609 / 7618      pressed (Graphite)
  7602 / 7612      gray symbol, drawn with the 50% mask when disabled

  6910 / 6900 / 6920   Icon / List / Column segment masks, each over the
                       whole 76x26 capsule (segments 26, 22 and 26 px wide)
  base + 1 normal, + 2 pressed, + 3 inactive window, + 4 selected,
  + 5 selected and pressed, + 6 selected in an inactive window
  6930 / 6932 / 6934   selected (Graphite)

Every state was matched pixel for pixel against a running Jaguar Finder.
The 22 px List segment is widened to Panther's 26 px by repeating the plain
columns beside its dividers; the symbol stays as it is.

Jaguar had no Action (gear) menu, and its Path item was an icon, so the
Gear (4300-4303) and Path (7300-7303) buttons, 46x25 in Panther, are made
here in the same style: a one-piece capsule from the View control's end caps
and plain fill, with new symbols drawn as Jaguar draws the View symbols
(near-black strokes over a soft shadow, gray when inactive), where Panther
puts its own. Pressed is blue (Graphite: gray-blue), as for Back and Forward.

Input (an Apple file, not in the repo): orig/jaguar-10.2.8/Finder-Localized.rsrc,
/System/Library/CoreServices/Finder.app/Contents/Resources/English.lproj/Localized.rsrc
from 10.2.8.

build(finder_rsrc) -> {Panther 'PNG ' id: new PNG bytes}
"""
import os, sys, struct, zlib, io
sys.path.insert(0, os.path.dirname(__file__))
from rsrc import ResFile
import pict, grip
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JAGUAR_SRC = os.path.join(ROOT, 'orig', 'jaguar-10.2.8', 'Finder-Localized.rsrc')

# Panther id -> (Jaguar image, Jaguar mask)
ARROWS = {
    8900: (7607, 7600), 8901: (7601, 7600), 8902: (7602, 7606), 8903: (7609, 7600),   # Back
    8904: (7615, 7610), 8905: (7611, 7610), 8906: (7612, 7614), 8907: (7618, 7610),   # Forward
}
# Panther View segment ids: normal, inactive, pressed, selected, graphite (selected).
# Panther's 'inactive' is the selected segment in an inactive window.
SEGMENTS = [   # (Panther first id, Jaguar base, Jaguar graphite selected, mask, columns)
    (8600, 6910, 6930, 6910, (1, 27)),    # Icon
    (8605, 6900, 6932, 6900, (27, 49)),   # List
    (8610, 6920, 6934, 6920, (49, 75)),   # Column
]
SEGMENT_STATES = [1, 6, 2, 4]             # + base, in Panther's order (graphite last)
ROWS = (0, 25)                            # 24 rows of art over a clear top row, bottoms aligned
LIST_WIDEN = (28, 47)                     # plain columns beside the List segment's dividers, each repeated twice

# Gear and Path: Panther id -> (left cap, fill, right cap Jaguar images, disabled)
CAPSULE_STATES = [((6911, 6901, 6921), False),   # normal
                  ((6914, 6904, 6924), False),   # pressed (Aqua): the selected segments' blue
                  ((6913, 6903, 6923), True),    # disabled: inactive, gray symbol, at 50%
                  ((6930, 6932, 6934), False)]   # pressed (Graphite)
GEAR, PATH = 4300, 7300
LEFT_CAP, FILL_COL, RIGHT_CAP = (1, 8), 28, (69, 75)   # Jaguar columns: Icon's left end, List's fill, Column's right end
INK, INK_GRAY = 14, 122                   # Jaguar's symbol gray, active and inactive
SHADOW = (1.5, 2, 0.19)                   # symbol shadow: blur radius, drop (px), darkening (fit to Jaguar's List symbol)


def _jaguar():
    rf = ResFile(open(JAGUAR_SRC, 'rb').read())
    return lambda i: pict.decode(rf.res[('PICT', i)]['data'])


def _rgba(im, mask, box):
    """Jaguar image + mask (black = opaque) -> RGBA, cropped to box."""
    a = mask.convert('L').point(lambda v: 255 - v)
    out = im.convert('RGB').copy(); out.putalpha(a)
    return out.crop(box)


def _widen(seg, cols):
    """Repeat the given columns (relative to seg) twice each."""
    w, h = seg.size
    parts, x = [], 0
    for c in cols:
        parts += [seg.crop((x, 0, c + 1, h))] + [seg.crop((c, 0, c + 1, h))] * 2
        x = c + 1
    parts.append(seg.crop((x, 0, w, h)))
    out = Image.new('RGBA', (sum(p.width for p in parts), h)); x = 0
    for p in parts:
        out.paste(p, (x, 0)); x += p.width
    return out


def _capsule(j, ids):
    """A plain 46x25 capsule: Jaguar's left and right ends with the fill between."""
    (l, f, r), (ml, mf, mr) = ids, (6910, 6900, 6920)
    left = _rgba(j(l), j(ml), (LEFT_CAP[0], ROWS[0], LEFT_CAP[1], ROWS[1]))
    right = _rgba(j(r), j(mr), (RIGHT_CAP[0], ROWS[0], RIGHT_CAP[1], ROWS[1]))
    fill = _rgba(j(f), j(mf), (FILL_COL, ROWS[0], FILL_COL + 1, ROWS[1]))
    out = Image.new('RGBA', (46, 25))
    out.paste(left, (0, 0)); out.paste(right, (46 - right.width, 0))
    for x in range(left.width, 46 - right.width):
        out.paste(fill, (x, 0))
    return out


def _symbol(kind):
    """Coverage (L, 46x25) of the symbol at Panther's place: the gear (13 px,
    8 teeth, centered at 19,12) with a 5x3 pop-up triangle at 30-34 x 11-13,
    or the Path's three staggered 1 px lines (as Jaguar's List symbol draws
    its lines) with Jaguar's 7x4 triangle at 30-36 x 11-14."""
    from PIL import ImageDraw
    import math
    k = 8                                   # supersampled, for the gear's curves
    big = Image.new('L', (46 * k, 25 * k)); d = ImageDraw.Draw(big)
    if kind == GEAR:
        cx, cy = 19.5 * k, 12.5 * k
        body, tip, tooth, hub = 4.6, 6.6, 1.8, 2.4
        d.ellipse((cx - body * k, cy - body * k, cx + body * k, cy + body * k), fill=255)
        for t in range(8):                  # teeth, 1.8 px wide, out to 6.6 px
            a = math.pi * t / 4
            pts = []
            for rr, side in ((body - 1, -1), (tip, -1), (tip, 1), (body - 1, 1)):
                w = tooth / 2 * side
                pts.append((cx + rr * k * math.cos(a) - w * k * math.sin(a), cy + rr * k * math.sin(a) + w * k * math.cos(a)))
            d.polygon(pts, fill=255)
        d.ellipse((cx - hub * k, cy - hub * k, cx + hub * k, cy + hub * k), fill=0)
        triangle = (5, 3, 1)
    else:                                   # 10 px lines, 3 apart
        for x, y in ((10, 9), (13, 12), (16, 15)):
            d.rectangle((x * k, y * k, (x + 10) * k - 1, (y + 1) * k - 1), fill=255)
        triangle = (7, 5, 3, 1)
    small = big.resize((46, 25), Image.BOX)
    tri = ImageDraw.Draw(small)
    for n, w in enumerate(triangle):
        tri.line((30 + n, 11 + n, 30 + n + w - 1, 11 + n), fill=255)
    return small


def _capsule_button(j, kind, ids, disabled):
    from PIL import ImageFilter
    import numpy as np
    body = _capsule(j, ids)
    sym = _symbol(kind)
    blur, drop, dark = SHADOW
    sh = sym.transform(sym.size, Image.AFFINE, (1, 0, 0, 0, 1, -drop)).filter(ImageFilter.GaussianBlur(blur))
    rgb = np.array(body).astype(float)
    g = np.array(sym).astype(float)[..., None] / 255
    s = np.array(sh).astype(float)[..., None] / 255 * dark * (0.5 if disabled else 1)
    ink = INK_GRAY if disabled else INK
    rgb[..., :3] = rgb[..., :3] * (1 - s)
    rgb[..., :3] = rgb[..., :3] * (1 - g) + ink * g
    if disabled:
        rgb[..., 3] *= 0.5
    return Image.fromarray(np.clip(rgb + 0.5, 0, 255).astype('uint8'), 'RGBA')


def png(im, like):
    """RGBA PNG carrying `like`'s pHYs, gAMA and cHRM chunks, so CoreGraphics
    treats it as it does Apple's original."""
    w, h = im.size
    raw = b''.join(b'\0' + im.crop((0, y, w, y + 1)).tobytes() for y in range(h))
    keep = []
    k = 8
    while k + 8 <= len(like):           # (some originals carry trailing bytes after IEND)
        n = struct.unpack_from('>I', like, k)[0]; kind = like[k + 4:k + 8]
        if kind in (b'pHYs', b'gAMA'):
            keep.append((kind, like[k + 8:k + 8 + n]))
        if kind == b'IEND':
            break
        k += 12 + n
    return (b'\x89PNG\r\n\x1a\n' + grip.chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
            + b''.join(grip.chunk(k, b) for k, b in keep)
            + grip.chunk(b'IDAT', zlib.compress(raw, 9)) + grip.chunk(b'IEND', b''))


def images():
    """{Panther id: RGBA image}"""
    j = _jaguar(); out = {}
    for pid, (img, msk) in ARROWS.items():
        # the circle (columns 2-25) centered in the 26 px slot
        out[pid] = _rgba(j(img), j(msk), (1, ROWS[0], 27, ROWS[1]))
    for first, base, graphite, msk, (c0, c1) in SEGMENTS:
        for k, src in enumerate([base + s for s in SEGMENT_STATES] + [graphite]):
            seg = _rgba(j(src), j(msk), (c0, ROWS[0], c1, ROWS[1]))
            if seg.width < 26:
                seg = _widen(seg, [c - c0 for c in LIST_WIDEN])
            assert seg.size == (26, 25), seg.size
            out[first + k] = seg
    for kind in (GEAR, PATH):
        for k, (ids, disabled) in enumerate(CAPSULE_STATES):
            out[kind + k] = _capsule_button(j, kind, ids, disabled)
    return out


def build(finder_rsrc):
    rf = ResFile(finder_rsrc); out = {}
    for pid, im in images().items():
        like = rf.res[('PNG ', pid)]['data']
        assert Image.open(io.BytesIO(like)).height == im.height == 25, pid
        out[pid] = png(im, like)
    return out


if __name__ == '__main__':      # toolbar.py <out dir>: write the new images as plain PNGs
    d = sys.argv[1]; os.makedirs(d, exist_ok=True)
    ims = images()
    for pid, im in ims.items():
        im.save(os.path.join(d, '%d.png' % pid))
