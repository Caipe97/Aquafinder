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

It also appends the search splitter's bar, 'PNG ' 8801 (see SPLITTER_ID),
and replaces the toolbar's Back, Forward and View buttons with Jaguar's
(toolbar.py); those are appended too, the originals left unreferenced.

With stripes=True (patch.py's 'stripes' set) the divider image is the
pinstriped sidebar's instead: see STRIPES_*.

usage: grip.py [--stripes] <Finder.rsrc> <out.rsrc> [divider.png [splitter.png]]
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

# The search results' horizontal splitter (between the results and the path
# pane; patch.py 'gap' draws it): Panther's Aqua splitter bar, 9 rows
# (lines included) with a centered three-line grip, measured from an Aqua
# Panther search window. A new resource, 'PNG ' 8801, appended to the file.
SPLITTER_ID = 8801
SPLITTER_NAME = 'SplitterBar'
SPLITTER_ROWS = [175, 245, 225, 219, 229, 235, 247, 255, 163]   # top to bottom
SPLITTER_GRIP = {2: [127, 140], 4: [140, 127], 6: [153]}         # row: alternating grays
SPLITTER_GRIP_WIDTH = 11
SPLITTER_WIDTH = 2048           # wider than any splitter (clipped to it); grip centered


def chunk(kind, body):
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xffffffff)


def chunks(png):
    out, k = [], 8
    while k < len(png):
        n = struct.unpack_from('>I', png, k)[0]
        out.append((png[k + 4:k + 8], png[k + 8:k + 8 + n]))
        k += 12 + n
    return out


def png8(w, rows, like, size=None):
    """8-bit gray PNG of `rows` carrying `like`'s gAMA and pHYs chunks (the
    same treatment by CoreGraphics as the original); padded with a tEXt
    chunk to `size` bytes if given."""
    # filter 'Up' (2): rows equal to the one above are zeros
    raw, prev = b'', bytes(w)
    for r in rows:
        raw += b'\2' + bytes((a - b) & 0xff for a, b in zip(r, prev))
        prev = r
    # (cHRM, the primaries, is left out: it means nothing for gray, and the
    # divider only fits the original's length without it)
    keep = [c for c in chunks(like) if c[0] in (b'pHYs', b'gAMA')]
    head = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, len(rows), 8, 0, 0, 0, 0))
    head += b''.join(chunk(k, b) for k, b in keep)
    tail = chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')
    if size is None:
        return head + tail
    pad = size - len(head) - len(tail) - 12 - len(b'Comment\0')
    assert pad >= 0, 'PNG is %d bytes over %d' % (-pad, size)
    png = head + chunk(b'tEXt', b'Comment\0' + b' ' * pad) + tail
    assert len(png) == size
    return png


def splitter_png(like):
    """The search splitter bar, SPLITTER_WIDTH x 9, grip in its center columns."""
    w, c = SPLITTER_WIDTH, SPLITTER_WIDTH // 2
    rows = []
    for y, g in enumerate(SPLITTER_ROWS):
        r = bytearray([g]) * w
        for k in range(SPLITTER_GRIP_WIDTH):
            if y in SPLITTER_GRIP:
                pat = SPLITTER_GRIP[y]
                r[c - SPLITTER_GRIP_WIDTH // 2 + k] = pat[k % len(pat)]
        rows.append(bytes(r))
    return png8(w, rows, like)


def divider_png(like):
    """The divider, padded to len(like) bytes (it replaces `like` in place)."""
    plain = bytes(GRADIENT)
    grip = bytearray(plain)
    for x, g in RIDGES:
        grip[x] = g
    rows = [plain] * (HEIGHT - RIDGE_GAP - RIDGE_ROWS) + [bytes(grip)] * RIDGE_ROWS + [plain] * RIDGE_GAP
    return png8(len(GRADIENT), rows, like, len(like))


# 'stripes': the divider of the pinstriped sidebar, 7 px (patch.STRIPES_WIDTH):
# see-through, so the toolbar pinstripes the divider is erased with show,
# with a soft shadow falling from a 1 px line by the files, and a small
# arrow in the middle rows (patch.py centers the image on the divider):
# 8-bit gray + alpha. Columns left to right; the shadow is black, by alpha.
STRIPES_WIDTH = 7
STRIPES_LINE = 163
STRIPES_SHADOW = [.17, .105, .06, .03, .012, .004]   # from the line outwards
# The arrow: 3 x 5, pointing right (toward the files), in columns 2..4: two
# stripe columns before it, so, collapsed, it stands clear of the window's
# left edge, and one before the line. (gray, coverage) per column.
_ARROW = [(.55, .15, 0), (.9, .7, .15), (.9, .95, .6)]
STRIPES_ARROW = [[None, None] + [(95, c) if c else None for c in r] + [None] for r in _ARROW + _ARROW[-2::-1]]


def png_ga(w, rows, like, size):
    """8-bit gray+alpha PNG of `rows` (lists of (gray, alpha)), with like's
    gAMA (and pHYs if it fits), padded to `size` bytes. Filter 'Up' or none,
    whichever packs smaller."""
    up, none, prev = b'', b'', bytes(2 * w)
    for r in rows:
        b = bytes(v for ga in r for v in ga)
        up += b'\2' + bytes((x - y) & 0xff for x, y in zip(b, prev))
        none += b'\0' + b
        prev = b
    idat = min(zlib.compress(up, 9), zlib.compress(none, 9), key=len)
    tail = chunk(b'IDAT', idat) + chunk(b'IEND', b'')
    for kinds in ((b'pHYs', b'gAMA'), (b'gAMA',)):    # pHYs (pixel density) goes if it must: the grays don't change
        keep = [c for c in chunks(like) if c[0] in kinds]
        head = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, len(rows), 8, 4, 0, 0, 0))
        head += b''.join(chunk(k, b) for k, b in keep)
        pad = size - len(head) - len(tail) - 12 - len(b'Comment\0')
        if pad >= 0:
            break
    assert pad >= 0, 'PNG is %d bytes over %d' % (-pad, size)
    png = head + chunk(b'tEXt', b'Comment\0' + b' ' * pad) + tail
    assert len(png) == size
    return png


def _over(cols, row):
    """An icon row (gray, coverage) drawn over the (gray, alpha) columns."""
    out = list(cols)
    for x, px in enumerate(row):
        if px:
            G, t = px
            g0, a0 = out[x]
            s = a0 / 255
            a = 1 - (1 - s) * (1 - t)
            out[x] = (round((g0 * s * (1 - t) + G * t) / a), round(255 * a))
    return out


def stripes_divider_png(like):
    """The pinstriped sidebar's divider, padded to len(like) bytes."""
    cols = [(0, 0)] * (STRIPES_WIDTH - 1) + [(STRIPES_LINE, 255)]
    for i, a in enumerate(STRIPES_SHADOW):
        cols[STRIPES_WIDTH - 2 - i] = (0, round(255 * a))
    arrow = [_over(cols, r) for r in STRIPES_ARROW]
    top = HEIGHT // 2 - len(arrow) // 2
    rows = [cols] * top + arrow + [cols] * (HEIGHT - top - len(arrow))
    return png_ga(STRIPES_WIDTH, rows, like, len(like))


def build(finder_rsrc, stripes=False):
    """Finder.rsrc bytes with the grip replaced (in place), the splitter bar
    added and the toolbar buttons replaced (both appended). stripes: the
    divider of the pinstriped sidebar instead of the column view's."""
    import toolbar
    rf = ResFile(finder_rsrc)
    like = rf.res[('PNG ', GRIP_ID)]['data']
    png = stripes_divider_png(like) if stripes else divider_png(like)
    bar = splitter_png(like)
    buttons = {('PNG ', i): b for i, b in toolbar.build(finder_rsrc).items()}
    out = ResFile(rf.patched_in_place({('PNG ', GRIP_ID): png})).with_added('PNG ', SPLITTER_ID, SPLITTER_NAME, bar)
    out = ResFile(out).with_replaced({k: b for k, b in buttons.items() if k in rf.res})
    for k, b in sorted(buttons.items()):
        if k not in rf.res:                       # the View control's 6th images (8615-8617)
            out = ResFile(out).with_added(k[0], k[1], None, b)
    new = ResFile(out)
    assert new.res[('PNG ', GRIP_ID)]['data'] == png and new.res[('PNG ', SPLITTER_ID)]['data'] == bar
    assert all(new.res[k]['data'] == b for k, b in buttons.items())
    assert all(new.res[k]['data'] == r['data'] and new.res[k]['name'] == r['name']
               for k, r in rf.res.items() if k != ('PNG ', GRIP_ID) and k not in buttons)
    return out


if __name__ == '__main__':
    stripes = '--stripes' in sys.argv
    if stripes:
        sys.argv.remove('--stripes')
    out = build(open(sys.argv[1], 'rb').read(), stripes)
    open(sys.argv[2], 'wb').write(out)
    if len(sys.argv) > 3:
        from PIL import Image
        Image.open(io.BytesIO(ResFile(out).res[('PNG ', GRIP_ID)]['data'])).save(sys.argv[3])
        if len(sys.argv) > 4:
            Image.open(io.BytesIO(ResFile(out).res[('PNG ', SPLITTER_ID)]['data'])).save(sys.argv[4])
