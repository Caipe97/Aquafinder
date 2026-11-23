"""The sidebar's Aqua list header ('header' sidebar style, patch.py): a
strip like the file list's column header over the sidebar, labeled
"Places", as panes had in Jaguar's Address Book.

It is a PNG, 'PNG ' 8802 in Finder.rsrc (Panther and Tiger), HEADER_WIDTH
x 17: the Aqua list header's own texture, an 8-column tile of four column
variants (TILE: top line, gradient, bottom line; the same on 10.3.9 and
10.4.11, measured from an unsorted column of a running Finder's list
header), with the label drawn over it. The Finder draws it at the sidebar's
top-left, clipped to the sidebar's width. 'PNG ' 8803 is the same for an
inactive window, its label 50% gray (INACTIVE_GRAY), as the file list's.

The label is the coverage of "Places" in black on white, Lucida Grande 11
(kThemeSmallSystemFont, the list header's font), as Cocoa draws it on both
systems (the same pixels on 10.3.9 and 10.4.11; tools/label.m renders it in
a VM): LABEL_X and LABEL_Y place its box so the glyphs sit where the file
list header's do, their bottoms on the header's row 12.
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

HEADER_ID = 8802                    # an active window's; HEADER_ID + 1 an inactive one's
HEADER_NAME = 'SidebarHeader'
INACTIVE_GRAY = 127                 # the label's gray in an inactive window (measured)
HEADER_WIDTH = 1024                 # wider than any sidebar (clipped to it)
# the header's columns, top to bottom (top line, gradient, bottom line)
_A = [158, 255, 249, 244, 242, 241, 240, 239, 234, 239, 241, 243, 247, 251, 255, 255, 178]
_B = [160, 255, 249, 244, 242, 241, 240, 240, 234, 239, 241, 244, 248, 252, 253, 255, 178]
_C = [161, 255, 249, 245, 243, 244, 241, 240, 232, 239, 242, 243, 248, 251, 254, 255, 178]
_D = [157, 255, 249, 244, 242, 242, 241, 241, 233, 240, 241, 243, 247, 250, 255, 255, 178]
TILE = [_A, _B, _C, _A, _D, _D, _B, _C]
HEIGHT = len(_A)

LABEL_X, LABEL_Y = 9, 4             # the label box's top-left in the header
LABEL = [                           # gray over white, rows of the box
    bytes.fromhex('ffffffffffff81f0ffffffffffffffffffffffffffffffffffffffffffffff'),
    bytes.fromhex('0621112fcdff0ee2ffffffffffffffffffffffffffffffffffffffffffffff'),
    bytes.fromhex('06dbfa6358ff0ee2ffffffffffffffffffffffffffffffffffffffffffffff'),
    bytes.fromhex('06dbff8d31ff0ee2ff8f392a70ffffde471d27c1ff83284acbffff8d3728b9'),
    bytes.fromhex('06cdb1218aff0ee2ffd8f9f912e4ff605ef3fffbd933f8c644fff60cebfffc'),
    bytes.fromhex('062b6fbdfeff0ee2ffffd9a015c8f80fcaffffff85326f6d09f7ff4434c6ff'),
    bytes.fromhex('06dbffffffff0ee2fd3a6fc522c8f60cd3ffffff6b52c3c3c3f9fffc98199c'),
    bytes.fromhex('06dbffffffff0ee2e10af9ed1dc1ff5b6cfcfffbb217effffffff9f8ff975a'),
    bytes.fromhex('06dbffffffff0ee2ff51243c5936fcd6271e28b1ff7f0f412feedf1e4237cc'),
    bytes.fromhex('fffffffffffffffffffff0ffffefffffffeafdfffffffaebffffffffecffff'),
]


def rows(width=HEADER_WIDTH, ink=0):
    """The header's pixel rows (8-bit gray): the tiled texture, with the label
    drawn over it in `ink` by its coverage (1 - gray / 255 of the label)."""
    out = []
    for y in range(HEIGHT):
        r = bytearray(TILE[x % len(TILE)][y] for x in range(width))
        ly = y - LABEL_Y
        if 0 <= ly < len(LABEL):
            for x, v in enumerate(LABEL[ly]):
                c = 1 - v / 255
                r[LABEL_X + x] = round(r[LABEL_X + x] * (1 - c) + ink * c)
        out.append(bytes(r))
    return out


def header_png(like, inactive=False):
    """The header PNG (inactive: an inactive window's), carrying `like`'s
    gAMA and pHYs (the same treatment by CoreGraphics as the Finder's own
    images)."""
    import grip
    return grip.png8(HEADER_WIDTH, rows(ink=INACTIVE_GRAY if inactive else 0), like)


if __name__ == '__main__':
    from PIL import Image
    im = Image.frombytes('L', (HEADER_WIDTH, HEIGHT), b''.join(rows()))
    im.crop((0, 0, 120, HEIGHT)).resize((480, HEIGHT * 4), Image.NEAREST).save(sys.argv[1])
