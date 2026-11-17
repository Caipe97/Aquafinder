"""Aquafinder Finder patcher: Aqua (non-metal) browser windows that keep
the toolbar and sidebar.

Patch sites are defined against the stock 10.3.9 (7W98) Finder. Other
copies -- re-prebound ones, and other builds such as 10.3.4 whose code has
moved -- are matched by masked instruction signatures, which
update_prebinding never changes; every site must match exactly once.

usage: patch.py <in-finder> <out-finder> [set,set,...]   (default: all sets)
"""
import sys, struct
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from macho import MachO

LI_R4_METAL, LI_R4_0, LI_R4_1 = 0x38800100, 0x38800000, 0x38800001

# (set, ref_addr in 10.3.9, expected word or None for "any bl/bc", action, comment)
#   action: int           -> write this literal word
#           ('bl', name)  -> bl to the stub for import `name` in this build
#           ('always',)   -> turn this conditional branch into an unconditional one
PATCHES = [
    # Never set kWindowMetalAttribute (0x100) on browser windows.
    ('nometal', 0x44f14, LI_R4_METAL, LI_R4_0, 'window init: ChangeWindowAttributes(set metal) -> set nothing'),
    ('nometal', 0x6e914, LI_R4_METAL, LI_R4_0, 'show-toolbar: ChangeWindowAttributes(set metal) -> set nothing'),
    # Square Aqua bottom corners instead of the rounded metal ones.
    ('square', 0x44f4c, LI_R4_1, LI_R4_0, 'window init: SetWindowHasRoundedCorners(1) -> 0'),
    ('square', 0x6e8f8, LI_R4_1, LI_R4_0, 'show-toolbar: SetWindowHasRoundedCorners(1) -> 0'),
    # View background eraser (status bar etc.) always takes the Aqua
    # SetThemeBackground+EraseRect branch instead of painting metal.
    ('statusbar', 0x23b0c, 0x419e0084, ('always',), 'EraseViewBackground: beq aqua -> b aqua'),
    # Splitter gap / framed box: EraseRgn(rgn) instead of
    # DrawWindowMetalOverContentRelativeRegion(window, rgn).
    # The splitter repaint (sidebar divider drag) runs inside QDBeginCGContext,
    # where QuickDraw erasing is never seen; fill the clipped CGRect white via
    # CoreGraphics instead (helper placed in the dead metal branch of
    # EraseViewBackground, see place_fill()).
    ('gap', 0x4e7a0, 0x7d8903a6, 0x80610074, 'splitter repaint: mtctr (GetMacWindow) -> lwz r3,cgctx'),
    ('gap', 0x4e7a4, 0x4e800421, 0x388100b0, 'splitter repaint: bctrl -> addi r4,r1,clipped CGRect'),
    ('gap', 0x4e7a8, 0x808100c4, 0x38a100d0, 'splitter repaint: lwz r4,rgn -> addi r5,r1,view CGRect'),
    ('gap', 0x4e7ac, None, ('bl_fill',), 'splitter repaint: bl DrawWindowMetal... -> bl CGFillRectWhite'),
    # Jaguar-style soft shadow instead of the flat bottom bar and its 1px line:
    # the Aqua erase branch jumps to a gradient routine (tools/cave.py) placed
    # in the free space at the end of __TEXT.
    ('shadow', 0x23b90, 0x38600034, ('cave',), 'status bar erase: li r3,0x34 -> b <gradient routine>'),
    # Softer 1px pane borders: both loads of the 0.6 gray (153) read the
    # gradient's darkest tone (212/255) from the cave instead. The panes'
    # bottom border sits directly on the bar, so it becomes the gradient's
    # first row (212, then the bar's 216, 220, ...), aligned with the side
    # borders and repainted with the frame (no stale pixels when dragging).
    ('softlines', 0x2d6f4, 0xc022fef4, ('lfs_gray',), 'pane frame fill gray 0.6 -> 212/255'),
    ('softlines', 0x19fac0, 0xc022fef4, ('lfs_gray',), 'framed box stroke gray 0.6 -> 212/255'),
    # Bottom bar 15 rows instead of 18, the height of the resize handle (no
    # white rows above it; the file list gains 3 rows). The window layout
    # subtracts this from the content height when the bar is at the bottom:
    # 14, so the panes overlap the bar's top row and their 1px bottom border
    # is that row (212, as in Jaguar). The list's scroll bar then ends right
    # above the resize handle, with no extra line between them.
    # Keep in sync with cave.BAR_HEIGHT (the gradient table's length).
    ('slimbar', 0x48958, 0x38000012, 0x3800000e, 'window layout: bottom bar height 18 -> 15, panes overlap its top row'),
    ('slimbar', 0x2ae30, 0x3842ffee, 0x3842fff1, 'status bar rect: top = bottom - 18 -> - 15'),
    ('slimbar', 0x2ae48, 0x38420012, 0x3842000f, 'status bar rect: bottom = top + 18 -> + 15'),
    # loading spinner (16x16 theme art, drawn bottom-aligned in its rect): the
    # rect ended 2 rows below the 15-row bar. Bottom = top + 14 puts the
    # canvas on the border line + bar; the theme's arrows are shrunk to 13 px
    # (theme.shrink_frames) so they sit on bar rows 1..13.
    ('slimbar', 0x1605c, 0x39290010, 0x3929000e, 'status bar spinner: bottom = top + 16 -> + 14'),
    # With the bar at the bottom, the panes' content view is one column wider
    # than the window, so the panes' right border line falls outside it and
    # the list's scroll bar ends on the window edge, in line with the resize
    # handle below it (as in Aqua windows). r28 = 1 when the bar is at the
    # bottom, 0 otherwise; the width is never negative, so no sign extension.
    ('slimbar', 0x48974, 0x7c840734, 0x7c84e214, 'window layout: content width -> width + (bar at bottom)'),
]
SET_NAMES = ['nometal', 'square', 'statusbar', 'gap', 'shadow', 'softlines', 'slimbar']
SETS = {n: {p[1]: p for p in PATCHES if p[0] == n} for n in SET_NAMES}

# Framed-box painter's metal fill section (QuickDraw erase inside a CG bracket,
# so it never showed): skipped and reused for the divider's erase entry point.
FRAMEDBOX_SKIP = 0x19faec      # mr r3,r25 ; ... ; bl EraseRgn  (17 words)
FRAMEDBOX_RESUME = 0x19fb30    # lis r29,0x32 (one-time grip image load)
DIVIDER_CGRECT_CALL = 0x22500  # bl sub_14fb4 in the divider's draw routine
# (10.3.9 addresses; located in other builds like the PATCHES sites)
DIVIDER_ANCHORS = [FRAMEDBOX_SKIP, FRAMEDBOX_RESUME, DIVIDER_CGRECT_CALL]

REF_PATH = __file__.rsplit('/', 2)[0] + '/orig/Finder-10.3.9'


def mask(w):
    op = w >> 26
    if op == 18: return w & 0xfc000003      # b/bl: drop displacement
    if op == 16: return w & 0xffff0003      # bc: drop displacement
    if op == 15: return w & 0xffff0000      # lis/addis: drop immediate
    if op in (48, 50): return w & 0xffff0000   # lfs/lfd of a constant: drop displacement
    return w


def text_words(m):
    s = m.section('__text')
    return s, [struct.unpack_from('>I', m.data, s['offset'] + 4*i)[0] for i in range(s['size'] // 4)]


def locate(ref, target):
    """Map each 10.3.9 patch address to its address in `target` (identity for the
    stock file; signature match for re-prebound copies)."""
    anchors = [p[1] for p in PATCHES] + DIVIDER_ANCHORS
    if ref.data == target.data:
        return {a: a for a in anchors}
    rs, rw = text_words(ref)
    ts, tw = text_words(target)
    tm = [mask(w) for w in tw]
    found = {}
    for a in anchors:
        i = (a - rs['addr']) // 4
        hits = []
        # symmetric context first, then left-only context
        for lo, hi in [(c, c) for c in range(8, 33, 4)] + [(c, 0) for c in range(8, 65, 4)]:
            sig = [mask(w) for w in rw[i-lo:i+hi+1]]
            hits = [j + lo for j in range(len(tm) - len(sig)) if tm[j:j+len(sig)] == sig]
            if len(hits) == 1:
                break
        if len(hits) != 1:
            sys.exit('cannot uniquely locate patch site %08x: %d candidates' % (a, len(hits)))
        found[a] = ts['addr'] + 4*hits[0]
    return found


def stub_addr(m, name):
    for s in m.sections:
        if s['type'] == 8:
            for a, n in m.imports.items():
                if n == name and s['addr'] <= a < s['addr'] + s['size']:
                    return a
    sys.exit('import %s not found' % name)


def place_cave(m, data, hook, quiet):
    """Write tools/cave.py's routine + constants into the free space at the
    end of __TEXT. Returns {'addr': routine, 'gray': border-line gray float}."""
    import cave
    last = max(x['addr'] + x['size'] for x in m.sections if x['seg'] == '__TEXT')
    seg = [x for x in m.segments if x['name'] == '__TEXT'][0]
    caddr = (last + 15) & ~15
    stubs = {nm: stub_addr(m, nm) for nm in cave.STUBS_NEEDED}
    code, gray = cave.build(caddr, hook, stubs)
    coff = m.addr2off(caddr)
    room = seg['vmaddr'] + seg['filesize'] - caddr
    if len(code) > room:
        sys.exit('gradient routine (%d bytes) does not fit in __TEXT padding (%d)' % (len(code), room))
    if any(data[coff:coff + len(code)]):
        sys.exit('__TEXT padding at %08x is not empty' % caddr)
    data[coff:coff + len(code)] = code
    if not quiet:
        print('cave      %08x file+%06x  %d bytes (routine + table + gray), %d free' % (
            caddr, coff, len(code), room - len(code)))
    return {'addr': caddr, 'gray': gray}


def place_fill(m, data, statusbar_branch, hook, quiet):
    """Write cave.build_fill_white() into EraseViewBackground's metal branch,
    which the 'statusbar' set makes unreachable (it starts right after the
    branch we make unconditional and ends at the Aqua branch)."""
    import cave
    start, end = statusbar_branch + 4, hook
    lit = [x for x in m.sections if x['sect'] == '__literal4'][0]
    ones = [lit['addr'] + k for k in range(0, lit['size'], 4)
            if bytes(data[lit['offset'] + k:lit['offset'] + k + 4]) == struct.pack('>f', 1.0)]
    assert ones, 'no 1.0f literal'
    stubs = {nm: stub_addr(m, nm) for nm in cave.FILL_STUBS}
    code = cave.build_fill_white(start, stubs, ones[0])
    assert len(code) <= end - start, 'fill helper too big for the dead branch'
    off = m.addr2off(start)
    data[off:off + len(code)] = code
    if not quiet:
        print('fill      %08x file+%06x  %d bytes (CGFillRectWhite) in dead metal branch, %d free' % (
            start, off, len(code), end - start - len(code)))
    return start




def place_divider(m, data, fill, sites, quiet):
    """Erase the sidebar divider before it draws its grip (window resizes)."""
    import cave
    ref = MachO(REF_PATH)
    def w(mm, a): return struct.unpack_from('>I', mm.data, mm.addr2off(a))[0]
    skip, resume = sites[FRAMEDBOX_SKIP], sites[FRAMEDBOX_RESUME]
    assert resume - skip == FRAMEDBOX_RESUME - FRAMEDBOX_SKIP, 'framed-box section has a different length'
    for k in range(0, resume - skip, 4):           # code must match the stock 10.3.9 code
        assert mask(w(m, skip + k)) == mask(w(ref, FRAMEDBOX_SKIP + k)), 'framed-box code differs at %08x' % (skip + k)
    hook = sites[DIVIDER_CGRECT_CALL]
    hw = w(m, hook)
    assert hw >> 26 == 18 and hw & 1, 'expected bl at %08x' % hook
    disp = hw & 0x03fffffc
    if disp & 0x02000000: disp -= 0x04000000
    cg_rect_fn = hook + disp
    body = fill + 0x10
    assert w2(data, m, body) == 0x7c7f1b78, 'fill helper body must start with mr r31,r3'
    stub = cave.Asm(skip)
    stub.li(30, 1)                                 # r30 = 1 is relied on later
    stub.li(0, 0)
    stub.stw(0, 0xa0, 1)                           # no region -> nothing to dispose
    stub.b(resume)
    code = stub.assemble()
    entry = skip + len(code)
    code += cave.build_divider_entry(entry, cg_rect_fn, body)
    assert skip + len(code) <= resume, 'divider entry does not fit'
    off = m.addr2off(skip)
    data[off:off + len(code)] = code
    struct.pack_into('>I', data, m.addr2off(hook), 0x48000001 | ((entry - hook) & 0x03fffffc))
    if not quiet:
        print('divider   %08x file+%06x  framed-box metal section skipped; erase entry at %08x (%d bytes free)' % (
            skip, off, entry, resume - skip - len(code)))
        print('divider   %08x file+%06x  %08x -> bl %08x  divider draw: erase before drawing the grip' % (
            hook, m.addr2off(hook), hw, entry))


def w2(data, m, a):
    return struct.unpack_from('>I', data, m.addr2off(a))[0]


def apply(path_in, path_out, names=SET_NAMES, quiet=False):
    ref, m = MachO(REF_PATH), MachO(path_in)
    sites = locate(ref, m)
    data = bytearray(m.data)
    cv = None
    if 'shadow' in names or 'softlines' in names:
        cv = place_cave(m, data, sites[0x23b90], quiet)
    fill = None
    if 'gap' in names:
        assert 'statusbar' in names, "'gap' needs 'statusbar' (its helper lives in the dead metal branch)"
        fill = place_fill(m, data, sites[0x23b0c], sites[0x23b90], quiet)
        place_divider(m, data, fill, sites, quiet)
    for p in PATCHES:
        name, refaddr, expect, action, why = p
        if name not in names:
            continue
        addr = sites[refaddr]
        off = m.addr2off(addr)
        cur = struct.unpack_from('>I', data, off)[0]
        if expect is not None and mask(cur) != mask(expect):
            sys.exit('mismatch at %08x: %08x != expected %08x (%s)' % (addr, cur, expect, why))
        if isinstance(action, int):
            new = action
        elif action[0] == 'bl':
            assert cur >> 26 == 18 and cur & 1, 'expected a bl at %08x' % addr
            new = 0x48000001 | ((stub_addr(m, action[1]) - addr) & 0x03fffffc)
        elif action[0] == 'bl_fill':
            assert cur >> 26 == 18 and cur & 1, 'expected a bl at %08x' % addr
            new = 0x48000001 | ((fill - addr) & 0x03fffffc)
        elif action[0] == 'cave':
            new = 0x48000000 | ((cv['addr'] - addr) & 0x03fffffc)
        elif action[0] == 'lfs_gray':
            # lfs f1,lo(0.6)(rB) after lis rB,hi -> load the lighter gray from the cave
            base = None
            for j in range(1, 6):
                pw = struct.unpack_from('>I', data, off - 4*j)[0]
                if pw >> 26 == 15 and (pw >> 16) & 31 == 0 and (pw >> 21) & 31 == (cur >> 16) & 31:
                    base = (pw & 0xffff) << 16
                    break
            assert base is not None, 'no lis base before lfs at %08x' % addr
            disp = cv['gray'] - base
            assert -0x8000 <= disp < 0x8000
            new = (cur & 0xffff0000) | (disp & 0xffff)
        elif action[0] == 'always':
            assert cur >> 26 == 16, 'expected a bc at %08x' % addr
            disp = cur & 0xfffc
            if disp & 0x8000: disp -= 0x10000
            new = 0x48000000 | (disp & 0x03fffffc)
        struct.pack_into('>I', data, off, new)
        if not quiet:
            print('%-9s %08x file+%06x  %08x -> %08x  %s' % (name, addr, off, cur, new, why))
    open(path_out, 'wb').write(bytes(data))
    return sites


if __name__ == '__main__':
    names = sys.argv[3].split(',') if len(sys.argv) > 3 else SET_NAMES
    apply(sys.argv[1], sys.argv[2], names)
