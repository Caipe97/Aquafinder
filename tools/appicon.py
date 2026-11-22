"""Aquafinder's own icon: a glass of water in front of an Aqua window with a
pinstriped title bar and a sidebar. Drawn here from scratch (no Apple art).

Writes gui/Aquafinder.icns in the classic formats Panther reads (it32/t8mk
128x128, ih32/h8mk 48, il32/l8mk 32, is32/s8mk 16, plus ICN#/ics#), which
native-build.sh copies into the app, and build/appicon/icon-<size>.png.

  python3 tools/appicon.py
"""
import os, struct
from PIL import Image, ImageDraw, ImageFilter, ImageChops

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = 1024                      # drawing size; 128 px is S/8


def rrect(size, box, r, fill):
    m = Image.new('L', size, 0)
    ImageDraw.Draw(m).rounded_rectangle(box, r, fill=fill)
    return m


def vgrad(size, top, bottom, y0=0, y1=None):
    """Vertical gradient image (RGBA) from top colour at y0 to bottom at y1."""
    w, h = size
    y1 = h if y1 is None else y1
    g = Image.new('RGBA', size)
    px = g.load()
    for y in range(h):
        t = min(max((y - y0) / max(y1 - y0, 1), 0), 1)
        c = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
        for x in range(w):
            px[x, y] = c
    return g


def fill(canvas, mask, colour):
    """Paint colour (RGBA or an image) through mask, scaling only its alpha
    (Image.composite would blend the colour towards transparent black)."""
    layer = colour.copy() if isinstance(colour, Image.Image) else Image.new('RGBA', canvas.size, colour)
    layer.putalpha(ImageChops.multiply(layer.split()[3], mask))
    canvas.alpha_composite(layer)


def shadow(canvas, mask, offset, blur, alpha):
    m = Image.new('L', canvas.size, 0)
    m.paste(mask, offset)
    m = m.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: v * alpha // 255)
    fill(canvas, m, (0, 0, 0, 255))


def gem(canvas, c, r, colour, dark):
    """A glossy Aqua button: coloured ball, darker rim, white highlight."""
    x, y = c
    d = ImageDraw.Draw(canvas)
    d.ellipse((x - r - 3, y - r - 3, x + r + 3, y + r + 3), fill=dark)
    ball = Image.new('L', canvas.size, 0)
    ImageDraw.Draw(ball).ellipse((x - r, y - r, x + r, y + r), fill=255)
    fill(canvas, ball, vgrad(canvas.size, tuple(min(255, v + 70) for v in colour[:3]) + (255,),
                             colour, y - r, y + r))
    hi = Image.new('L', canvas.size, 0)
    ImageDraw.Draw(hi).ellipse((x - r * .62, y - r * .9, x + r * .62, y - r * .05), fill=200)
    fill(canvas, hi.filter(ImageFilter.GaussianBlur(r * .12)), (255, 255, 255, 255))


def window(canvas):
    """The Aqua window, top right."""
    x0, y0, x1, y1 = 40, 96, 780, 736
    bar = 112
    win = rrect(canvas.size, (x0, y0, x1, y1), 34, 255)
    shadow(canvas, win, (0, 22), 26, 120)
    fill(canvas, win, (120, 120, 120, 255))                          # 4 px dark frame
    inner = rrect(canvas.size, (x0 + 4, y0 + 4, x1 - 4, y1 - 4), 30, 255)
    # pinstripes: 8 px rows (1 px at 128) alternating white and light gray
    stripes = Image.new('RGBA', canvas.size, (255, 255, 255, 255))
    d = ImageDraw.Draw(stripes)
    for y in range(y0, y0 + bar, 16):
        d.rectangle((x0, y, x1, y + 7), fill=(226, 226, 230, 255))
    titlebar = ImageChops.multiply(inner, rrect(canvas.size, (x0, y0, x1, y0 + bar), 0, 255))
    fill(canvas, titlebar, stripes)
    ImageDraw.Draw(canvas).rectangle((x0 + 4, y0 + bar - 4, x1 - 4, y0 + bar), fill=(150, 150, 155, 255))
    for i, (col, dark) in enumerate((((236, 64, 58, 255), (140, 30, 26, 255)),
                                     ((246, 178, 40, 255), (150, 96, 10, 255)),
                                     ((96, 196, 64, 255), (40, 110, 24, 255)))):
        gem(canvas, (x0 + 62 + i * 70, y0 + bar // 2), 22, col, dark)
    # body: blue-gray sidebar on the left, white files on the right
    body = ImageChops.multiply(inner, rrect(canvas.size, (x0, y0 + bar, x1, y1), 0, 255))
    fill(canvas, body, (255, 255, 255, 255))
    side = ImageChops.multiply(body, rrect(canvas.size, (x0, y0 + bar, x0 + 200, y1), 0, 255))
    fill(canvas, side, (228, 234, 244, 255))
    d = ImageDraw.Draw(canvas)
    d.rectangle((x0 + 200, y0 + bar, x0 + 205, y1 - 4), fill=(170, 176, 190, 255))
    for i in range(4):                                               # sidebar rows
        y = y0 + bar + 50 + i * 76
        sel = i == 1
        if sel:
            d.rectangle((x0 + 4, y - 22, x0 + 199, y + 46), fill=(56, 117, 215, 255))
        d.rounded_rectangle((x0 + 30, y - 6, x0 + 78, y + 30), 6,
                            fill=(255, 255, 255, 255) if sel else (90, 130, 200, 255))
        d.rectangle((x0 + 96, y + 6, x0 + 176, y + 18),
                    fill=(255, 255, 255, 255) if sel else (150, 156, 170, 255))
    for i in range(3):                                               # folders in the file area
        for j in range(2):
            fx, fy = x0 + 262 + i * 160, y0 + bar + 64 + j * 170
            d.rounded_rectangle((fx, fy, fx + 50, fy + 28), 8, fill=(98, 152, 222, 255))
            d.rounded_rectangle((fx, fy + 14, fx + 112, fy + 96), 10, fill=(118, 172, 236, 255))
            d.rectangle((fx + 6, fy + 22, fx + 106, fy + 28), fill=(180, 210, 246, 255))
            d.rectangle((fx + 12, fy + 114, fx + 100, fy + 126), fill=(160, 164, 172, 255))


def glass(canvas):
    """The tumbler, bottom right, two thirds full of aqua water."""
    top, bot = 330, 990                         # rim and the very bottom
    tl, tr, bl, br = 500, 1000, 560, 940        # x at the rim and at the bottom
    wall = (96, 128, 170, 255)
    def xl(y): return tl + (bl - tl) * (y - top) / (bot - top)
    def xr(y): return tr + (br - tr) * (y - top) / (bot - top)
    body = Image.new('L', canvas.size, 0)
    ImageDraw.Draw(body).polygon([(tl, top), (tr, top), (br, bot - 60), (br - 50, bot),
                                  (bl + 50, bot), (bl, bot - 60)], fill=255)
    body = body.filter(ImageFilter.GaussianBlur(2))
    shadow(canvas, body, (6, 22), 20, 80)
    fill(canvas, body, (214, 232, 255, 90))                 # the glass: a faint cool tint
    # water, inside walls 14 px thick, above a 70 px glass base
    wl, floor = 540, bot - 84
    water = Image.new('L', canvas.size, 0)
    ImageDraw.Draw(water).polygon([(xl(wl) + 14, wl), (xr(wl) - 14, wl), (xr(floor) - 14, floor - 30),
                                   (xr(floor) - 44, floor), (xl(floor) + 44, floor),
                                   (xl(floor) + 14, floor - 30)], fill=255)
    fill(canvas, water, vgrad(canvas.size, (110, 206, 255, 215), (10, 92, 210, 245), wl, floor))
    d = ImageDraw.Draw(canvas)
    d.ellipse((xl(wl) + 14, wl - 30, xr(wl) - 14, wl + 30), fill=(170, 228, 255, 255))
    d.arc((xl(wl) + 14, wl - 30, xr(wl) - 14, wl + 30), 0, 180, fill=(40, 130, 225, 255), width=6)
    # the base: thick glass, lighter where the light catches it
    d.line([(xl(floor) + 30, floor + 14), (xr(floor) - 30, floor + 14)], fill=(255, 255, 255, 170), width=8)
    # rim and walls
    d.ellipse((tl, top - 36, tr, top + 36), outline=wall, width=8)
    d.arc((tl + 12, top - 24, tr - 12, top + 24), 180, 360, fill=(255, 255, 255, 220), width=5)
    d.line([(tl + 3, top), (bl + 3, bot - 60), (bl + 50, bot - 3), (br - 50, bot - 3),
            (br - 3, bot - 60), (tr - 3, top)], fill=wall, width=8, joint='curve')
    # light: a soft band down the left wall, a thin one on the right, bubbles
    hi = Image.new('L', canvas.size, 0)
    dh = ImageDraw.Draw(hi)
    dh.polygon([(tl + 34, top + 50), (tl + 74, top + 50), (bl + 74, bot - 110), (bl + 34, bot - 110)], fill=150)
    dh.polygon([(tr - 46, top + 60), (tr - 34, top + 60), (br - 34, top + 260), (br - 46, top + 260)], fill=110)
    fill(canvas, hi.filter(ImageFilter.GaussianBlur(10)), (255, 255, 255, 255))
    for bx, by, r in ((800, 650, 13), (760, 740, 9), (840, 800, 7), (720, 610, 6)):
        d.ellipse((bx - r, by - r, bx + r, by + r), outline=(225, 246, 255, 255), width=4)


def draw(with_window=True):
    canvas = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    if with_window:
        window(canvas)
    glass(canvas)
    return canvas


def small():
    """16 px: the window is mush at that size, so just the glass, filling it."""
    g = draw(False)
    x0, y0, x1, y1 = g.getbbox()
    side = max(x1 - x0, y1 - y0)
    sq = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    sq.paste(g.crop((x0, y0, x1, y1)), ((side - (x1 - x0)) // 2, (side - (y1 - y0)) // 2))
    return sq


# --- icns, classic formats

def packbits(data):
    """The icns RLE: n < 0x80 -> n+1 literal bytes; n >= 0x80 -> next byte n-0x80+3 times."""
    out, i, lit = bytearray(), 0, bytearray()
    def flush():
        while lit:
            chunk = lit[:128]; del lit[:128]
            out.append(len(chunk) - 1); out.extend(chunk)
    while i < len(data):
        run = 1
        while i + run < len(data) and data[i + run] == data[i] and run < 130:
            run += 1
        if run >= 3:
            flush(); out.append(0x80 + run - 3); out.append(data[i]); i += run
        else:
            lit.append(data[i]); i += 1
    flush()
    return bytes(out)


def rgb_rle(im):
    r, g, b, _ = im.split()
    return b''.join(packbits(c.tobytes()) for c in (r, g, b))


def bits(mask_bool, w):
    out = bytearray()
    for y in range(w):
        for x0 in range(0, w, 8):
            v = 0
            for k in range(8):
                v = v << 1 | (1 if mask_bool(x0 + k, y) else 0)
            out.append(v)
    return bytes(out)


def onebit(im):
    """ICN#/ics#: 1-bit icon (dark pixels) then 1-bit mask (alpha > 50%)."""
    w = im.width
    px = im.load()
    icon = bits(lambda x, y: px[x, y][3] > 127 and sum(px[x, y][:3]) < 384, w)
    mask = bits(lambda x, y: px[x, y][3] > 127, w)
    return icon + mask


def icns(sizes):
    chunks = []
    for size, rgb, mask, rle in ((128, b'it32', b't8mk', True), (48, b'ih32', b'h8mk', True),
                                 (32, b'il32', b'l8mk', True), (16, b'is32', b's8mk', True)):
        im = sizes[size]
        data = rgb_rle(im)
        if size == 128:
            data = bytes(4) + data
        chunks.append((rgb, data))
        chunks.append((mask, im.split()[3].tobytes()))
    chunks.insert(0, (b'ics#', onebit(sizes[16])))
    chunks.insert(0, (b'ICN#', onebit(sizes[32])))
    body = b''.join(t + struct.pack('>I', len(d) + 8) + d for t, d in chunks)
    return b'icns' + struct.pack('>I', len(body) + 8) + body


def sized(big, n):
    im = big.resize((n, n), Image.LANCZOS)
    if n <= 32:   # small sizes: a touch of sharpening keeps the edges crisp
        im = im.filter(ImageFilter.UnsharpMask(radius=1, percent=60, threshold=2))
    return im


if __name__ == '__main__':
    big = draw()
    sizes = {n: sized(big, n) for n in (128, 48, 32)}
    sizes[16] = sized(small(), 16)
    out = os.path.join(ROOT, 'build', 'appicon')
    os.makedirs(out, exist_ok=True)
    for n, im in sizes.items():
        im.save(os.path.join(out, 'icon-%d.png' % n))
    big.resize((512, 512), Image.LANCZOS).save(os.path.join(out, 'icon-512.png'))
    data = icns(sizes)
    open(os.path.join(ROOT, 'gui', 'Aquafinder.icns'), 'wb').write(data)
    print('gui/Aquafinder.icns', len(data))
