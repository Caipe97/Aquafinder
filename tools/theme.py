"""Transplant Appearance theme artwork (pxm# resources) from one Extras.rsrc
into another, e.g. Jaguar's pinstriped title bars into Panther.

usage: theme.py <panther Extras.rsrc> <jaguar Extras.rsrc> <out Extras.rsrc> id[,id...]
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from rsrc import ResFile
import pxm


def transplant(dst_path, src_path, out_path, ids, preview_dir=None):
    dst = ResFile(open(dst_path, 'rb').read())
    src = ResFile(open(src_path, 'rb').read())
    changes = {}
    for i in ids:
        key = ('pxm#', i)
        if key not in src.res:
            sys.exit('pxm# %d missing in %s' % (i, src_path))
        a, b = dst.res.get(key), src.res[key]
        ha, hb = (pxm.header(a['data']) if a else None), pxm.header(b['data'])
        print('pxm# %5d %-38s %s -> %s' % (i, (b['name'] or '')[:38],
              ha and '%dx%d n%d' % (ha['w'], ha['h'], ha['count']),
              '%dx%d n%d' % (hb['w'], hb['h'], hb['count'])))
        if preview_dir:
            for tag, r in (('before', a), ('after', b)):
                if r and pxm.header(r['data'])['depth'] == 32:
                    pxm.sheet(pxm.visible(*pxm.decode(r['data']))).save(
                        os.path.join(preview_dir, '%d-%s.png' % (i, tag)))
        new = dict(b)
        if a:   # keep Panther's name/attributes, take Jaguar's pixels
            new['name'], new['attrs'] = a['name'], a['attrs']
        if a and ha['count'] != hb['count']:
            # Re-encode into Panther's layout, mapping each Panther state to a
            # Jaguar state (extra Panther states reuse Jaguar's state 0, active).
            assert (ha['w'], ha['h']) == (hb['w'], hb['h']), 'size differs'
            ims, ms = pxm.decode(b['data'])
            pick = [k if k < hb['count'] else 0 for k in range(ha['count'])]
            _, pms = pxm.decode(a['data'])
            masks = [ms[min(k, len(ms)-1)] for k in pick][:len(pms)]
            new['data'] = pxm.encode(a['data'], [ims[k] for k in pick], masks)
            print('          states remapped Panther<-Jaguar: %s' % pick)
        changes[key] = new['data']
    out = dst.patched_in_place(changes)
    check = ResFile(out)
    for key, data in changes.items():
        assert check.res[key]['data'] == data
    open(out_path, 'wb').write(out)


if __name__ == '__main__':
    transplant(sys.argv[1], sys.argv[2], sys.argv[3],
               [int(x) for x in sys.argv[4].split(',')],
               preview_dir=os.environ.get('PREVIEW_DIR'))


def shrink_frames(in_path, out_path, res_id, size, offset):
    """Resample every frame of pxm# res_id to size x size, placed at
    (offset, offset) inside its unchanged canvas (rest transparent).
    Pixels are premultiplied RGBA; resampling premultiplied values is correct."""
    from PIL import Image
    rf = ResFile(open(in_path, 'rb').read())
    key = ('pxm#', res_id)
    d = rf.res[key]['data']
    ims, ms = pxm.decode(d)
    out = []
    for im in ims:
        small = im.resize((size, size), Image.LANCZOS)
        c = Image.new('RGBA', im.size, (0, 0, 0, 0))
        c.paste(small, (offset, offset))
        out.append(c)
    new = pxm.encode(d, out, ms)
    data = rf.patched_in_place({key: new})
    assert ResFile(data).res[key]['data'] == new
    open(out_path, 'wb').write(data)



TOOLBAR_PPAT = 2137    # kThemeBrushToolbarBackground (Panther: 247/244 pinstripes)
# Jaguar's toolbar pinstripes (pxm# 4330: 250, 255, 250, 233 from its top),
# in the row order that puts them in phase with a Finder window's toolbar:
# the brush pattern starts at the content's port origin, the toolbar art at
# the window top, one row apart modulo 4.
JAGUAR_TOOLBAR_ROWS = [233, 250, 255, 250]


def jaguar_toolbar_brush(in_path, out_path, res_id=TOOLBAR_PPAT, rows=JAGUAR_TOOLBAR_ROWS):
    """Repaint the toolbar background brush (a 2-bit 'ppat' of solid rows) with
    Jaguar's pinstripes, so what the Finder erases with it (the sidebar
    divider, the status bar under the toolbar) matches the transplanted
    toolbar art. Same size and layout: only the color table and pixels change."""
    import struct
    rf = ResFile(open(in_path, 'rb').read())
    key = ('ppat', res_id)
    d = bytearray(rf.res[key]['data'])
    pat_type, map_off, data_off = struct.unpack_from('>HII', d, 0)
    assert pat_type == 1, 'not a full-color pattern'
    row_bytes = struct.unpack_from('>H', d, map_off + 4)[0] & 0x3fff
    t, l, b, r = struct.unpack_from('>4h', d, map_off + 6)
    pixel_size = struct.unpack_from('>H', d, map_off + 32)[0]
    ct = struct.unpack_from('>I', d, map_off + 42)[0]
    size = struct.unpack_from('>H', d, ct + 6)[0]
    assert pixel_size == 2 and size + 1 >= 4 and (b - t) % len(rows) == 0, 'unexpected brush layout'
    grays = sorted(set(rows))
    assert len(grays) <= 3
    for k, g in enumerate(grays, start=1):           # entries 1..3 (0 stays black)
        struct.pack_into('>4H', d, ct + 8 + 8 * k, k, g * 0x101, g * 0x101, g * 0x101)
    for y in range(b - t):
        v = grays.index(rows[y % len(rows)]) + 1
        d[data_off + y * row_bytes:data_off + (y + 1) * row_bytes] = bytes([v * 0x55]) * row_bytes
    data = rf.patched_in_place({key: bytes(d)})
    assert ResFile(data).res[key]['data'] == bytes(d)
    open(out_path, 'wb').write(data)


# Jaguar's title bar buttons. Panther draws an Aqua window's close, minimize
# and zoom buttons from the 14x16 'MetalWindowLarge*' art (pxm# 4690, 4700,
# 4710; Graphite and its other variant via tdat 2 and 3: 13176-13181);
# Jaguar drew 'WindowLarge*' (pxm# 200, 210, 220, 19x19; Graphite 10182-10184,
# the other variant 10161, 10171, 10181), which Panther still carries,
# unchanged, but no longer uses. Each Panther button gets Jaguar's art at
# Jaguar's size, in Panther's state order: Panther's close button has one
# more state (10) than Jaguar's (9), a second dirty-and-inactive one, which
# takes Jaguar's (its last).
# Panther spaces the buttons by their art's width + 7 (21 px for its 14 px
# art); Jaguar's were 22 px apart. So Jaguar's 19 px canvas is cropped to
# its 15 middle columns (WINDOW_BUTTON_COLS): only the faintest shadow
# (alpha 14 and less) goes, and the first button's center stays 15 px from
# the window's edge, as in Jaguar. Panther draws the art's top 4 rows into
# the title bar, so its top row (alpha 2 at most) goes too, which puts the
# buttons 1 px lower than Jaguar's instead of 2; its bottom rows (alpha 14
# and 0) go as well, as nothing shows there.
WINDOW_BUTTON_COLS = (2, 17)
WINDOW_BUTTON_ROWS = (1, 17)
# Panther id -> Jaguar id
WINDOW_BUTTONS = {4690: 200, 4700: 210, 4710: 220,
                  13176: 10182, 13178: 10183, 13180: 10184,
                  13177: 10161, 13179: 10171, 13181: 10181}
# Tiger 10.4.11 carries the same buttons (same ids, size and placement) with
# states added at the end: close 12 instead of 10, minimize and zoom 7
# instead of 6. The new ones are an unavailable button in an active window
# (Tiger's clear, colorless bead; dirty for close's 12th), where Panther
# drew one of its gray states. Each takes Jaguar's: unavailable (5) and
# dirty, inactive (8). (state count, Jaguar's) -> Jaguar states for the
# states past Jaguar's own.
EXTRA_STATES = {
    (10, 9): [8],          # Panther close: a second dirty-and-inactive state
    (12, 9): [8, 5, 8],    # Tiger close: that, then unavailable and unavailable dirty
    (7, 6): [5],           # Tiger minimize and zoom: unavailable
}


def jaguar_window_buttons(in_path, src_path, out_path, buttons=WINDOW_BUTTONS, cols=WINDOW_BUTTON_COLS, rows=WINDOW_BUTTON_ROWS):
    """Replace each Panther (or Tiger) button pxm# with the Jaguar one's
    pixels (its columns cols[0]..cols[1]-1), keeping the file's state count
    (extra states: EXTRA_STATES). The new data is longer, so it's appended
    (rsrc.with_replaced)."""
    import struct
    rf = ResFile(open(in_path, 'rb').read())
    src = ResFile(open(src_path, 'rb').read())
    changes = {}
    for pid, jid in buttons.items():
        p, j = rf.res[('pxm#', pid)]['data'], src.res[('pxm#', jid)]['data']
        n, jn = pxm.header(p)['count'], pxm.header(j)['count']
        assert n >= jn, 'pxm# %d: fewer states than Jaguar\'s %d' % (pid, jid)
        ims, ms = pxm.decode(j)
        h = pxm.header(j)
        box = (cols[0], rows[0], cols[1], rows[1])
        ims, ms = [im.crop(box) for im in ims], [m.crop(box) for m in ms]
        pick = list(range(jn)) + EXTRA_STATES[(n, jn)] if n > jn else list(range(n))
        head = bytearray(j[:24])
        top, left, bottom, right = struct.unpack_from('>4h', head, 4)
        struct.pack_into('>4h', head, 4, top, left, top + rows[1] - rows[0], left + cols[1] - cols[0])
        struct.pack_into('>H', head, 22, n)
        out = bytes(head)
        for m in ([ms[0]] if len(ms) == 1 else [ms[k] for k in pick]):
            mm = bytearray(pxm.encode_mask(m))
            out += bytes(mm)
        for k in pick:
            out += ims[k].convert('RGBA').tobytes()
        ni, nm = pxm.decode(out)
        assert len(ni) == n and all(ni[k].tobytes() == ims[pick[k]].tobytes() for k in range(n))
        changes[('pxm#', pid)] = out
    data = rf.with_replaced(changes)
    check = ResFile(data)
    assert all(check.res[k]['data'] == v for k, v in changes.items())
    open(out_path, 'wb').write(data)
