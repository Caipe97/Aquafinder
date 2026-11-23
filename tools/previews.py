"""Before/after preview pictures for the Aquafinder app, cut from the
screenshots in screens/ (all taken on Panther 10.3.9 at 800x600).

Writes gui/preview/<name>.png, 280x170 each, which native-build.sh copies
into Aquafinder.app/Contents/Resources:

  finder-metal  finder-aqua  finder-stripes    a Finder window's top-left corner
  finder-header finder-well                    (with each sidebar style)
  sidebar-plain sidebar-stripes                its sidebar, a bit lower
  sidebar-header sidebar-well
  titlebar-panther titlebar-jaguar             TextEdit's title bar, 2x close-up
  logo-panther  logo-jaguar                    About This Mac logo + Finder icon

  python3 tools/previews.py
"""
import os
from PIL import Image
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(ROOT, 'screens')
OUT = os.path.join(ROOT, 'gui', 'preview')
W, H = 280, 170


def shot(name):
    return Image.open(os.path.join(SHOTS, name)).convert('RGB')


def window(name, x, y, dy=0):
    """W x H from a window whose top-left corner is at (x, y), with a few
    pixels of desktop showing on the left and above."""
    return shot(name).crop((x - 6, y - 6 + dy, x - 6 + W, y - 6 + dy + H))


def closeup(name, x, y):
    """Half-size region at (x, y), doubled pixel for pixel."""
    return shot(name).crop((x, y, x + W // 2, y + H // 2)).resize((W, H), Image.NEAREST)


def icon(left):
    """Finder icon from finder-icon.png (stock on the left, Jaguar on the
    right, both on flat 236 gray), with that gray turned into alpha."""
    im = shot('finder-icon.png').crop((12, 52, 148, 188) if left else (188, 52, 324, 188))
    a = np.array(im).astype(int)
    d = np.abs(a - 236).max(axis=2)
    alpha = np.clip(d * 255 // 24, 0, 255).astype(np.uint8)
    rgba = np.dstack([np.array(im), alpha])
    return Image.fromarray(rgba, 'RGBA').resize((92, 92), Image.LANCZOS)


def logo(left):
    """About This Mac's logo (screens/about.png: stock panel at x=0, Aquafinder
    at x=323) beside the Finder icon, on the About window's pinstripes."""
    px = 0 if left else 323
    about = shot('about.png')
    y0 = 60
    blank = about.crop((px + 20, y0, px + 21, y0 + H))          # an empty pinstripe column
    out = Image.new('RGB', (W, H))
    for x in range(W):
        out.paste(blank, (x, 0))
    out.paste(about.crop((px + 72, y0, px + 232, y0 + 150)), (8, 10))
    out = out.convert('RGBA')
    out.alpha_composite(icon(left), (176, 40))
    return out.convert('RGB')


def build():
    return {
        'finder-metal': window('before-after.png', 28, 90),
        'finder-aqua': window('finder-list.png', 28, 50),
        'finder-stripes': window('stripes.png', 40, 30),
        'finder-header': window('header.png', 40, 30),
        'finder-well': window('well.png', 40, 30),
        'sidebar-plain': window('finder-list.png', 28, 50, 60),
        'sidebar-stripes': window('stripes.png', 40, 30, 60),
        'sidebar-header': window('header.png', 40, 30, 60),
        'sidebar-well': window('well.png', 40, 30, 60),
        'titlebar-panther': closeup('stock-textedit.png', 336, 230),
        'titlebar-jaguar': closeup('titlebars-cocoa-finder.png', 336, 230),
        'logo-panther': logo(True),
        'logo-jaguar': logo(False),
    }


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    for k, im in build().items():
        assert im.size == (W, H), k
        p = os.path.join(OUT, k + '.png')
        im.save(p, dpi=(72, 72), optimize=True)   # 72 dpi: NSImage sizes it 1:1
        print(k, os.path.getsize(p))
