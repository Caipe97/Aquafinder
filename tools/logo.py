"""Jaguar-style branding for Panther: the Garamond "Mac OS X" wordmark and
Jaguar's Finder icon.

Inputs (Apple files, not in the repo; see README), in orig/logo/:
  panther-MacOSX.tif       loginwindow.app  About This Mac logo (apple + Myriad text)
  jaguar-AboutBox.tiff     10.2.8 loginwindow.app About box art (Aqua X + Garamond)
  panther-MacOSXart.tif    SecurityAgent / loginwindow.bundle login panel wordmark
  jaguar-MacOSXart.tif     10.2.8 loginwindow.bundle wordmark (Apple Garamond)
  jaguar-Finder.icns       10.2.8 Finder.app icon
  jaguar-dock-finder.png   10.2.8 Dock.app Finder tile

build() returns {name: bytes} for the replacement files.
"""
import io, os
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'orig', 'logo')


def _img(name):
    return Image.open(os.path.join(SRC, name)).convert('RGBA')


def _tiff(im):
    """Uncompressed RGBA TIFF with premultiplied (associated) alpha at 72 dpi,
    the way Apple's own files are written. Panther's NSImage draws Pillow's
    default (unassociated alpha, ExtraSamples=2) as an opaque black box."""
    import struct
    w, h = im.size
    px = bytearray()
    for r, g, b_, a in im.getdata():
        px += bytes((r * a // 255, g * a // 255, b_ * a // 255, a))
    tags = [(256, 3, 1, w), (257, 3, 1, h), (258, 3, 4, None), (259, 3, 1, 1), (262, 3, 1, 2),
            (273, 4, 1, None), (277, 3, 1, 4), (278, 3, 1, h), (279, 4, 1, len(px)),
            (282, 5, 1, None), (283, 5, 1, None), (284, 3, 1, 1), (296, 3, 1, 2), (338, 3, 1, 1)]
    ifd = 8
    extra = ifd + 2 + 12 * len(tags) + 4          # BitsPerSample, then the two resolutions
    bps, xres, yres, data = extra, extra + 8, extra + 16, extra + 24
    out = bytearray(b'MM\0\x2a' + struct.pack('>I', ifd) + struct.pack('>H', len(tags)))
    for tag, typ, n, v in tags:
        v = {258: bps, 273: data, 282: xres, 283: yres}.get(tag, v)
        if typ == 3 and n == 1:
            out += struct.pack('>HHIHH', tag, typ, n, v, 0)
        else:
            out += struct.pack('>HHII', tag, typ, n, v)
    out += struct.pack('>I', 0)
    out += struct.pack('>4H', 8, 8, 8, 8) + struct.pack('>2I', 72, 1) * 2
    return bytes(out + px)


def _extra_as_alpha(data):
    """Jaguar's art keeps the glyph mask in a 4th sample marked ExtraSamples=0
    ("unspecified", a Photoshop channel) over solid black RGB. Pillow drops
    that sample, so mark it as alpha (2) before decoding."""
    import struct
    bo = '>' if data[:2] == b'MM' else '<'
    ifd = struct.unpack_from(bo + 'I', data, 4)[0]
    n = struct.unpack_from(bo + 'H', data, ifd)[0]
    d = bytearray(data)
    for k in range(n):
        e = ifd + 2 + 12 * k
        if struct.unpack_from(bo + 'H', d, e)[0] == 338:
            struct.pack_into(bo + 'H', d, e + 8, 2)
    return bytes(d)


def wordmark():
    """Jaguar's Garamond text, trimmed to its ink."""
    raw = open(os.path.join(SRC, 'jaguar-MacOSXart.tif'), 'rb').read()
    j = Image.open(io.BytesIO(_extra_as_alpha(raw))).convert('RGBA')
    assert j.split()[3].getextrema() != (255, 255), 'wordmark has no mask'
    return j.crop(j.split()[3].point(lambda v: 255 if v > 20 else 0).getbbox())


def _jaguar_about():
    """Jaguar's About box art (blue Aqua X over Garamond text), premultiplied RGBA."""
    im = Image.open(os.path.join(SRC, 'jaguar-AboutBox.tiff'))
    assert im.tag_v2.get(338) == (1,), 'expected associated alpha'
    return Image.frombytes('RGBa', im.size, im.convert('RGBA').tobytes()).convert('RGBA')


def about_logo():
    """Jaguar's About art refitted into Panther's 214x124 slot: the blue X
    where Panther's apple was and the Garamond text unscaled, ending on row
    111 like Panther's Myriad text, so it clears the version line below."""
    p = _img('panther-MacOSX.tif')
    j = _jaguar_about()
    a = j.split()[3]
    ink = lambda box: j.crop(box).crop(a.crop(box).point(lambda v: 255 if v > 20 else 0).getbbox())
    x, text = ink((0, 0, j.width, 131)), ink((0, 131, j.width, j.height))
    text_top = 112 - text.height
    xh = text_top - 3
    x = x.resize((round(x.width * xh / x.height), xh), Image.LANCZOS)
    out = Image.new('RGBA', p.size, (0, 0, 0, 0))
    out.alpha_composite(x, ((p.width - x.width) // 2, 0))
    out.alpha_composite(text, ((p.width - text.width) // 2, text_top))
    return out


def login_art():
    """Garamond wordmark scaled to fit the login panel's 140x24 slot."""
    p = _img('panther-MacOSXart.tif')
    t = wordmark()
    h = p.height - 2
    w = round(t.width * h / t.height)
    out = Image.new('RGBA', p.size, (0, 0, 0, 0))
    out.alpha_composite(t.resize((w, h), Image.LANCZOS), ((p.width - w) // 2, 1))
    return out


def build():
    raw = lambda n: open(os.path.join(SRC, n), 'rb').read()
    return {
        'about': _tiff(about_logo()),
        'loginart': _tiff(login_art()),
        'findericon': raw('jaguar-Finder.icns'),
        'dockfinder': raw('jaguar-dock-finder.png'),
    }


if __name__ == '__main__':
    out = os.path.join(ROOT, 'build', 'logo')
    os.makedirs(out, exist_ok=True)
    for k, v in build().items():
        open(os.path.join(out, k), 'wb').write(v)
        print(k, len(v))
