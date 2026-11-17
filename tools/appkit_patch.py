"""Panther 10.3.9 AppKit: translucent (Jaguar-style) inactive title bars in
Cocoa windows.

Panther creates titled Cocoa windows with CGSNewWindowWithOpaqueShape, so the
window server gives them a backing store without alpha: Jaguar's 75%-alpha
inactive title bar art is stored as flat gray, and fully transparent pixels
come out black. Jaguar (10.2) created every Cocoa window with plain
CGSNewWindow and only then made it non-opaque. We do the same:

  1. -[NSWindow _commonAwake] always takes its plain _NSCreateWindow path
     (CGSNewWindow, backing store with alpha) instead of the opaque-shape one.
  2. The window is then sent [self setOpaque:NO] (window flag + server
     opacity), where Panther only did that for windows that weren't opaque.

Cost: titled Cocoa windows are blended by the window server like Panther's
own brushed-metal windows (Safari, iTunes) already are.

usage: appkit_patch.py <in AppKit> <out AppKit>
"""
import sys, os, struct
sys.path.insert(0, os.path.dirname(__file__))
from macho import MachO

SET_OPAQUE = 0x92fc4280          # -[NSWindow setOpaque:]

# (address, expected word, new word or None for "bl -[NSWindow setOpaque:]", comment)
PATCHES = [
    (0x92f03368, 0x419e0068, 0x48000068, '_commonAwake: always plain _NSCreateWindow (Jaguar-style)'),
    (0x92f03458, 0x40be0018, 0x60000000, '_commonAwake: if (!isOpaque) ... -> always'),
    # that block becomes [self setOpaque:NO]; setOpaque: expects its own
    # address in r12, as objc_msgSend leaves it
    (0x92f0345c, 0x809c0000, 0x3d8092fc, '_commonAwake: lis r12,hi(-[NSWindow setOpaque:])'),
    (0x92f03460, 0x7fc3f378, 0x618c4280, '_commonAwake: ori r12,r12,lo'),
    (0x92f03464, 0x4839dc59, 0x7fc3f378, '_commonAwake: mr r3,self'),
    (0x92f03468, 0x38800000, 0x38a00000, '_commonAwake: li r5,NO'),
    (0x92f0346c, 0x480931c5, None,       '_commonAwake: bl -[NSWindow setOpaque:]'),
]


def apply(src, dst, quiet=False):
    m = MachO(src); data = bytearray(m.data)
    for addr, old, new, why in PATCHES:
        off = m.addr2off(addr)
        cur = struct.unpack_from('>I', data, off)[0]
        if new is None:
            new = 0x48000001 | ((SET_OPAQUE - addr) & 0x03fffffc)
        if cur != old:
            sys.exit('mismatch at %08x: %08x != %08x (%s)' % (addr, cur, old, why))
        struct.pack_into('>I', data, off, new)
        if not quiet:
            print('%08x file+%06x  %08x -> %08x  %s' % (addr, off, old, new, why))
    open(dst, 'wb').write(bytes(data))


if __name__ == '__main__':
    apply(sys.argv[1], sys.argv[2])
