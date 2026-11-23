"""Panther 10.3.9 AppKit: translucent (Jaguar-style) inactive title bars in
Cocoa windows.

Panther creates titled Cocoa windows with CGSNewWindowWithOpaqueShape, so the
window server gives them a backing store without alpha: Jaguar's 75%-alpha
inactive title bar art is stored as flat gray, and fully transparent pixels
come out black. Jaguar (10.2) created every Cocoa window with plain
CGSNewWindow and only then made it non-opaque. We do the same:

  1. -[NSWindow _commonAwake] always takes its plain _NSCreateWindow path
     (CGSNewWindow, backing store with alpha) instead of the opaque-shape one.
  2. An opaque window is then sent [self setOpaque:NO] (window flag +
     server opacity), in the opaque-shape path's code, now unused. A window
     that's already non-opaque keeps Panther's own _NSSetWindowOpacity(NO):
     setOpaque:NO returns early when the flag is already NO, so it never told
     the window server, and a plain CGSNewWindow is opaque there. Such
     windows (Tiger's Spotlight menu) were drawn opaque, their clear pixels
     black.

Also, the gap between the title bar buttons is 8 px instead of 7, so
Jaguar's buttons sit 22 px apart, as in Jaguar and in Carbon windows.

Cost: titled Cocoa windows are blended by the window server like Panther's
own brushed-metal windows (Safari, iTunes) already are.

Tiger 10.4.11 (8S165) has the same code in _commonAwake, at other addresses;
it keeps `self` on the stack (0x538(r1)) instead of in r30. The build is
recognised by every expected word matching.

usage: appkit_patch.py <in AppKit> <out AppKit>
"""
import sys, os, struct
sys.path.insert(0, os.path.dirname(__file__))
from macho import MachO

# (address, expected word, new word or None for "bl -[NSWindow setOpaque:]", comment)
def _b(at, to):                 # b to
    return 0x48000000 | ((to - at) & 0x03fffffc)


def _bne7(at, to):              # bne cr7,to
    return 0x40be0000 | ((to - at) & 0xfffc)


# setOpaque: expects its own address in r12, as objc_msgSend leaves it.
PATCHES_1039 = [
    (0x92f03368, 0x419e0068, 0x48000068, '_commonAwake: always plain _NSCreateWindow (Jaguar-style)'),
    # if (!isOpaque) _NSSetWindowOpacity(NO) stays; an opaque window goes to
    # [self setOpaque:NO] in the opaque-shape path, unused since the line above
    (0x92f03458, 0x40be0018, _bne7(0x92f03458, 0x92f0336c), '_commonAwake: if (isOpaque) -> [self setOpaque:NO] below'),
    (0x92f0336c, 0x809d0000, 0x3d8092fc, '_commonAwake (unused path): lis r12,hi(-[NSWindow setOpaque:])'),
    (0x92f03370, 0x807e0044, 0x618c4280, '_commonAwake (unused path): ori r12,r12,lo'),
    (0x92f03374, 0x4839dd49, 0x7fc3f378, '_commonAwake (unused path): mr r3,self'),
    (0x92f03378, 0x809cbf28, 0x38a00000, '_commonAwake (unused path): li r5,NO'),
    (0x92f0337c, 0x7c7d1b78, None,       '_commonAwake (unused path): bl -[NSWindow setOpaque:]'),
    (0x92f03380, 0x7fc3f378, _b(0x92f03380, 0x92f03470), '_commonAwake (unused path): b back, after the opacity block'),
    # 3. Jaguar's button spacing: with Jaguar's buttons (theme.jaguar_window_buttons)
    # Carbon windows space them 22 px apart, Cocoa ones by sizeOfTitlebarButtons
    # (14) + _windowTitlebarButtonSpacingWidth (7; 5 in utility windows): 21.
    # The gap of non-utility windows becomes 8.0, so 22 as in Jaguar.
    (0x92ede160, 0x3c0040e0, 0x3c004100, '_windowTitlebarButtonSpacingWidth: 7.0 -> 8.0 (non-utility)'),
]

PATCHES_10411 = [
    (0x937bad8c, 0x419e00c4, 0x480000c4, '_commonAwake: always plain _NSCreateWindow (Jaguar-style)'),
    (0x937baee4, 0x40be0018, _bne7(0x937baee4, 0x937bad90), '_commonAwake: if (isOpaque) -> [self setOpaque:NO] below'),
    (0x937bad90, 0x80410538, 0x3d80937b, '_commonAwake (unused path): lis r12,hi(-[NSWindow setOpaque:])'),
    (0x937bad94, 0x809d0000, 0x618cc750, '_commonAwake (unused path): ori r12,r12,lo'),
    (0x937bad98, 0x3ba10060, 0x80610538, '_commonAwake (unused path): lwz r3,self'),
    (0x937bad9c, 0x80620044, 0x38a00000, '_commonAwake (unused path): li r5,NO'),
    (0x937bada0, 0x4bfeff03, None,       '_commonAwake (unused path): bl -[NSWindow setOpaque:]'),
    (0x937bada4, 0x90610378, _b(0x937bada4, 0x937baefc), '_commonAwake (unused path): b back, after the opacity block'),
    # 3. as in 10.3.9: Jaguar's buttons 22 px apart
    (0x937df218, 0x3c0040e0, 0x3c004100, '_windowTitlebarButtonSpacingWidth: 7.0 -> 8.0 (non-utility)'),
]

# build -> (-[NSWindow setOpaque:], patches)
BUILDS = {
    '10.3.9':  (0x92fc4280, PATCHES_1039),
    '10.4.11': (0x937bc750, PATCHES_10411),
}


def word_at(m, data, addr):
    off = m.addr2off(addr)
    return None if off is None or off + 4 > len(data) else struct.unpack_from('>I', data, off)[0]


def detect(m):
    """The build whose expected words all match, or None."""
    for ver, (_, patches) in BUILDS.items():
        if all(word_at(m, m.data, a) == old for a, old, _, _ in patches):
            return ver


def apply(src, dst, quiet=False):
    m = MachO(src); data = bytearray(m.data)
    ver = detect(m)
    if ver is None:
        sys.exit('%s: not a stock AppKit this patch knows (%s)' % (src, ', '.join(BUILDS)))
    set_opaque, patches = BUILDS[ver]
    if not quiet:
        print('AppKit %s' % ver)
    for addr, old, new, why in patches:
        off = m.addr2off(addr)
        if new is None:
            new = 0x48000001 | ((set_opaque - addr) & 0x03fffffc)
        struct.pack_into('>I', data, off, new)
        if not quiet:
            print('%08x file+%06x  %08x -> %08x  %s' % (addr, off, old, new, why))
    open(dst, 'wb').write(bytes(data))


if __name__ == '__main__':
    apply(sys.argv[1], sys.argv[2])
