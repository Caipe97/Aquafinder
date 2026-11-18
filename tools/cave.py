"""Hand-assembled routines for the Panther Finder (see patch.py).

The status bar's background eraser (EraseViewBackground, see patch.py
'statusbar') ends in an Aqua branch:

    li r3,0x34 ; li r4,0x20 ; li r5,1 ; bl SetThemeBackground
    mr r3,r30  ; bl EraseRect           ; (falls through to the epilogue)

r30 = Rect* to erase (local coordinates, port already focused), r31 = view.
We replace the first instruction with a branch into the free space at the end
of __TEXT, where build_topbar's routine runs instead (float constants for the
lighter pane lines live right after it, see patch.py 'softlines'). The other
routines live in code the patches leave dead.
"""
import struct

# Gray of the lighter 1px lines (patch.py 'softlines'): 212, as Jaguar's pane
# borders.
BAR_LINE = 212

# Theme brush the status bar is erased with (the Aqua branch's own): the
# toolbar background, whose pinstripes the 'titlebars' theme repaints as
# Jaguar's, in phase with the toolbar art (theme.jaguar_toolbar_brush).
TOOLBAR_BRUSH = 0x34           # kThemeBrushToolbarBackground


R = {f'r{i}': i for i in range(32)}


def d_form(op, rt, ra, imm):
    return (op << 26) | (rt << 21) | (ra << 16) | (imm & 0xffff)


class Asm:
    def __init__(self, base):
        self.base, self.words, self.labels, self.fixups = base, [], {}, []

    @property
    def pc(self):
        return self.base + 4 * len(self.words)

    def label(self, name):
        self.labels[name] = self.pc

    def emit(self, w):
        self.words.append(w & 0xffffffff)

    # --- D-form loads/stores/arith
    def lwz(self, rt, d, ra):  self.emit(d_form(32, rt, ra, d))
    def stw(self, rs, d, ra):  self.emit(d_form(36, rs, ra, d))
    def lha(self, rt, d, ra):  self.emit(d_form(42, rt, ra, d))
    def sth(self, rs, d, ra):  self.emit(d_form(44, rs, ra, d))
    def addi(self, rt, ra, v): self.emit(d_form(14, rt, ra, v))
    def li(self, rt, v):       self.addi(rt, 0, v)
    def lis(self, rt, v):      self.emit(d_form(15, rt, 0, v))
    def cmpwi(self, ra, v):    self.emit((11 << 26) | (7 << 23) | (ra << 16) | (v & 0xffff))   # cr7

    # --- X-form
    def cmpw(self, ra, rb):    self.emit((31 << 26) | (7 << 23) | (ra << 16) | (rb << 11))     # cr7
    def subf(self, rt, ra, rb): self.emit((31 << 26) | (rt << 21) | (ra << 16) | (rb << 11) | (40 << 1))
    def lbzx(self, rt, ra, rb): self.emit((31 << 26) | (rt << 21) | (ra << 16) | (rb << 11) | (87 << 1))
    def mr(self, ra, rs):      self.emit((31 << 26) | (rs << 21) | (ra << 16) | (rs << 11) | (444 << 1))
    def rlwimi(self, ra, rs, sh, mb, me):
        self.emit((20 << 26) | (rs << 21) | (ra << 16) | (sh << 11) | (mb << 6) | (me << 1))

    def stwu(self, rs, d, ra): self.emit(d_form(37, rs, ra, d))
    def lfs(self, ft, d, ra):  self.emit(d_form(48, ft, ra, d))
    def stfs(self, fs, d, ra): self.emit(d_form(52, fs, ra, d))
    def fadds(self, ft, fa, fb): self.emit((59 << 26) | (ft << 21) | (fa << 16) | (fb << 11) | (21 << 1))
    def fsubs(self, ft, fa, fb): self.emit((59 << 26) | (ft << 21) | (fa << 16) | (fb << 11) | (20 << 1))
    def fcmpu(self, fa, fb):   self.emit((63 << 26) | (7 << 23) | (fa << 16) | (fb << 11))      # cr7
    def fmuls(self, ft, fa, fc): self.emit((59 << 26) | (ft << 21) | (fa << 16) | (fc << 6) | (25 << 1))
    def fmr(self, ft, fb):     self.emit((63 << 26) | (ft << 21) | (fb << 11) | (72 << 1))
    def lswi(self, rt, ra, nb): self.emit((31 << 26) | (rt << 21) | (ra << 16) | ((nb & 31) << 11) | (597 << 1))
    def stswi(self, rs, ra, nb): self.emit((31 << 26) | (rs << 21) | (ra << 16) | ((nb & 31) << 11) | (725 << 1))
    def mflr(self, rt):        self.emit((31 << 26) | (rt << 21) | (8 << 16) | (339 << 1))
    def mtlr(self, rs):        self.emit((31 << 26) | (rs << 21) | (8 << 16) | (467 << 1))
    def blr(self):             self.emit(0x4e800020)
    def nop(self):             self.emit(0x60000000)

    # --- branches (targets: int address or label name)
    def _br(self, kind, target, bo=0, bi=0):
        self.fixups.append((len(self.words), kind, target, bo, bi))
        self.emit(0)

    def b(self, t):  self._br('b', t)
    def bl(self, t): self._br('bl', t)
    def beq(self, t): self._br('bc', t, 12, 30)   # cr7 eq set
    def bne(self, t): self._br('bc', t, 4, 30)    # cr7 eq clear
    def bge(self, t): self._br('bc', t, 4, 28)    # cr7 lt clear
    def ble(self, t): self._br('bc', t, 4, 29)    # cr7 gt clear

    def data(self, bs):
        bs = bytes(bs) + bytes(-len(bs) % 4)
        for k in range(0, len(bs), 4):
            self.emit(struct.unpack('>I', bs[k:k+4])[0])

    def assemble(self):
        for idx, kind, t, bo, bi in self.fixups:
            here = self.base + 4 * idx
            dest = self.labels[t] if isinstance(t, str) else t
            disp = dest - here
            if kind in ('b', 'bl'):
                assert -(1 << 25) <= disp < (1 << 25)
                self.words[idx] = (18 << 26) | (disp & 0x03fffffc) | (kind == 'bl')
            else:
                assert -(1 << 15) <= disp < (1 << 15)
                self.words[idx] = (16 << 26) | (bo << 21) | (bi << 16) | (disp & 0xfffc)
        return b''.join(struct.pack('>I', w) for w in self.words)


STUBS_NEEDED = ['_GetForeColor', '_RGBForeColor', '_PaintRect', '_GetPort',
                '_GetPortBounds', '_SetThemeBackground', '_EraseRect']

# Status bar under the toolbar (patch.py 'topbar'): the bar is the top 20 rows
# of the window's port (the Finder's top status bar rect, top + 0x14), with
# Jaguar 10.2.8's 1px lines on its first and last row.
TOPBAR_ROWS = 20
TOPBAR_LINE = 163


def build_topbar(cave, hook, stubs, line_gray=BAR_LINE / 255.0):
    """cave: address of the routine; hook: address of the hooked 'li r3,0x34'
    (the host epilogue is at hook+0x18); stubs: import name -> stub address.
    The status bar of a browser window gets the usual Aqua erase, then the
    two lines.

    The erased rect can be just part of the bar (the text, when it changes),
    so the lines are placed from the port bounds, not from the rect; the
    object in r31 isn't the pane itself, so LPane's frame getters don't work
    on it. This needs its own stack frame (0x80); the host already saved LR.
    Returns (bytes, {'gray': address of the float line gray})."""
    a = Asm(cave)
    r0, r1, r3, r4, r5, r30, r31 = 0, 1, 3, 4, 5, 30, 31
    ret = hook + 0x18
    v16 = TOPBAR_LINE * 0x101
    a.lwz(r0, 0x120, r31)            # view->metal: the status bar of a browser window?
    a.cmpwi(r0, 0)
    a.beq('original')
    a.li(r3, 0x34)                   # the original Aqua erase
    a.li(r4, 0x20)
    a.li(r5, 1)
    a.bl(stubs['_SetThemeBackground'])
    a.mr(r3, r30)
    a.bl(stubs['_EraseRect'])
    a.stwu(r1, -0x80, r1)
    a.addi(r3, r1, 0x40)             # save pen color -> 0x40
    a.bl(stubs['_GetForeColor'])
    a.addi(r3, r1, 0x58)             # GetPort(0x58); GetPortBounds(port, 0x58)
    a.bl(stubs['_GetPort'])
    a.lwz(r3, 0x58, r1)
    a.addi(r4, r1, 0x58)
    a.bl(stubs['_GetPortBounds'])
    a.li(r0, v16 - 0x10000 if v16 >= 0x8000 else v16)
    a.sth(r0, 0x60, r1)
    a.sth(r0, 0x62, r1)
    a.sth(r0, 0x64, r1)
    a.addi(r3, r1, 0x60)
    a.bl(stubs['_RGBForeColor'])
    a.lha(r5, 0x58, r1)              # row = {port.top, port.left, port.top + 1, port.right}
    a.sth(r5, 0x68, r1)
    a.addi(r0, r5, 1)
    a.sth(r0, 0x6c, r1)
    a.lha(r0, 0x5a, r1)
    a.sth(r0, 0x6a, r1)
    a.lha(r0, 0x5e, r1)
    a.sth(r0, 0x6e, r1)
    a.addi(r3, r1, 0x68)
    a.bl(stubs['_PaintRect'])        # top line
    a.lha(r5, 0x58, r1)              # row = port.top + TOPBAR_ROWS - 1
    a.addi(r5, r5, TOPBAR_ROWS - 1)
    a.sth(r5, 0x68, r1)
    a.addi(r0, r5, 1)
    a.sth(r0, 0x6c, r1)
    a.addi(r3, r1, 0x68)
    a.bl(stubs['_PaintRect'])        # bottom line
    a.addi(r3, r1, 0x40)             # restore pen color
    a.bl(stubs['_RGBForeColor'])
    a.addi(r1, r1, 0x80)
    a.b(ret)

    a.label('original')              # not a browser window: original Aqua erase
    a.li(r3, 0x34)
    a.b(hook + 4)

    a.label('line_gray')             # float gray for the 1px lines (patch.py 'softlines')
    a.data(struct.pack('>f', line_gray))
    return a.assemble(), {'gray': a.labels['line_gray']}


# Theme brush the sidebar divider is erased with: plain white, like the panes
# on both sides of it (their side borders are gone, patch.py 'gap'), so only
# its grip shows.
DIVIDER_BRUSH = -2             # kThemeBrushWhite


def build_divider_erase(addr, stubs, frame_fn, ext, brush=DIVIDER_BRUSH):
    """DividerErase, called instead of `bl GetWindowPort` right before the
    sidebar divider opens its QDBeginCGContext bracket, both in its draw
    routine and in the splitter repaint while it is dragged (r31 = the
    divider view in both). In a metal window the Window Manager painted metal
    behind the divider; in an Aqua window nothing erases it (a trail of grips
    when resizing). QuickDraw drawing inside the bracket is never seen, so
    erase here, before it opens:

        frame_fn(&r, divider)            divider frame, port coordinates
        OffsetRect(&r, port origin)      -> local (the port may be focused with
                                            an origin, e.g. under a top status bar)
        r.bottom -= 1                    keep the bottom row: the panes' border
                                         line, painted by the bar
        SetThemeBackground(brush)
        b ext: DividerOutset (build_divider_outset) widens r by the 1px
        columns on both sides and erases it, then branches back to 'back'

    then tail-call GetWindowPort with the host's r3 (its window).
    Returns (bytes, address of 'back')."""
    a = Asm(addr)
    r0, r1, r3, r4, r5, r31 = 0, 1, 3, 4, 5, 31
    a.mflr(r0)
    a.stw(r0, 8, r1)
    a.stwu(r1, -0x60, r1)
    a.stw(r3, 0x58, r1)              # the window, for GetWindowPort
    a.addi(r3, r1, 0x40)             # r = divider frame (port coordinates)
    a.mr(r4, r31)
    a.bl(frame_fn)
    a.addi(r3, r1, 0x50)             # GetPortBounds(GetPort()) -> 0x48
    a.bl(stubs['_GetPort'])
    a.lwz(r3, 0x50, r1)
    a.addi(r4, r1, 0x48)
    a.bl(stubs['_GetPortBounds'])
    a.addi(r3, r1, 0x40)             # OffsetRect(&r, origin.h, origin.v)
    a.lha(r4, 0x4a, r1)
    a.lha(r5, 0x48, r1)
    a.bl(stubs['_OffsetRect'])
    a.lha(r4, 0x44, r1)              # r.bottom -= 1 (not r0: addi reads it as 0)
    a.addi(r4, r4, -1)
    a.sth(r4, 0x44, r1)
    a.li(r3, brush)
    a.li(r4, 32)                     # depth
    a.li(r5, 1)                      # isColorDevice
    a.bl(stubs['_SetThemeBackground'])
    a.b(ext)                         # DividerOutset: widen r, EraseRect(&r)
    a.label('back')
    a.lwz(r3, 0x58, r1)
    a.addi(r1, r1, 0x60)
    a.lwz(r0, 8, r1)
    a.mtlr(r0)
    a.b(stubs['_GetWindowPort'])
    return a.assemble(), a.labels['back']


def build_divider_outset(addr, back, stubs):
    """DividerOutset, the tail of DividerErase (branched to and back, on its
    stack frame: r at 0x40). The 1px columns on either side of the divider
    are neither the divider's nor the panes' (they held the panes' side
    borders, which 'gap' no longer draws), so erase them with the divider:
    r.left -= 1, r.right += 1, EraseRect(&r)."""
    a = Asm(addr)
    r1, r3, r4 = 1, 3, 4
    a.lha(r4, 0x42, r1)              # not r0: addi reads it as 0
    a.addi(r4, r4, -1)
    a.sth(r4, 0x42, r1)
    a.lha(r4, 0x46, r1)
    a.addi(r4, r4, 1)
    a.sth(r4, 0x46, r1)
    a.addi(r3, r1, 0x40)
    a.bl(stubs['_EraseRect'])
    a.b(back)
    return a.assemble()


DIVIDER_STUBS = ['_GetPort', '_GetPortBounds', '_OffsetRect', '_SetThemeBackground',
                 '_EraseRect', '_GetWindowPort']


def build_splitter_draw(addr, image, cgrect_fn, done, stubs):
    """The search results' horizontal splitter (the framed-box painter, between
    the results and the path pane), drawn as Panther's Aqua splitter bar: the
    image 'PNG ' 8801 (tools/grip.py, SPLITTER_WIDTH x 9, the grip in its center
    columns), which the painter's own loader has just made (r30 = &image, as
    after its one-time load). In the painter's frame (ctx at 0x74) and in
    place of its centered draw of the grip:

        cgrect_fn(&box, view, qdRect)         the box, CG (0xd0; r31, r25 as there)
        CGContextClipToRect(ctx, box)
        CGContextSetInterpolationQuality(ctx, none)   1:1 pixels
        CGContextDrawImage(ctx, {box.x + round(box.w/2) - W/2, box.y, W, box.h}, image)
        b done

    The image covers the box, its frame included (the bar's own lines)."""
    a = Asm(addr)
    r0, r1, r3, r4, r5, r8, r12, r25, r30, r31 = 0, 1, 3, 4, 5, 8, 12, 25, 30, 31
    def fconst(fr, bits):                          # fr = float with these bits (scratch at 0xe0)
        a.lis(r0, bits >> 16)
        a.stw(r0, 0xe0, r1)
        a.lfs(fr, 0xe0, r1)
    a.addi(r3, r1, 0xd0)
    a.mr(r4, r31)
    a.mr(r5, r25)
    a.bl(cgrect_fn)
    a.lwz(r3, 0x74, r1)
    a.addi(r12, r1, 0xd0)
    a.lswi(r4, r12, 16)
    a.bl(stubs['_CGContextClipToRect'])
    a.lwz(r3, 0x74, r1)
    a.li(r4, 1)                                    # kCGInterpolationNone
    a.bl(stubs['_CGContextSetInterpolationQuality'])
    a.lfs(1, 0xd8, r1)                             # x = box.x + round(box.w * 0.5) - W/2
    fconst(0, 0x3f000000)                          # 0.5
    a.fmuls(1, 1, 0)
    fconst(0, 0x4b000000)                          # 2^23: adding it rounds to a whole number
    a.fadds(1, 1, 0)                               # (box.x is one already: a whole pixel,
    a.fsubs(1, 1, 0)                               #  not blended over two)
    a.lfs(3, 0xd0, r1)
    a.fadds(3, 3, 1)
    fconst(0, struct.unpack('>I', struct.pack('>f', image / 2))[0])
    a.fsubs(3, 3, 0)
    a.stfs(3, 0xd0, r1)
    a.lis(r0, struct.unpack('>I', struct.pack('>f', image))[0] >> 16)
    a.stw(r0, 0xd8, r1)                            # width W (y, height: the box's)
    a.lwz(r3, 0x74, r1)
    a.addi(r12, r1, 0xd0)
    a.lswi(r4, r12, 16)
    a.lwz(r8, 0, r30)
    a.bl(stubs['_CGContextDrawImage'])
    a.b(done)
    return a.assemble()


SPLITTER_STUBS = ['_CGContextClipToRect', '_CGContextSetInterpolationQuality', '_CGContextDrawImage']


def build_cgrect_port(addr, cg_rect_fn, stubs):
    """A second entry into the QD rect -> CGRect converter (cg_rect_fn,
    sub_14fb4 in 10.3.9) for rects in port coordinates (patch.py 'topbar').

    The converter flips y with the window's content height, which matches
    the CG context only while the port origin is (0, 0). With the status bar
    on top, the browser panes sit 20 rows down and are focused with origin
    (0, -20). Most callers pass local rects and come out right, but the
    sidebar divider's own drawing (its grip and the pane border lines,
    and the splitter repaint) passes port rects (CalcPortFrameRect) and
    landed 20 rows low. Those callers call entry 'port' instead.

    Layout (23 words, in the bottom-status-bar branch that 'topbar' leaves
    dead): 'port' = the converter's prologue + r31 = 1; 'normal' = the
    prologue's last word + r31 = 0 (the converter's own prologue branches
    here); 'top' = the hooked 'lha r0,0x48(r1)' (content top), plus the port
    origin when r31 = 1. r31 is saved by the converter's stmw r28 and unused
    in its body; 0x38..0x3f of its 0x60 frame are free.
    Returns (bytes, {'port', 'normal', 'top'} addresses)."""
    a = Asm(addr)
    r0, r1, r3, r4, r5, r28, r31 = 0, 1, 3, 4, 5, 28, 31
    body = cg_rect_fn + 0x14          # after mflr/stmw/stw/mr r28,r3/stwu
    a.label('port')
    a.mflr(r0)
    a.emit(0xbf81fff0)                # stmw r28,-0x10(r1)
    a.stw(r0, 8, r1)
    a.mr(r28, r3)
    a.stwu(r1, -0x60, r1)
    a.li(r31, 1)
    a.b(body)
    a.label('normal')
    a.stwu(r1, -0x60, r1)
    a.li(r31, 0)
    a.b(body)
    a.label('top')
    a.lha(r0, 0x48, r1)               # the hooked instruction: content top
    a.cmpwi(r31, 0)
    a.beq('back')
    a.addi(r3, r1, 0x38)              # top += GetPortBounds(GetPort()).top
    a.bl(stubs['_GetPort'])
    a.lwz(r3, 0x38, r1)
    a.addi(r4, r1, 0x38)
    a.bl(stubs['_GetPortBounds'])
    a.lha(r0, 0x48, r1)
    a.lha(r5, 0x38, r1)
    a.emit(0x7c002a14)                # add r0,r0,r5
    a.label('back')
    a.b(cg_rect_fn + 0x3c)            # the word after the hooked one
    code = a.assemble()
    return code, {k: a.labels[k] for k in ('port', 'normal', 'top')}


CGRECT_STUBS = ['_GetPort', '_GetPortBounds']


# Tiger 10.4.11 (patch.py TIGER_PATCHES 'shadow'): the status bar view's Draw
# (vtable slot 0xe4, sub_42de4) calls its background fill sub_3f360(view, ctx)
# (transparent: the window's white shows), then draws a 1px gray line (163)
# on its bottom row. That call goes through build_tiger_bar's routine instead:
# the original fill, then the rows above the bottom one in Jaguar's toolbar
# pinstripes (as Panther's 'shadow' erases the bar with the toolbar brush).
# The 163 line above the bar is the toolbar's own bottom line, so the bar
# (19 rows, patch.py 'topbar') reads as Panther's: line, 18 stripes, line.
# top_line=True draws a 163 line on the bar's top row too. HIView coordinates:
# y down.
TIGER_BAR_FILL = 0x3f360       # sub_3f360(view, ctx): the view's background fill
TIGER_VIEW_BOUNDS = 0x13d48    # sub_13d48(&rect, view): HIViewGetBounds
TIGER_BAR_STUBS = ['_CGContextSetRGBFillColor', '_CGContextFillRect']
PINSTRIPES = (250, 255, 250, 233)   # Jaguar's toolbar rows below the top line


def build_tiger_bar(cave, stubs, line=TOPBAR_LINE, top_line=False):
    """cave: where the routine goes (constants first, then the entry point).
    Called as fill(view r3, ctx r4). Returns (bytes, entry address)."""
    consts = struct.pack('>6f', 1.0, line / 255.0, *[g / 255.0 for g in PINSTRIPES])
    ONE, LINE, TAB, TAB_END = 0, 4, 8, 8 + 4 * len(PINSTRIPES)
    entry = cave + len(consts)
    a = Asm(cave)
    a.data(consts)
    hi, lo = (cave + 0x8000) >> 16, cave & 0xffff
    r0, r1, r3, r4, r8, r9, r28, r29, r30, r31 = 0, 1, 3, 4, 8, 9, 28, 29, 30, 31
    f0, f1, f2, f3, f4, f13 = 0, 1, 2, 3, 4, 13
    # frame 0x80: 0x40 bounds {x, y, w, h}; 0x50 row rect {x, y, w, 1}; 0x60 end y
    a.mflr(r0)
    a.stw(r0, 8, r1)
    a.stwu(r1, -0x80, r1)
    for k, rr in enumerate((r28, r29, r30, r31)):
        a.stw(rr, 0x70 + 4 * k, r1)
    a.mr(r30, r3)                         # view
    a.mr(r31, r4)                         # ctx
    a.bl(TIGER_BAR_FILL)                  # the original fill
    a.addi(r3, r1, 0x40)
    a.mr(r4, r30)
    a.bl(TIGER_VIEW_BOUNDS)
    a.lis(r29, hi)
    a.addi(r29, r29, lo)                  # r29 = constants
    a.lfs(f0, 0x40, r1); a.stfs(f0, 0x50, r1)     # row.x = x
    a.lfs(f0, 0x44, r1)                           # row.y = y (the top row), or
    if not top_line:                              # y - 1 when the loop starts there
        a.lfs(f13, ONE, r29)
        a.fsubs(f0, f0, f13)
    a.stfs(f0, 0x54, r1)
    a.lfs(f0, 0x48, r1); a.stfs(f0, 0x58, r1)     # row.w = w
    a.lfs(f0, ONE, r29); a.stfs(f0, 0x5c, r1)     # row.h = 1
    a.lfs(f13, 0x4c, r1)                  # end = y + h - 1 (the bottom line's row)
    a.lfs(f0, 0x44, r1)
    a.fadds(f0, f0, f13)
    a.lfs(f13, ONE, r29)
    a.fsubs(f0, f0, f13)
    a.stfs(f0, 0x60, r1)
    if top_line:
        a.mr(r3, r31)
        a.lfs(f1, LINE, r29); a.fmr(f2, f1); a.fmr(f3, f1); a.lfs(f4, ONE, r29)
        a.bl(stubs['_CGContextSetRGBFillColor'])
        a.mr(r3, r31)
        a.addi(r8, r1, 0x50)
        a.lswi(r4, r8, 16)
        a.bl(stubs['_CGContextFillRect'])
    a.addi(r28, r29, TAB)                 # r28 = this row's gray
    a.label('row')
    a.lfs(f0, 0x54, r1)                   # next row: y += 1; stop at the bottom line
    a.lfs(f13, ONE, r29)
    a.fadds(f0, f0, f13)
    a.stfs(f0, 0x54, r1)
    a.lfs(f13, 0x60, r1)
    a.fcmpu(f0, f13)
    a.bge('done')
    a.mr(r3, r31)
    a.lfs(f1, 0, r28); a.fmr(f2, f1); a.fmr(f3, f1); a.lfs(f4, ONE, r29)
    a.bl(stubs['_CGContextSetRGBFillColor'])
    a.mr(r3, r31)
    a.addi(r8, r1, 0x50)
    a.lswi(r4, r8, 16)
    a.bl(stubs['_CGContextFillRect'])
    a.addi(r28, r28, 4)                   # next gray, wrapping after the last
    a.addi(r9, r29, TAB_END)
    a.cmpw(r28, r9)
    a.bne('row')
    a.addi(r28, r29, TAB)
    a.b('row')
    a.label('done')
    for k, rr in enumerate((r28, r29, r30, r31)):
        a.lwz(rr, 0x70 + 4 * k, r1)
    a.addi(r1, r1, 0x80)
    a.lwz(r0, 8, r1)
    a.mtlr(r0)
    a.blr()
    return a.assemble(), entry


# Tiger 10.4.11 (patch.py TIGER_PATCHES 'gap'): the sidebar divider. The
# splitter view's Draw (sub_3f234) calls sub_3f304: its background fill, then
# the virtual DrawDivider(view, ctx, &rect) (vtable slot 0x168, sub_3f3f8:
# Tiger's dimple, HIThemeDrawPaneSplitter); then it outlines both panes. The
# call goes to build_tiger_divider's routine instead: the column view's gradient (grip.py
# GRADIENT), 15 columns from one left of the 13 px divider (the panes' 1px
# outline columns, now that the outlines are gone, are the outer two), and the
# grip's two ridges (grip.RIDGES), RIDGE_ROWS long, ending GRIP_BOTTOM rows
# above the divider's bottom (the window's), as in Panther.
TIGER_GRIP_BOTTOM = 4


TIGER_DIVIDER_RECT = 0xe0      # the splitter's divider rect {x, y, w, h}


def build_tiger_divider(cave, stubs):
    """cave: where the routine goes (constants first). Two entry points:
    draw(view r3, ctx r4, rect* r5) draws the divider into rect; the second,
    returned, stands in for the splitter Draw's call of sub_3f304 (view r3,
    ctx r4): the background fill, then the divider into the view's own
    divider rect, so the vtable (in __DATA, rewritten by re-prebinding's
    neighbours) is left alone. Returns (bytes, the second entry)."""
    import grip
    grays = [g / 255.0 for g in grip.GRADIENT]
    (c1, g1), (c2, g2) = grip.RIDGES
    consts = struct.pack('>%df' % (4 + len(grays)), 1.0, float(grip.RIDGE_ROWS),
                         float(grip.RIDGE_ROWS + TIGER_GRIP_BOTTOM), 0.0, *grays)
    consts += struct.pack('>2f', g1 / 255.0, g2 / 255.0)
    ONE, RIDGE_H, RIDGE_UP, TAB = 0, 4, 8, 16
    TAB_END = TAB + 4 * len(grays)
    RG1, RG2 = TAB_END, TAB_END + 4
    entry = cave + len(consts)
    a = Asm(cave)
    a.data(consts)
    hi, lo = (cave + 0x8000) >> 16, cave & 0xffff
    r0, r1, r3, r4, r5, r8, r9, r28, r29, r31 = 0, 1, 3, 4, 5, 8, 9, 28, 29, 31
    f0, f1, f2, f3, f4, f13 = 0, 1, 2, 3, 4, 13
    # frame 0x80: 0x40 divider rect {x, y, w, h}; 0x50 fill rect {x, y, w, h}
    a.mflr(r0)
    a.stw(r0, 8, r1)
    a.stwu(r1, -0x80, r1)
    for k, rr in enumerate((r28, r29, r31)):
        a.stw(rr, 0x70 + 4 * k, r1)
    a.mr(r31, r4)                         # ctx
    a.mr(r9, r5)                          # the divider rect -> 0x40 (via r5..r8;
    a.lswi(r5, r9, 16)                    # lswi's base must be outside them)
    a.addi(r9, r1, 0x40)
    a.stswi(r5, r9, 16)
    a.lis(r29, hi)
    a.addi(r29, r29, lo)                  # r29 = constants
    a.lfs(f0, 0x40, r1); a.lfs(f13, ONE, r29); a.fsubs(f0, f0, f13)
    a.stfs(f0, 0x50, r1)                  # column x = x - 1
    a.lfs(f0, 0x44, r1); a.stfs(f0, 0x54, r1)     # y
    a.stfs(f13, 0x58, r1)                 # w = 1
    a.lfs(f0, 0x4c, r1); a.stfs(f0, 0x5c, r1)     # h
    a.addi(r28, r29, TAB)                 # r28 = this column's gray
    a.label('col')
    a.mr(r3, r31)
    a.lfs(f1, 0, r28); a.fmr(f2, f1); a.fmr(f3, f1); a.lfs(f4, ONE, r29)
    a.bl(stubs['_CGContextSetRGBFillColor'])
    a.mr(r3, r31)
    a.addi(r9, r1, 0x50)
    a.lswi(r4, r9, 16)
    a.bl(stubs['_CGContextFillRect'])
    a.lfs(f0, 0x50, r1); a.lfs(f13, ONE, r29); a.fadds(f0, f0, f13)
    a.stfs(f0, 0x50, r1)
    a.addi(r28, r28, 4)
    a.addi(r9, r29, TAB_END)
    a.cmpw(r28, r9)
    a.bne('col')
    # the ridges: {x - 1 + col, y + h - (RIDGE_ROWS + GRIP_BOTTOM), 1, RIDGE_ROWS}
    a.lfs(f0, 0x44, r1); a.lfs(f13, 0x4c, r1); a.fadds(f0, f0, f13)
    a.lfs(f13, RIDGE_UP, r29); a.fsubs(f0, f0, f13)
    a.stfs(f0, 0x54, r1)
    a.lfs(f0, RIDGE_H, r29); a.stfs(f0, 0x5c, r1)
    for col, gray in ((c1, RG1), (c2, RG2)):
        a.lfs(f0, 0x40, r1)               # x - 1 + col
        a.lfs(f13, ONE, r29)
        a.fsubs(f0, f0, f13)
        for _ in range(col):
            a.fadds(f0, f0, f13)
        a.stfs(f0, 0x50, r1)
        a.mr(r3, r31)
        a.lfs(f1, gray, r29); a.fmr(f2, f1); a.fmr(f3, f1); a.lfs(f4, ONE, r29)
        a.bl(stubs['_CGContextSetRGBFillColor'])
        a.mr(r3, r31)
        a.addi(r9, r1, 0x50)
        a.lswi(r4, r9, 16)
        a.bl(stubs['_CGContextFillRect'])
    for k, rr in enumerate((r28, r29, r31)):
        a.lwz(rr, 0x70 + 4 * k, r1)
    a.addi(r1, r1, 0x80)
    a.lwz(r0, 8, r1)
    a.mtlr(r0)
    a.blr()
    # draw_all(view, ctx): sub_3f360(view, ctx), then draw(view, ctx, &view->rect)
    r30 = 30
    a.label('draw_all')
    a.mflr(r0)
    a.stw(r0, 8, r1)
    a.stwu(r1, -0x60, r1)
    a.stw(r30, 0x50, r1)
    a.stw(r31, 0x54, r1)
    a.mr(r30, r3)
    a.mr(r31, r4)
    a.bl(TIGER_BAR_FILL)
    a.mr(r3, r30)
    a.mr(r4, r31)
    a.addi(r5, r30, TIGER_DIVIDER_RECT)
    a.bl(entry)
    a.lwz(r30, 0x50, r1)
    a.lwz(r31, 0x54, r1)
    a.addi(r1, r1, 0x60)
    a.lwz(r0, 8, r1)
    a.mtlr(r0)
    a.blr()
    return a.assemble(), a.labels['draw_all']


# Tiger 10.4.11 (patch.py TIGER_PATCHES 'softlines'): lighter 1px lines, 212
# (BAR_LINE, Jaguar's pane borders), as RGBA floats {g, g, g, 1}: the search
# scope bar's bottom line loads its first word (the gray) instead of 0.54
# (138), and the search window's path pane strokes its frame with it instead
# of its own 158 gray.
def build_tiger_line(cave, stubs, gray=BAR_LINE):
    """Constants only (no code). Returns (bytes, address of the RGBA gray,
    address of the float gray: the same)."""
    g = gray / 255.0
    return struct.pack('>4f', g, g, g, 1.0), cave, cave
