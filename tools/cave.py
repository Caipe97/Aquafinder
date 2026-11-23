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
    def blt(self, t): self._br('bc', t, 12, 28)   # cr7 lt set
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


def build_topbar(cave, hook, stubs, line_gray=BAR_LINE / 255.0, keep_last_row=False):
    """cave: address of the routine; hook: address of the hooked 'li r3,0x34'
    (the host epilogue is at hook+0x18); stubs: import name -> stub address.
    The status bar of a browser window gets the usual Aqua erase, then the
    two lines.

    The erased rect can be just part of the bar (the text, when it changes),
    so the lines are placed from the port bounds, not from the rect; the
    object in r31 isn't the pane itself, so LPane's frame getters don't work
    on it. This needs its own stack frame (0x80); the host already saved LR.
    keep_last_row (the 'header' and 'well' sidebar styles): the bar's last
    row is left alone, neither erased nor lined: the splitter paints it
    (the top edge of the sidebar and the files, patch.py EDGE_*), so the
    erase goes to a copy of the rect, clipped above that row.
    Returns (bytes, {'gray': address of the float line gray})."""
    a = Asm(cave)
    r0, r1, r3, r4, r5, r30, r31 = 0, 1, 3, 4, 5, 30, 31
    ret = hook + 0x18
    v16 = TOPBAR_LINE * 0x101
    a.lwz(r0, 0x120, r31)            # view->metal: the status bar of a browser window?
    a.cmpwi(r0, 0)
    a.beq('original')
    if keep_last_row:
        a.stwu(r1, -0x80, r1)
        a.addi(r3, r1, 0x58)         # GetPort(0x58); GetPortBounds(port, 0x58)
        a.bl(stubs['_GetPort'])
        a.lwz(r3, 0x58, r1)
        a.addi(r4, r1, 0x58)
        a.bl(stubs['_GetPortBounds'])
        a.lwz(r0, 0, r30); a.stw(r0, 0x70, r1)      # the rect, clipped above the last row
        a.lwz(r0, 4, r30); a.stw(r0, 0x74, r1)
        a.lha(r5, 0x58, r1)
        a.addi(r5, r5, TOPBAR_ROWS - 1)
        a.lha(r0, 0x74, r1)
        a.cmpw(r0, r5)
        a.ble('clipped')
        a.sth(r5, 0x74, r1)
        a.label('clipped')
        a.li(r3, 0x34)               # the original Aqua erase, of the copy
        a.li(r4, 0x20)
        a.li(r5, 1)
        a.bl(stubs['_SetThemeBackground'])
        a.addi(r3, r1, 0x70)
        a.bl(stubs['_EraseRect'])
        a.addi(r3, r1, 0x40)         # save pen color -> 0x40
        a.bl(stubs['_GetForeColor'])
    else:
        a.li(r3, 0x34)               # the original Aqua erase
        a.li(r4, 0x20)
        a.li(r5, 1)
        a.bl(stubs['_SetThemeBackground'])
        a.mr(r3, r30)
        a.bl(stubs['_EraseRect'])
        a.stwu(r1, -0x80, r1)
        a.addi(r3, r1, 0x40)         # save pen color -> 0x40
        a.bl(stubs['_GetForeColor'])
        a.addi(r3, r1, 0x58)         # GetPort(0x58); GetPortBounds(port, 0x58)
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
    if not keep_last_row:
        a.lha(r5, 0x58, r1)          # row = port.top + TOPBAR_ROWS - 1
        a.addi(r5, r5, TOPBAR_ROWS - 1)
        a.sth(r5, 0x68, r1)
        a.addi(r0, r5, 1)
        a.sth(r0, 0x6c, r1)
        a.addi(r3, r1, 0x68)
        a.bl(stubs['_PaintRect'])    # bottom line
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


def build_divider_erase(addr, stubs, frame_fn, ext, brush=DIVIDER_BRUSH, bottom_row=False):
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
    bottom_row ('well'): erase the bottom row too (no border line there, and
    nothing else paints it).
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
    if not bottom_row:
        a.lha(r4, 0x44, r1)          # r.bottom -= 1 (not r0: addi reads it as 0)
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


def build_divider_outset(addr, back, stubs, outset=1):
    """DividerOutset, the tail of DividerErase (branched to and back, on its
    stack frame: r at 0x40). The 1px columns on either side of the divider
    are neither the divider's nor the panes' (they held the panes' side
    borders, which 'gap' no longer draws), so erase them with the divider:
    r.left -= 1, r.right += 1, EraseRect(&r). (With 'stripes' the panes have
    no border, those columns are theirs: outset 0, the divider's frame only.)"""
    a = Asm(addr)
    r1, r3, r4 = 1, 3, 4
    a.lha(r4, 0x42, r1)              # not r0: addi reads it as 0
    a.addi(r4, r4, -outset)
    a.sth(r4, 0x42, r1)
    a.lha(r4, 0x46, r1)
    a.addi(r4, r4, outset)
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


# Browser windows (TFileViewerWindow) draw their status bar only when it's
# laid out, resized or shown, never on an update: in a metal window the
# window's own background under it hid that. In an Aqua window an update
# erases it white for good -- e.g. a window shown while the display sleeps,
# whose first update comes after Show drew the bar. The sidebar splitter
# (TSidebarSplitter, which holds the sidebar and the file pane) draws on
# every update of the panes, so its DrawSelf ends in build_splitter_bar:
# if the port is a browser window's, its bar is drawn too.
BAR_FIELD = 0x1f4              # TFileViewerWindow: its status bar (or 0)
BAR_HIDDEN_FIELD = 0x248       # TFileViewerWindow: 1 when the bar is hidden (Show skips it)
SPLITTER_BAR_STUBS = ['_GetPort', '_GetWindowFromPort', '_GetWRefCon']


def build_splitter_bar(addr, tail, vptr, bar_draw, stubs):
    """Two pieces (the free spaces are small): (head at addr, tail at tail).
    Entered by a branch from the splitter's DrawSelf epilogue (its frame
    gone, LR = its caller): if the current port's window is a browser window
    (LWindow* in its refcon, as PowerPlant keeps it; vtable vptr) with its
    status bar shown, bar_draw(bar). Returns to the DrawSelf caller."""
    r0, r1, r3, r12 = 0, 1, 3, 12
    t = Asm(tail)
    t.lwz(r3, BAR_FIELD, r3)         # window->statusBar
    t.cmpwi(r3, 0)
    t.beq('out')
    t.bl(bar_draw)
    t.label('out')
    t.addi(r1, r1, 0x50)
    t.lwz(r0, 8, r1)
    t.mtlr(r0)
    t.blr()
    tail_code, out = t.assemble(), t.labels['out']

    a = Asm(addr)
    a.mflr(r0)
    a.stw(r0, 8, r1)
    a.stwu(r1, -0x50, r1)
    a.addi(r3, r1, 0x40)             # GetPort(&port)
    a.bl(stubs['_GetPort'])
    a.lwz(r3, 0x40, r1)
    a.bl(stubs['_GetWindowFromPort'])
    a.cmpwi(r3, 0)
    a.beq('no')
    a.bl(stubs['_GetWRefCon'])       # the LWindow
    a.cmpwi(r3, 0)
    a.beq('no')
    a.lwz(r0, 0, r3)                 # a TFileViewerWindow?
    a.lis(r12, (vptr + 0x8000) >> 16)
    lo = vptr & 0xffff
    a.addi(r12, r12, lo - 0x10000 if lo >= 0x8000 else lo)
    a.cmpw(r0, r12)
    a.bne('no')
    a.lwz(r0, BAR_HIDDEN_FIELD, r3)  # its bar shown?
    a.cmpwi(r0, 1)
    a.beq('no')
    a.b(tail)
    a.label('no')                    # (the tail is out of a conditional branch's reach)
    a.b(out)
    return a.assemble(), tail_code


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


def build_tiger_bar(cave, stubs, line=TOPBAR_LINE, top_line=False, stash=None):
    """cave: where the routine goes (constants first, then the entry point).
    Called as fill(view r3, ctx r4). stash ('well'): the address of a word
    the view goes to, for the status bar's edge routine later in the same
    draw (build_tiger_edge). Returns (bytes, entry address)."""
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
    if stash:
        a.lis(r9, (stash + 0x8000) >> 16)
        a.stw(r3, stash & 0xffff, r9)
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


# The View control's image loader (Panther 'toolbar', see patch.py
# place_view_loader): 15 copies of one block, each loading 'PNG ' <id> into
# the control's image vector (operator new, GetResource, the image's
# constructor, push_back). Its last two blocks become a loop over the ids
# from that of the first of them up to `end` (exclusive), so the vector gets
# 18 images: 6 per segment instead of 5. The counter lives at 0x3c(r1), a
# free word of the loader's frame (its locals are 0x40..0x4f).
VIEW_LOADER_COUNTER = 0x3c


def build_view_loader(addr, block, block_addr, end, done, landing):
    """block: the words of the original block at block_addr (29: the last
    one has no landing pad word, so the one before it is passed); done: the
    epilogue; landing: the shared exception landing pad. Returns code to be
    written at addr (= block_addr)."""
    assert len(block) == 29 and block[3] >> 16 == 0x3880, 'expected li r4,<id> in the block'
    first = block[3] & 0xffff
    a = Asm(addr)
    a.li(0, first)
    a.stw(0, VIEW_LOADER_COUNTER, 1)
    a.label('body')
    for k, w in enumerate(block):
        src = block_addr + 4 * k
        if k == 3:
            a.lwz(4, VIEW_LOADER_COUNTER, 1)              # li r4,<id> -> the counter
        elif w >> 26 == 18:                               # b/bl: same target from here
            disp = w & 0x03fffffc
            if disp & 0x02000000: disp -= 0x04000000
            target = src + disp
            if k == 28:
                target = landing
            if not (block_addr <= target <= block_addr + 4 * 29):   # the block's own exits (to the next block) reach 'next'
                (a.bl if w & 1 else a.b)(target)
            else:
                a.emit(w)
        else:
            a.emit(w)                                     # bc's stay inside the block
    a.label('next')                                       # the block's own exits land here
    a.lwz(4, VIEW_LOADER_COUNTER, 1)
    a.addi(4, 4, 1)
    a.stw(4, VIEW_LOADER_COUNTER, 1)
    a.cmpwi(4, end)
    a.blt('body')
    a.b(done)
    code = a.assemble()
    assert a.labels['next'] - a.labels['body'] == 4 * 29
    return code


# --- 'stripes' (patch.py): a pinstriped sidebar (Panther 10.3.9).
#
# The sidebar view (TSidebarView) and its items fill their background with
# the view's back color, white, in CoreGraphics: the whole view in its draw
# (sub_16444), one item when it redraws alone (sub_ffa4) and while an item
# is dragged (sub_18f784). Each fill calls SidebarStripes(ctx, &rect)
# instead: 1 px rows in the window's pinstripe grays, each the gray of its
# QuickDraw row, so the stripes are in phase with the status bar's and the
# divider's (both erased with the toolbar brush, which QuickDraw aligns to
# the port).
STRIPE_GRAYS = (255, 250, 233, 250)   # by QuickDraw row % 4, with SIDEBAR_STRIPES_PHASE
SIDEBAR_STRIPES_PHASE = 2             # measured: in phase with the status bar
SIDEBAR_STRIPES_STUBS = ['_GetPort', '_GetPortBounds', '_CGContextSetRGBFillColor', '_CGContextFillRect']


def build_sidebar_stripes(addr, ret1, table, stubs, phase=SIDEBAR_STRIPES_PHASE):
    """At addr (the fake background control's draw, sub_1af134: a metal
    leftover that draws nothing in an Aqua window): `b ret1` (an existing
    `li r3,1 ; blr`, so that draw does nothing), then SidebarStripes:

        SidebarStripes(r3 = ctx, r4 = CGRect *r)
          row = *r with h = 1; end = r->y + r->h
          q = bottom - 2 * top - 1 - (int) r->y + phase   (GetPortBounds(GetPort()))
          while row.y < end: fill row with table[q & 3]; row.y += 1; q -= 1

    The CG space of the QDBeginCGContext bracket is y-up from the port's
    bottom, and the port's bounds carry the sidebar's scroll origin: bottom
    - 2 top is the window row of CG y 0 at any scroll position (bottom - top
    missed the scroll; bottom alone was right for even scroll offsets only).
    table: 4 grays (STRIPE_GRAYS / 255) then 1.0, as floats.
    Returns (bytes, SidebarStripes' address)."""
    a = Asm(addr)
    a.b(ret1)
    a.label('entry')
    a.mflr(0)
    a.emit((47 << 26) | (28 << 21) | (1 << 16) | (-16 & 0xffff))     # stmw r28,-16(r1)
    a.stw(0, 8, 1)
    a.stwu(1, -0x80, 1)
    a.mr(28, 3)                          # r28 = ctx
    a.lswi(5, 4, 16)                     # the row rect at 0x40 = *r ...
    a.addi(29, 1, 0x40)
    a.stswi(5, 29, 16)
    a.lfs(0, 0x44, 1)                    # end = y + h, at 0x50
    a.lfs(13, 0x4c, 1)
    a.fadds(0, 0, 13)
    a.stfs(0, 0x50, 1)
    a.lis(31, (table + 0x8000) >> 16)    # r31 = the gray table, then 1.0
    a.addi(31, 31, table & 0xffff)
    a.lfs(0, 16, 31)                     # ... 1 row high
    a.stfs(0, 0x4c, 1)
    a.addi(3, 1, 0x58)                   # GetPortBounds(GetPort()) -> 0x5c
    a.bl(stubs['_GetPort'])
    a.lwz(3, 0x58, 1)
    a.addi(4, 1, 0x5c)
    a.bl(stubs['_GetPortBounds'])
    a.lha(30, 0x60, 1)                   # bottom
    a.lha(0, 0x5c, 1)                    # - 2 * top
    a.subf(30, 0, 30)
    a.subf(30, 0, 30)
    a.lfs(0, 0x44, 1)                    # - (int) y
    a.emit((63 << 26) | (0 << 21) | (0 << 11) | (15 << 1))           # fctiwz f0,f0
    a.emit(d_form(54, 0, 1, 0x68))                                    # stfd f0,0x68(r1)
    a.lwz(0, 0x6c, 1)
    a.subf(30, 0, 30)
    a.addi(30, 30, phase - 1)
    a.label('row')
    a.lfs(0, 0x44, 1)
    a.lfs(13, 0x50, 1)
    a.fcmpu(0, 13)
    a.bge('done')
    a.emit((21 << 26) | (30 << 21) | (0 << 16) | (2 << 11) | (28 << 6) | (29 << 1))  # rlwinm r0,r30,2,28,29
    a.emit((31 << 26) | (1 << 21) | (31 << 16) | (0 << 11) | (535 << 1))           # lfsx f1,r31,r0
    a.fmr(2, 1)
    a.fmr(3, 1)
    a.lfs(4, 16, 31)                     # alpha 1
    a.mr(3, 28)
    a.bl(stubs['_CGContextSetRGBFillColor'])
    a.mr(3, 28)
    a.lswi(4, 29, 16)
    a.bl(stubs['_CGContextFillRect'])
    a.addi(30, 30, -1)                   # the next row up is one QuickDraw row higher
    a.lfs(0, 0x44, 1)
    a.lfs(13, 16, 31)
    a.fadds(0, 0, 13)
    a.stfs(0, 0x44, 1)
    a.b('row')
    a.label('done')
    a.lwz(0, 0x88, 1)
    a.addi(1, 1, 0x80)
    a.mtlr(0)
    a.emit((46 << 26) | (28 << 21) | (1 << 16) | (-16 & 0xffff))     # lmw r28,-16(r1)
    a.blr()
    return a.assemble(), a.labels['entry']


def build_stripes_call(addr, end, ctx, rect, entry, copy_to=None, copy_reg=None, table=None, setup=()):
    """A fill site (SetRGBFillColor + FillRect of the view's back color)
    becomes SidebarStripes(ctx, rect): mr r3,ctx ; mr r4,rect ; bl entry ;
    then, as the original left it, the rect copied into the copy register
    (setup: words to emit after the call, e.g. that register's addi);
    b end; optionally the gray table (table: bytes) right after it.
    Padded with nops to end. Returns (bytes, the table's address or None)."""
    a = Asm(addr)
    a.mr(3, ctx)
    a.mr(4, rect)
    a.bl(entry)
    for w in setup:
        a.emit(w)
    if copy_reg is not None:
        a.lswi(5, rect, 16)
        a.stswi(5, copy_reg, 16)
    a.b(end)
    where = None
    if table is not None:
        where = a.pc
        a.data(table)
    code = a.assemble()
    assert len(code) <= end - addr, 'stripes call at %x does not fit' % addr
    return code + struct.pack('>I', 0x60000000) * ((end - addr - len(code)) // 4), where


def build_refresh_thunk(addr, refresh_slot):
    """TSidebarView's ScrollBits (patch.py 'stripes'): this->Refresh(), as a
    tail call. PowerPlant's ScrollImageBy copied the sidebar's pixels and
    redrew only the exposed strip, so the copied stripes moved with the items
    (a row is 18 or 34 px: 2 rows out of phase); now the sidebar redraws."""
    a = Asm(addr)
    a.lwz(12, 0, 3)
    a.lwz(12, refresh_slot, 12)
    a.emit(0x7d8903a6)                   # mtctr r12
    a.emit(0x4e800420)                   # bctr
    return a.assemble()


def build_centered_draw(addr, end):
    """The divider draw's x centering (a no-op with 'stripes': the image is as
    wide as the frame), from lfs f12... to before the clip's lswi, becomes:

        r28 = r1 + 0x90 = a copy of the divider rect (r29 = 0x70): the clip
        image y = y + round(h/2) - image height/2      (f0 = 0.5, f9 = the
            image height, f31 = 2^52: + f31 - f31 rounds a double >= 0 to an
            integer, so an odd height doesn't put the icon on a half pixel;
            y keeps its own fraction, x.5 for odd port heights)

    so the image's middle rows (the arrow, grip.py) sit at the divider's
    middle. The clip's lswi must then read r28 (patch.py)."""
    a = Asm(addr)
    a.addi(28, 1, 0x90)
    a.lswi(5, 29, 16)
    a.stswi(5, 28, 16)
    a.lwz(3, 0x44, 1)                    # ctx
    a.lfs(12, 0x7c, 1)                   # h
    a.fmuls(13, 12, 0)                   # h/2
    a.emit((63 << 26) | (13 << 21) | (13 << 16) | (31 << 11) | (21 << 1))   # fadd f13,f13,f31
    a.emit((63 << 26) | (13 << 21) | (13 << 16) | (31 << 11) | (20 << 1))   # fsub f13,f13,f31
    a.fmuls(11, 9, 0)                    # image height / 2
    a.fsubs(13, 13, 11)
    a.lfs(11, 0x74, 1)                   # + y
    a.fadds(13, 13, 11)
    a.stfs(13, 0x74, 1)
    code = a.assemble()
    assert len(code) <= end - addr
    return code + struct.pack('>I', 0x60000000) * ((end - addr - len(code)) // 4)


# --- 'header' (patch.py): the sidebar's Aqua list header (Panther 10.3.9).
#
# The splitter's DrawSelf (TSidebarSplitter, inside its QDBeginCGContext
# bracket, ctx at 0x44 of its frame) outlined both panes after the divider;
# 'gap' made those calls nops. With 'header' the first (skipped when the
# sidebar is collapsed) calls SidebarHeader instead: the header image
# (tools/header.py, 'PNG ' 8802) over the 17 rows above the sidebar, which
# the layout moved down by as much (patch.py HEADER_*), from the splitter's
# left edge to the divider's line, the divider's last column.
SIDEBAR_HEADER_STUBS = ['_GetPort', '_GetWindowFromPort', '_IsWindowHilited', '_GetResource',
                        '_CGContextResetClip', '_CGContextClipToRect', '_CGContextDrawImage',
                        '_CGContextSetGrayFillColor', '_CGContextFillRect']
DIVIDER_LEFT = 0xd6            # TSidebarSplitter: the divider rect's left (local)
SPLITTER_COLLAPSED = 0xc8      # TSidebarSplitter: nonzero while the sidebar is collapsed
# The top edge of the 'header' and 'well' styles: the status bar's last row,
# painted by the splitter (the bar leaves it, build_topbar keep_last_row),
# a 1 px line over the files (the file pane starts a row higher, so its own
# first row, the list header's line or the icon view's white, is hidden
# under it) and the sidebar: the header's first row, or the well's frame.
EDGE_HEADER = 158              # the list header's top line (its texture's commonest gray)


def build_sidebar_header(head, tail, rest, statics, loader, frame_fn, cgrect_port, stubs, rsrc_id, rows, width,
                         edge=EDGE_HEADER):
    """SidebarHeader(r3 = splitter, r4 = ctx), in three pieces (head, tail,
    rest: dead stretches of code, each branching to the next):

        k = IsWindowHilited(GetWindowFromPort(GetPort())) ? 0 : 1
        holder = statics + 8 k; if !holder.image:
            h = GetResource('PNG ', rsrc_id + k); if h: loader(holder, h)
        frame_fn(&r, splitter)              divider frame, port coordinates
        line = {r.top - 1, r.left, r.top, r.left + 4096}     the top edge
        hdr  = {r.top - 1, r.left - divider's local left, r.top + rows - 1, r.right - 1}
        reset the clip; fill line in `edge` gray (the files' top edge, the
        status bar's last row: the bar leaves it to us, cave.build_topbar)
        unless collapsed: clip to hdr; draw the image at {hdr.x, hdr.y, width, rows}

    The header's first row (its top line) is the bar's last row too, in
    line with the file list's header, whose own first row the bar hides.
    Image rsrc_id is the header of an active window, rsrc_id + 1 that of an
    inactive one (its label gray, as the file list's). The divider's draw
    left the context clipped to the divider, hence the reset (the window's
    backing store is its own: nothing outside it can be drawn over); the
    clip needs no undoing, the bracket ends after the pane outline calls.
    statics: 16 zero bytes of the data segment's zero-fill tail, the
    loader's two holders (image, data provider): each image is loaded once,
    as the divider's grip is. Returns (head, tail, rest) bytes."""
    r0, r1, r3, r4, r5, r8, r9, r10, r11, r28, r29, r30, r31 = 0, 1, 3, 4, 5, 8, 9, 10, 11, 28, 29, 30, 31
    def flt(v): return struct.unpack('>I', struct.pack('>f', v))[0]
    assert flt(width) & 0xffff == 0
    c = Asm(rest)                         # unless collapsed: the image; the epilogue
    c.lwz(r0, SPLITTER_COLLAPSED, r31)
    c.cmpwi(r0, 0)
    c.bne('done')
    c.mr(r3, r30)
    c.addi(r9, r1, 0x50)
    c.lswi(r4, r9, 16)
    c.bl(stubs['_CGContextClipToRect'])
    c.lis(r0, flt(width) >> 16)           # the image's own width (its height: hdr's, rows)
    c.stw(r0, 0x58, r1)
    c.mr(r3, r30)
    c.addi(r9, r1, 0x50)
    c.lswi(r4, r9, 16)
    c.lwz(r8, 0, r29)
    c.bl(stubs['_CGContextDrawImage'])
    c.label('done')
    c.lwz(r0, 0x88, r1)
    c.addi(r1, r1, 0x80)
    c.mtlr(r0)
    _lmw(c, 28, -16, r1)
    c.blr()
    rest_code, done = c.assemble(), c.labels['done']
    b = Asm(tail)
    b.addi(r3, r1, 0x40)                  # r: {top, left, bottom, right} at 0x40
    b.mr(r4, r31)
    b.bl(frame_fn)
    b.lha(r10, 0x40, r1)                  # line at 0x48
    b.addi(r11, r10, -1)
    b.sth(r11, 0x48, r1)
    b.sth(r10, 0x4c, r1)
    b.lha(r10, 0x42, r1)
    b.sth(r10, 0x4a, r1)
    b.addi(r10, r10, 4096)
    b.sth(r10, 0x4e, r1)
    b.lha(r10, 0x46, r1)                  # hdr at 0x40: right before the divider's line
    b.addi(r10, r10, -1)
    b.sth(r10, 0x46, r1)
    b.lha(r10, 0x40, r1)                  # rows from the bar's last row
    b.addi(r11, r10, rows - 1)
    b.sth(r11, 0x44, r1)
    b.addi(r10, r10, -1)
    b.sth(r10, 0x40, r1)
    b.lha(r10, 0x42, r1)                  # left: the splitter's (the sidebar's) edge
    b.lha(r9, DIVIDER_LEFT, r31)
    b.subf(r10, r9, r10)
    b.sth(r10, 0x42, r1)
    b.addi(r3, r1, 0x60)                  # line -> CG at 0x60, hdr -> 0x50
    b.mr(r4, r31)
    b.addi(r5, r1, 0x48)
    b.bl(cgrect_port)
    b.addi(r3, r1, 0x50)
    b.mr(r4, r31)
    b.addi(r5, r1, 0x40)
    b.bl(cgrect_port)
    b.mr(r3, r30)
    b.bl(stubs['_CGContextResetClip'])
    consts = 0                            # patched below: the tail's own constants
    b.mr(r3, r30)
    b.lis(r9, 0); fix = len(b.words) - 1
    b.lfs(1, 0, r9); b.lfs(2, 0, r9)
    b.bl(stubs['_CGContextSetGrayFillColor'])
    b.mr(r3, r30)
    b.addi(r9, r1, 0x60)
    b.lswi(r4, r9, 16)
    b.bl(stubs['_CGContextFillRect'])
    b.b(rest)
    consts = b.pc
    b.data(struct.pack('>2f', edge / 255.0, 1.0))
    b.words[fix] = d_form(15, r9, 0, (consts + 0x8000) >> 16)
    b.words[fix + 1] = d_form(48, 1, r9, consts & 0xffff)
    b.words[fix + 2] = d_form(48, 2, r9, (consts + 4) & 0xffff)
    tail_code = b.assemble()
    a = Asm(head)
    a.mflr(r0)
    _stmw(a, 28, -16, r1)
    a.stw(r0, 8, r1)
    a.stwu(r1, -0x80, r1)
    a.mr(r31, r3)                         # splitter
    a.mr(r30, r4)                         # ctx
    a.addi(r3, r1, 0x60)                  # the window: hilited (active) or not
    a.bl(stubs['_GetPort'])
    a.lwz(r3, 0x60, r1)
    a.bl(stubs['_GetWindowFromPort'])
    a.bl(stubs['_IsWindowHilited'])
    _rlwinm(a, r3, r3, 0, 24, 31)         # Boolean
    a.lis(r29, (statics + 0x8000) >> 16)
    a.addi(r29, r29, statics & 0xffff)
    a.li(r28, rsrc_id)
    a.cmpwi(r3, 0)
    a.bne('picked')
    a.addi(r29, r29, 8)                   # inactive: the second holder, the next id
    a.li(r28, rsrc_id + 1)
    a.label('picked')
    a.lwz(r0, 0, r29)
    a.cmpwi(r0, 0)
    a.bne('go')
    a.lis(r3, 0x504e)                     # 'PNG '
    a.emit(d_form(24, r3, r3, 0x4720))    # ori r3,r3,0x4720
    a.mr(r4, r28)
    a.bl(stubs['_GetResource'])
    a.cmpwi(r3, 0)
    a.beq('go')                           # (no image: the line all the same; the draw skips a null image)
    a.mr(r4, r3)
    a.mr(r3, r29)
    a.bl(loader)
    a.label('go')                         # (tail is too far for a bc)
    a.b(tail)
    return a.assemble(), tail_code, rest_code


# --- 'well' (patch.py): the sidebar as a white inset list on the window's
# pinstripes, framed like an Aqua list box (Panther 10.3.9). The layout puts
# the sidebar WELL_MARGIN px in from the splitter's left, top and bottom
# edges and from the divider, which is WELL_MARGIN px of stripes ending in a
# 1 px line. In the splitter's DrawSelf, DividerErase erases the whole strip
# left of the files (the sidebar's margins and the divider) with the toolbar
# brush: the pinstripes, in phase with the status bar's, which the sidebar
# then paints over in white (build_divider_outset_well); then WellFrame
# (build_well_frame) draws the list box's frame, 1 px around the sidebar, in
# the bracket's place of the pane outlines.
WELL_TOP = 142                 # an Aqua list box's frame (NSScrollView's bezel, measured on 10.3.9)
WELL_SIDES = 190
WELL_BAR_STRIPE = 250          # the status bar's last row, in its pinstripes (port row 19)
WELL_FRAME_STUBS = ['_CGContextResetClip', '_CGContextSetGrayFillColor', '_CGContextFillRect']


def build_divider_outset_well(addr, back, stubs, drawself_ret):
    """DividerOutset for 'well' (the tail of DividerErase, on its frame: r at
    0x40, its return address at 0x68, r31 the splitter): called from the
    splitter's DrawSelf (returning to drawself_ret), r.left goes to the
    splitter's left edge (the divider's local left back): the whole strip
    is erased; from the splitter repaint while dragging, the divider only
    (the sidebar isn't redrawn then). Then EraseRect(&r), back."""
    a = Asm(addr)
    r0, r1, r3, r4, r5, r31 = 0, 1, 3, 4, 5, 31
    a.lwz(r0, 0x68, r1)
    a.lis(r4, drawself_ret >> 16)
    a.emit(d_form(24, r4, r4, drawself_ret & 0xffff))   # ori
    a.cmpw(r0, r4)
    a.bne('erase')
    a.lha(r4, 0x42, r1)
    a.lha(r5, DIVIDER_LEFT, r31)
    a.subf(r4, r5, r4)
    a.sth(r4, 0x42, r1)
    a.label('erase')
    a.addi(r3, r1, 0x40)
    a.bl(stubs['_EraseRect'])
    a.b(back)
    return a.assemble()


def build_well_frame(head, tail, rest, frame_fn, cgrect_port, stubs, margin, top=WELL_TOP, sides=WELL_SIDES):
    """WellFrame(r3 = splitter, r4 = ctx), in three pieces (head, tail, rest,
    each branching to the next; rest ends in the constants):

        frame_fn(&r, splitter)                    divider frame, port coordinates
        o = {r.top - 1, r.left - divider's local left + margin - 1,
             r.bottom - margin + 1, r.left}       1 px around the sidebar, the
                                                  bar's last row for its top
        cgrect_port(&c, splitter, &o); reset the clip (the divider's draw
        left it on the divider)
        the top row (the status bar's last, cave.EDGE_*), on to the window's
        right: the bar's pinstripe gray, then from the divider's line on the
        files' top edge in `top` gray
        unless collapsed: c's left and right columns and bottom row in
        `sides` gray (the sidebar has drawn itself), c's top row in `top`
        gray (over the sidebar only: the divider's pinstripes run up into
        the bar beside it)
    Fills go through a helper, fill(f1 = gray, r28 = the rect). Returns
    (head, tail, rest) bytes."""
    r0, r1, r3, r4, r5, r9, r10, r28, r29, r30, r31 = 0, 1, 3, 4, 5, 9, 10, 28, 29, 30, 31
    ONE, WIDE, SIDES, TOP, STRIPE, MM1 = 0, 4, 8, 12, 16, 20
    k = struct.pack('>6f', 1.0, 4096.0, sides / 255.0, top / 255.0, WELL_BAR_STRIPE / 255.0, float(margin - 1))
    # c at 0x50 {x, y, w, h}; the top row's rect at 0x60; the frame's sides at 0x40
    c = Asm(rest)                         # the sidebar's top line, the epilogue, the constants
    c.lfs(0, 0x50, r1); c.stfs(0, 0x60, r1)
    c.lfs(0, 0x58, r1); c.stfs(0, 0x68, r1)
    c.addi(r28, r1, 0x60)
    c.lfs(1, TOP, r29)
    c.bl(tail)                            # (fill: the tail's first routine)
    c.label('done')
    c.lwz(r0, 0x98, r1)
    c.addi(r1, r1, 0x90)
    c.mtlr(r0)
    _lmw(c, 28, -16, r1)
    c.blr()
    consts = c.pc
    c.data(k)
    done = c.labels['done']
    b = Asm(tail)
    b.label('fill')                       # fill(f1 gray, r28 rect): on our frame (0x90: saved
                                          # r28..r31 at 0x80..0x8f), LR at 0x7c
    b.mflr(r0)
    b.stw(r0, 0x7c, r1)
    b.mr(r3, r30)
    b.lfs(2, ONE, r29)
    b.bl(stubs['_CGContextSetGrayFillColor'])
    b.mr(r3, r30)
    b.lswi(r4, r28, 16)
    b.bl(stubs['_CGContextFillRect'])
    b.lwz(r0, 0x7c, r1)
    b.mtlr(r0)
    b.blr()
    b.label('entry')
    b.addi(r28, r1, 0x60)                 # the top row: {0, y + h - 1, 4096, 1}
    b.li(r0, 0); b.stw(r0, 0x60, r1)
    b.lfs(0, WIDE, r29); b.stfs(0, 0x68, r1)
    b.lfs(1, STRIPE, r29)
    b.bl('fill')                          # pinstripe gray
    b.lfs(0, 0x50, r1); b.lfs(13, 0x58, r1); b.fadds(0, 0, 13)   # from the divider's line: x + w + m - 1
    b.lfs(13, MM1, r29); b.fadds(0, 0, 13); b.stfs(0, 0x60, r1)
    b.lfs(1, TOP, r29)
    b.bl('fill')                          # the files' top edge
    b.lwz(r0, SPLITTER_COLLAPSED, r31)
    b.cmpwi(r0, 0)
    b.bne('out')
    b.addi(r9, r1, 0x50)                  # the frame's sides: a copy of c at 0x40
    b.lswi(r4, r9, 16)
    b.addi(r28, r1, 0x40)
    b.stswi(r4, r28, 16)
    b.lfs(0, ONE, r29); b.stfs(0, 0x48, r1)
    b.lfs(1, SIDES, r29)
    b.bl('fill')                          # left {x, y, 1, h}
    b.lfs(0, 0x50, r1); b.lfs(13, 0x58, r1); b.fadds(0, 0, 13); b.lfs(13, ONE, r29); b.fsubs(0, 0, 13)
    b.stfs(0, 0x40, r1)
    b.lfs(1, SIDES, r29)
    b.bl('fill')                          # right {x + w - 1, y, 1, h}
    b.lfs(0, 0x50, r1); b.stfs(0, 0x40, r1)
    b.lfs(0, 0x58, r1); b.stfs(0, 0x48, r1)
    b.lfs(0, ONE, r29); b.stfs(0, 0x4c, r1)
    b.lfs(1, SIDES, r29)
    b.bl('fill')                          # bottom {x, y, w, 1}
    b.b(rest)
    b.label('out')
    b.b(done)
    tail_code, entry = b.assemble(), b.labels['entry']
    assert c.labels.get('done') and tail == b.labels['fill']
    a = Asm(head)
    a.mflr(r0)
    _stmw(a, 28, -16, r1)
    a.stw(r0, 8, r1)
    a.stwu(r1, -0x90, r1)
    a.mr(r31, r3)                         # splitter
    a.mr(r30, r4)                         # ctx
    a.addi(r3, r1, 0x40)
    a.mr(r4, r31)
    a.bl(frame_fn)
    a.lha(r10, 0x40, r1)                  # top: the bar's last row
    a.addi(r10, r10, -1)
    a.sth(r10, 0x40, r1)
    a.lha(r10, 0x42, r1)                  # right: the divider's left
    a.sth(r10, 0x46, r1)
    a.lha(r9, DIVIDER_LEFT, r31)          # left: the splitter's edge + margin - 1
    a.subf(r10, r9, r10)
    a.addi(r10, r10, margin - 1)
    a.sth(r10, 0x42, r1)
    a.lha(r10, 0x44, r1)                  # bottom - margin + 1
    a.addi(r10, r10, 1 - margin)
    a.sth(r10, 0x44, r1)
    a.addi(r3, r1, 0x50)
    a.mr(r4, r31)
    a.addi(r5, r1, 0x40)
    a.bl(cgrect_port)
    a.mr(r3, r30)
    a.bl(stubs['_CGContextResetClip'])
    a.lis(r29, (consts + 0x8000) >> 16)
    a.addi(r29, r29, consts & 0xffff)     # r29 = the constants
    a.lfs(0, 0x54, r1); a.lfs(13, 0x5c, r1); a.fadds(0, 0, 13)   # the top row: y + h - 1, 1 high
    a.lfs(13, ONE, r29); a.fsubs(0, 0, 13)
    a.stfs(0, 0x64, r1); a.stfs(13, 0x6c, r1)
    a.b(entry)
    return a.assemble(), tail_code, c.assemble()


# --- 'stripes' on Tiger 10.4.11 (patch.py TIGER_STRIPES_PATCHES).
#
# The sidebar view's draw (sub_79c40) fills the dirty part of its bounds with
# its back color, white, in sub_3f6e4 (only the sidebar calls it), then draws
# the items over it. That CGContextFillRect goes to SideFill instead, which
# stripes the rect. Stripes are 1 px rows in STRIPE_GRAYS by window row
# (HIViewConvertPoint to the window's root view), so they keep their place
# whatever the view and its scroll position, in phase with the status bar's
# (cave.build_tiger_bar, PINSTRIPES from its top row).
#
# The splitter's divider (7 px, the stock width) is drawn as Panther's
# (grip.py STRIPES_*): the splitter's left part (the sidebar's margins and the
# divider) striped, a soft shadow falling left from a 163 line by the files,
# and the small arrow at the divider's middle height.
TIGER_STRIPES_STUBS = ['_HIViewConvertPoint', '_CGContextSetRGBFillColor', '_CGContextFillRect']
TIGER_STRIPES_PHASE = 0               # measured: in phase with the status bar


def _fctiwz(a, ft, fb): a.emit((63 << 26) | (ft << 21) | (fb << 11) | (15 << 1))
def _stfd(a, fs, d, ra): a.emit(d_form(54, fs, ra, d))
def _rlwinm(a, ra, rs, sh, mb, me): a.emit((21 << 26) | (rs << 21) | (ra << 16) | (sh << 11) | (mb << 6) | (me << 1))
def _lfsx(a, ft, ra, rb): a.emit((31 << 26) | (ft << 21) | (ra << 16) | (rb << 11) | (535 << 1))
def _stmw(a, rs, d, ra): a.emit(d_form(47, rs, ra, d))
def _lmw(a, rt, d, ra): a.emit(d_form(46, rt, ra, d))


TIGER_HIVIEW = 0x48                   # a Finder view object's HIViewRef (see sub_13d48)
TIGER_SIDEBAR_VTABLE = 0x3a81d8       # the sidebar view's vtable (its Draw, slot 0xe4: sub_3f6e4)
TIGER_SCROLL_OPAQUE = 0x2e50c         # sub_2e50c(obj): the view's opaque feature bit


def build_tiger_stripes(cave, stubs, phase=TIGER_STRIPES_PHASE, vtable=TIGER_SIDEBAR_VTABLE, only_stripes=False):
    """cave: where the routines go (constants first). Entry points:
      stripes(ctx r3, CGRect *r4, view r5): r4's rows striped (view coords;
        r5 a Finder view object, its HIViewRef at TIGER_HIVIEW)
      sidefill(ctx r3, rect r4..r7 by value): stands in for sub_3f6e4's
        CGContextFillRect; the view is the caller's r28
      itemfill: the same for sub_16de60's (an item, while one is dragged),
        the view in r30
      divider(view r3, ctx r4): stands in for the splitter Draw's call of
        sub_3f304 (see build_tiger_divider)
    only_stripes: the stripes routine alone (and the constants it reads).
    Returns (bytes, {'sidefill': addr, 'divider': addr, ...}) or, only_stripes,
    (bytes, {'stripes_fn': addr})."""
    import grip
    W = grip.STRIPES_WIDTH
    cols = [(float(W - 1), grip.STRIPES_LINE / 255.0, 1.0)]
    cols += [(float(W - 2 - i), 0.0, a) for i, a in enumerate(grip.STRIPES_SHADOW)]
    pix = []
    for dy, row in enumerate(grip.STRIPES_ARROW):
        for dx, p in enumerate(row):
            if p:
                pix.append((float(dx), float(dy), p[0] / 255.0, p[1] / 255.0 if p[1] > 1 else p[1]))
    half = len(grip.STRIPES_ARROW) // 2
    consts = struct.pack('>4f', *[g / 255.0 for g in STRIPE_GRAYS])          # 0  TAB
    consts += struct.pack('>4f', 1.0, 4096.0 + phase, 8388608.0, 0.5)      # 16 ONE BIAS BIG HALF
    consts += struct.pack('>2f', 0.0, float(half))                          # 32 ZERO HALFA
    COLS = len(consts)
    if only_stripes:
        cols, pix = [], []
    for c in cols:
        consts += struct.pack('>3f', *c)
    PIX = len(consts)
    for p in pix:
        consts += struct.pack('>4f', *p)
    END = len(consts)
    TAB, ONE, BIAS, BIG, HALF, ZERO, HALFA = 0, 16, 20, 24, 28, 32, 36
    a = Asm(cave)
    a.data(consts)
    hi, lo = (cave + 0x8000) >> 16, cave & 0xffff
    K = 31                                  # r31 = constants, in every routine

    def prologue(size):
        a.mflr(0)
        _stmw(a, 26, -24, 1)
        a.stw(0, 8, 1)
        a.stwu(1, -size, 1)
        a.lis(K, hi)
        a.addi(K, K, lo)

    def epilogue(size):
        a.lwz(0, size + 8, 1)
        a.addi(1, 1, size)
        a.mtlr(0)
        _lmw(a, 26, -24, 1)
        a.blr()

    def fill(ctx, rect_off, gray_reg_off=None):
        pass

    # stripes(ctx, rect*, view); frame 0x80: 0x40 row {x,y,w,h}, 0x50 end,
    # 0x58 point, 0x60 fctiwz; 0x68.. the saved r26..r31
    a.label('stripes')
    prologue(0x80)
    a.mr(28, 3)
    a.lswi(6, 4, 16)                        # (r4 is the base: load into r6..r9)
    a.addi(29, 1, 0x40)
    a.stswi(6, 29, 16)
    a.lfs(0, 0x44, 1); a.lfs(13, 0x4c, 1); a.fadds(0, 0, 13); a.stfs(0, 0x50, 1)
    a.lfs(0, ONE, K); a.stfs(0, 0x4c, 1)    # rows 1 high
    a.lfs(0, ZERO, K); a.stfs(0, 0x58, 1); a.stfs(0, 0x5c, 1)
    a.addi(3, 1, 0x58)
    a.lwz(4, TIGER_HIVIEW, 5)               # the object's HIViewRef
    a.li(5, 0)
    a.bl(stubs['_HIViewConvertPoint'])      # (0, 0) in the window's root view
    a.lfs(0, 0x44, 1); a.lfs(13, 0x5c, 1); a.fadds(0, 0, 13)
    a.lfs(13, BIAS, K); a.fadds(0, 0, 13)
    _fctiwz(a, 0, 0)
    _stfd(a, 0, 0x60, 1)
    a.lwz(30, 0x64, 1)                      # r30 = window row + bias
    a.label('row')
    a.lfs(0, 0x44, 1); a.lfs(13, 0x50, 1); a.fcmpu(0, 13)
    a.bge('sdone')
    _rlwinm(a, 0, 30, 2, 28, 29)            # (row & 3) * 4
    _lfsx(a, 1, K, 0)
    a.fmr(2, 1); a.fmr(3, 1); a.lfs(4, ONE, K)
    a.mr(3, 28)
    a.bl(stubs['_CGContextSetRGBFillColor'])
    a.mr(3, 28)
    a.lswi(4, 29, 16)
    a.bl(stubs['_CGContextFillRect'])
    a.addi(30, 30, 1)
    a.lfs(0, 0x44, 1); a.lfs(13, ONE, K); a.fadds(0, 0, 13); a.stfs(0, 0x44, 1)
    a.b('row')
    a.label('sdone')
    epilogue(0x80)
    if only_stripes:
        return a.assemble(), {'stripes_fn': a.labels['stripes']}

    # sidefill(ctx r3, rect r4..r7), view = the caller's r28 (sub_3f6e4,
    # the sidebar's Draw: its back color fill), and itemfill, view = r30
    # (sub_16de60: an item's back color fill, while an item is dragged):
    # the sidebar's only (sub_3f6e4 is also the column view's columns' Draw)
    for label, view in (('sidefill', 28), ('itemfill', 30)):
        a.label(label)
        a.lwz(0, 0, view)
        a.lis(12, (vtable + 0x8000) >> 16)
        a.addi(12, 12, vtable & 0xffff)
        a.cmpw(0, 12)
        a.beq(label + '_mine')
        a.b(stubs['_CGContextFillRect'])
        a.label(label + '_mine')
        a.mflr(0)
        a.stw(0, 8, 1)
        a.stwu(1, -0x60, 1)
        a.addi(9, 1, 0x40)
        a.stswi(4, 9, 16)
        a.mr(4, 9)
        a.mr(5, view)
        a.bl('stripes')
        a.lwz(0, 0x68, 1)
        a.addi(1, 1, 0x60)
        a.mtlr(0)
        a.blr()

    # divider(view r3, ctx r4); frame 0xa0: 0x40 divider rect, 0x50 fill rect, 0x60 arrow top
    a.label('divider')
    prologue(0xa0)
    a.mr(27, 3)                             # view
    a.mr(28, 4)                             # ctx
    a.bl(TIGER_BAR_FILL)                    # the splitter's own background
    a.addi(9, 27, TIGER_DIVIDER_RECT)
    a.lswi(4, 9, 16)
    a.addi(29, 1, 0x40)
    a.stswi(4, 29, 16)
    # the left part, striped: {0, y, x + w, h}
    a.lfs(0, ZERO, K); a.stfs(0, 0x50, 1)
    a.lfs(0, 0x44, 1); a.stfs(0, 0x54, 1)
    a.lfs(0, 0x40, 1); a.lfs(13, 0x48, 1); a.fadds(0, 0, 13); a.stfs(0, 0x58, 1)
    a.lfs(0, 0x4c, 1); a.stfs(0, 0x5c, 1)
    a.mr(3, 28)
    a.addi(4, 1, 0x50)
    a.mr(5, 27)
    a.bl('stripes')
    # columns: {x + dx, y, 1, h} in (gray, alpha)
    a.lfs(0, ONE, K); a.stfs(0, 0x58, 1)
    a.addi(26, K, COLS)
    a.label('col')
    a.lfs(0, 0x40, 1); a.lfs(13, 0, 26); a.fadds(0, 0, 13); a.stfs(0, 0x50, 1)
    a.lfs(1, 4, 26); a.fmr(2, 1); a.fmr(3, 1); a.lfs(4, 8, 26)
    a.mr(3, 28)
    a.bl(stubs['_CGContextSetRGBFillColor'])
    a.mr(3, 28)
    a.addi(9, 1, 0x50)
    a.lswi(4, 9, 16)
    a.bl(stubs['_CGContextFillRect'])
    a.addi(26, 26, 12)
    a.addi(9, K, PIX)
    a.cmpw(26, 9)
    a.bne('col')
    # the arrow: top = y + round(h/2) - half; pixels {x + dx, top + dy, 1, 1}
    a.lfs(0, 0x4c, 1); a.lfs(13, HALF, K); a.fmuls(0, 0, 13)
    a.lfs(13, BIG, K); a.fadds(0, 0, 13); a.fsubs(0, 0, 13)
    a.lfs(13, 0x44, 1); a.fadds(0, 0, 13)
    a.lfs(13, HALFA, K); a.fsubs(0, 0, 13)
    a.stfs(0, 0x60, 1)
    a.lfs(0, ONE, K); a.stfs(0, 0x5c, 1)
    a.label('pix')
    a.lfs(0, 0x40, 1); a.lfs(13, 0, 26); a.fadds(0, 0, 13); a.stfs(0, 0x50, 1)
    a.lfs(0, 0x60, 1); a.lfs(13, 4, 26); a.fadds(0, 0, 13); a.stfs(0, 0x54, 1)
    a.lfs(1, 8, 26); a.fmr(2, 1); a.fmr(3, 1); a.lfs(4, 12, 26)
    a.mr(3, 28)
    a.bl(stubs['_CGContextSetRGBFillColor'])
    a.mr(3, 28)
    a.addi(9, 1, 0x50)
    a.lswi(4, 9, 16)
    a.bl(stubs['_CGContextFillRect'])
    a.addi(26, 26, 16)
    a.addi(9, K, END)
    a.cmpw(26, 9)
    a.bne('pix')
    epilogue(0xa0)

    # opaque(obj r3): stands in for the scroll handler's call of sub_2e50c
    # (sub_2e290: may the view scroll by copying its pixels?): never for the
    # sidebar, which then redraws whole, so its stripes stay with the window
    a.label('opaque')
    a.lwz(0, 0, 3)
    a.lis(12, (vtable + 0x8000) >> 16)
    a.addi(12, 12, vtable & 0xffff)
    a.cmpw(0, 12)
    a.beq('op_mine')
    a.b(TIGER_SCROLL_OPAQUE)
    a.label('op_mine')
    a.li(3, 0)
    a.blr()
    code = a.assemble()
    return code, {'sidefill': a.labels['sidefill'], 'itemfill': a.labels['itemfill'], 'sdivider': a.labels['divider'],
                  'sopaque': a.labels['opaque'], 'stripes_fn': a.labels['stripes']}


# --- 'header' on Tiger 10.4.11 (patch.py TIGER_HEADER_PATCHES): the
# sidebar under an Aqua list header. The splitter's sidebar margins are 0
# but the top one, 17 - 1: the header's first row (its top line) is the
# status bar's last, which the bar draws as the top edge (build_tiger_edge),
# so the header shows its rows below that; the file pane's top margin is -1,
# its own first row hidden above the splitter, under that edge, as on
# Panther (cave.EDGE_*); its left one goes. The divider keeps its stock 7 px.
# The splitter's Draw calls build_tiger_header's routine instead of its
# background + DrawDivider: its background (white), the divider's line (its
# last column), and, unless the sidebar is collapsed (the divider at x 0),
# the header image (tools/header.py: 'PNG ' 8802, or 8803 when the splitter
# is inactive) from the splitter's left edge to the line, a row up, clipped
# to the splitter. The image is read from Finder.rsrc at each draw, as
# the toolbar's are. Tiger doesn't redraw the splitter when its window is
# activated or deactivated, so on its first draw each splitter gets a Carbon
# event handler for those (it marks the view for redrawing), and a control
# property ('Aqfn' 'hdr ') saying it has one.
TIGER_HEADER_STUBS = ['_CGContextSetRGBFillColor', '_CGContextFillRect', '_IsControlActive', '_GetResource',
                      '_GetHandleSize', '_CGDataProviderCreateWithData', '_CGImageCreateWithPNGDataProvider',
                      '_CGDataProviderRelease', '_CGContextSaveGState', '_CGContextClipToRect',
                      '_HIViewDrawCGImage', '_CGContextRestoreGState', '_CGImageRelease',
                      '_GetControlProperty', '_SetControlProperty', '_GetControlEventTarget',
                      '_InstallEventHandler', '_HIViewSetNeedsDisplay']


def build_tiger_header(cave, stubs, rsrc_id, rows, width, line=TOPBAR_LINE):
    """cave: where the routine goes (constants first). Entry 'hdivider'
    (view r3, ctx r4) stands in for the splitter Draw's call of sub_3f304.
    Also returns 'hmargin', the address of the float rows - 1 (the sidebar's
    top margin, loaded by the splitter's init), and 'hmone', of -1.0 (the
    file pane's). Returns (bytes, entries)."""
    consts = struct.pack('>6f', 1.0, line / 255.0, float(rows), float(width), 0.0, float(rows - 1))
    consts += struct.pack('>4I', _ostype('cntl'), 9, _ostype('cntl'), 10)    # kEventControlActivate, Deactivate
    consts += struct.pack('>f', -1.0)
    ONE, LINE, ROWS, WIDTH, ZERO, MARGIN, SPECS, MONE = 0, 4, 8, 12, 16, 20, 24, 40
    a = Asm(cave)
    a.data(consts)
    hi, lo = (cave + 0x8000) >> 16, cave & 0xffff
    K = 31
    def lis_ori(r, v):
        a.lis(r, v >> 16); a.emit(d_form(24, r, r, v & 0xffff))
    # handler(callRef, event, view): redraw the view; let others see the event
    a.label('hhandler')
    a.mflr(0)
    a.stw(0, 8, 1)
    a.stwu(1, -0x40, 1)
    a.mr(3, 5)
    a.li(4, 1)
    a.bl(stubs['_HIViewSetNeedsDisplay'])
    a.li(3, EVENT_NOT_HANDLED)
    a.lwz(0, 0x48, 1)
    a.addi(1, 1, 0x40)
    a.mtlr(0)
    a.blr()
    handler = a.labels['hhandler']
    a.label('hdivider')
    a.mflr(0)
    _stmw(a, 26, -24, 1)
    a.stw(0, 8, 1)
    a.stwu(1, -0xa0, 1)
    a.lis(K, hi)
    a.addi(K, K, lo)
    a.mr(27, 3)                             # view
    a.mr(28, 4)                             # ctx
    a.lwz(3, TIGER_HIVIEW, 27)              # once per view: the (de)activation handler
    lis_ori(4, _ostype('Aqfn'))
    lis_ori(5, _ostype('hdr '))
    a.li(6, 4)
    a.addi(7, 1, 0x78)
    a.addi(8, 1, 0x7c)
    a.bl(stubs['_GetControlProperty'])
    a.cmpwi(3, 0)
    a.beq('has')
    a.lwz(3, TIGER_HIVIEW, 27)
    a.bl(stubs['_GetControlEventTarget'])
    a.lis(4, (handler + 0x8000) >> 16); a.addi(4, 4, handler & 0xffff)
    a.li(5, 2)
    a.addi(6, K, SPECS)
    a.lwz(7, TIGER_HIVIEW, 27)
    a.li(8, 0)
    a.bl(stubs['_InstallEventHandler'])
    a.li(0, 1)
    a.stw(0, 0x7c, 1)
    a.lwz(3, TIGER_HIVIEW, 27)
    lis_ori(4, _ostype('Aqfn'))
    lis_ori(5, _ostype('hdr '))
    a.li(6, 4)
    a.addi(7, 1, 0x7c)
    a.bl(stubs['_SetControlProperty'])
    a.label('has')
    a.mr(3, 27)
    a.mr(4, 28)
    a.bl(TIGER_BAR_FILL)                    # the splitter's own background
    a.addi(9, 27, TIGER_DIVIDER_RECT)       # divider rect {x, y, w, h} at 0x40
    a.lswi(4, 9, 16)
    a.addi(29, 1, 0x40)
    a.stswi(4, 29, 16)
    # the line: {x + w - 1, y, 1, h}
    a.lfs(0, 0x40, 1); a.lfs(13, 0x48, 1); a.fadds(0, 0, 13); a.lfs(13, ONE, K); a.fsubs(0, 0, 13)
    a.stfs(0, 0x50, 1)                      # (0x50: the line's x, the header's width)
    a.lfs(0, 0x44, 1); a.stfs(0, 0x54, 1)
    a.stfs(13, 0x58, 1)
    a.lfs(0, 0x4c, 1); a.stfs(0, 0x5c, 1)
    a.mr(3, 28)
    a.lfs(1, LINE, K); a.fmr(2, 1); a.fmr(3, 1); a.lfs(4, ONE, K)
    a.bl(stubs['_CGContextSetRGBFillColor'])
    a.mr(3, 28)
    a.addi(9, 1, 0x50)
    a.lswi(4, 9, 16)
    a.bl(stubs['_CGContextFillRect'])
    # collapsed (the divider at the left edge): no header
    a.lfs(0, 0x40, 1); a.lfs(13, ZERO, K); a.fcmpu(0, 13)
    a.ble('done')
    # the header: clip {0, y, x + w - 1, rows - 1}, image a row up {0, y - 1, width, rows}
    a.lfs(0, 0x50, 1); a.stfs(0, 0x68, 1)
    a.lfs(0, ZERO, K); a.stfs(0, 0x60, 1)
    a.lfs(0, 0x44, 1); a.stfs(0, 0x64, 1)
    a.lfs(0, MARGIN, K); a.stfs(0, 0x6c, 1)
    a.lwz(3, TIGER_HIVIEW, 27)
    a.bl(stubs['_IsControlActive'])
    _clrlwi24(a, 3, 3)
    a.li(4, rsrc_id + 1)                    # inactive: the next id
    a.cmpwi(3, 0)
    a.beq('picked')
    a.li(4, rsrc_id)
    a.label('picked')
    a.lis(3, _ostype('PNG ') >> 16); a.emit(d_form(24, 3, 3, _ostype('PNG ') & 0xffff))
    a.bl(stubs['_GetResource'])
    a.cmpwi(3, 0); a.beq('done')
    a.mr(30, 3)
    a.bl(stubs['_GetHandleSize'])
    a.mr(5, 3)
    a.lwz(4, 0, 30)
    a.li(3, 0); a.li(6, 0)
    a.bl(stubs['_CGDataProviderCreateWithData'])
    a.cmpwi(3, 0); a.beq('done')
    a.mr(30, 3)
    a.li(4, 0); a.li(5, 0); a.li(6, 0)
    a.bl(stubs['_CGImageCreateWithPNGDataProvider'])
    a.mr(26, 3)
    a.mr(3, 30)
    a.bl(stubs['_CGDataProviderRelease'])
    a.cmpwi(26, 0); a.beq('done')
    a.mr(3, 28)
    a.bl(stubs['_CGContextSaveGState'])
    a.mr(3, 28)
    a.addi(9, 1, 0x60)
    a.lswi(4, 9, 16)
    a.bl(stubs['_CGContextClipToRect'])
    a.lfs(0, WIDTH, K); a.stfs(0, 0x68, 1)
    a.lfs(0, ROWS, K); a.stfs(0, 0x6c, 1)
    a.lfs(0, 0x64, 1); a.lfs(13, ONE, K); a.fsubs(0, 0, 13); a.stfs(0, 0x64, 1)
    a.mr(3, 28)
    a.addi(4, 1, 0x60)
    a.mr(5, 26)
    a.bl(stubs['_HIViewDrawCGImage'])
    a.mr(3, 28)
    a.bl(stubs['_CGContextRestoreGState'])
    a.mr(3, 26)
    a.bl(stubs['_CGImageRelease'])
    a.label('done')
    a.lwz(0, 0xa8, 1)
    a.addi(1, 1, 0xa0)
    a.mtlr(0)
    _lmw(a, 26, -24, 1)
    a.blr()
    return a.assemble(), {'hdivider': a.labels['hdivider'], 'hmargin': cave + MARGIN, 'hmone': cave + MONE}


# --- 'well' on Tiger 10.4.11 (patch.py TIGER_WELL_PATCHES): the sidebar as
# a white inset list on the window's pinstripes, framed like an Aqua list box,
# as on Panther (build_well_frame). The splitter's sidebar margins are the
# well's margin (left, top, bottom) and 1 (right: the frame's line), the file
# pane has none, and the divider is the margin wide. The splitter's Draw calls
# build_tiger_well's routine instead of its background + DrawDivider: its
# background, the strip left of the files striped (build_tiger_stripes'
# stripes, by window row), the divider's line (its last column) and, unless
# the sidebar is collapsed, the list box's frame 1 px around the sidebar.
TIGER_WELL_STUBS = TIGER_STRIPES_STUBS + ['_HIViewGetWindow', '_SetWindowProperty', '_HIViewConvertRect',
                                         '_HIViewGetRoot', '_HIViewSetNeedsDisplayInRect']
TIGER_OUTLINE_FN = (0x3f448, 0x3f660)  # sub_3f448, a pane's outline: called only from the splitter Draw's two calls 'gap' nops
TIGER_DIVUPDATE_STUBS = ['_RemoveEventLoopTimer', '_GetWindowProperty', '_HIViewSetNeedsDisplay', '_CFRelease',
                         '_HIViewGetWindow', '_SetWindowProperty', '_CFRetain', '_GetMainEventLoop',
                         '_InstallEventLoopTimer']
TIGER_DIVX_SIZE = 8                    # the window's 'Aqfn' 'divx' property: {divider x, its line's x}
                                       # ('Aqfn' 'barv': the status bar's HIView, build_tiger_well_edge)


def build_tiger_divupdate(addr, stubs):
    """For the well's top edge on Tiger (build_tiger_well_edge), in the
    outline routine's dead code (TIGER_OUTLINE_FN):
      divupdate(splitter r3), from the splitter's Draw: the window's 'Aqfn'
        'divx' property = {x, x + w - 1} of its divider rect; then a timer,
        firing right after this draw, marks the window's status bar (its
        'Aqfn' 'barv' property, which the bar's edge routine sets) for
        redrawing: a redraw asked for during a draw is lost. The timer keeps
        the window retained until it fires.
      fired(timer r3, window r4): the timer's proc.
    Returns (bytes, {'divupdate'})."""
    a = Asm(addr)
    a.data(struct.pack('>f', 1.0))
    ONE = addr
    def creator_tag(size, tag='divx'):
        a.lis(4, _ostype('Aqfn') >> 16); a.emit(d_form(24, 4, 4, _ostype('Aqfn') & 0xffff))
        a.lis(5, _ostype(tag) >> 16); a.emit(d_form(24, 5, 5, _ostype(tag) & 0xffff))
        a.li(6, size)
    a.label('fired')                       # fired(timer, window): frame 0x70, r30/r31 at 0x68
    a.mflr(0)
    _stmw(a, 30, -8, 1)
    a.stw(0, 8, 1)
    a.stwu(1, -0x70, 1)
    a.mr(31, 4)
    a.bl(stubs['_RemoveEventLoopTimer'])
    a.mr(3, 31)
    creator_tag(4, 'barv')
    a.li(7, 0)
    a.addi(8, 1, 0x40)
    a.bl(stubs['_GetWindowProperty'])
    a.cmpwi(3, 0)
    a.bne('fdone')
    a.lwz(3, 0x40, 1)
    a.li(4, 1)
    a.bl(stubs['_HIViewSetNeedsDisplay'])
    a.label('fdone')
    a.mr(3, 31)
    a.bl(stubs['_CFRelease'])
    a.b('out')
    a.label('divupdate')
    a.mflr(0)
    _stmw(a, 30, -8, 1)
    a.stw(0, 8, 1)
    a.stwu(1, -0x70, 1)
    a.mr(31, 3)
    a.lis(9, (ONE + 0x8000) >> 16)
    a.lfs(12, ONE & 0xffff, 9)
    a.lfs(0, TIGER_DIVIDER_RECT, 31); a.stfs(0, 0x40, 1)                # {x, x + w - 1}
    a.lfs(13, TIGER_DIVIDER_RECT + 8, 31); a.fadds(13, 0, 13); a.fsubs(13, 13, 12); a.stfs(13, 0x44, 1)
    a.lwz(3, TIGER_HIVIEW, 31)
    a.bl(stubs['_HIViewGetWindow'])
    a.mr(30, 3)
    creator_tag(TIGER_DIVX_SIZE)
    a.addi(7, 1, 0x40)
    a.bl(stubs['_SetWindowProperty'])
    a.mr(3, 30)
    a.bl(stubs['_CFRetain'])
    a.bl(stubs['_GetMainEventLoop'])
    a.lis(9, (ONE + 0x8000) >> 16)
    a.lfs(1, ONE & 0xffff, 9); a.fsubs(1, 1, 1); a.fmr(2, 1)           # delay 0, interval 0 (doubles)
    # (the Darwin PPC ABI: each double also takes two GPRs, r4..r7 here)
    a.lis(8, 0); fix = len(a.words) - 1; a.addi(8, 8, 0)                # the proc: fired
    a.mr(9, 30)                            # its data: the window
    a.addi(10, 1, 0x60)                    # (the timer, unused: its proc gets it)
    a.bl(stubs['_InstallEventLoopTimer'])
    a.label('out')
    a.lwz(0, 0x78, 1)
    a.addi(1, 1, 0x70)
    a.mtlr(0)
    _lmw(a, 30, -8, 1)
    a.blr()
    fired = a.labels['fired']
    a.words[fix] = d_form(15, 8, 0, (fired + 0x8000) >> 16)
    a.words[fix + 1] = d_form(14, 8, 8, fired & 0xffff)
    return a.assemble(), {'divupdate': a.labels['divupdate']}


def build_tiger_well(cave, stubs, margin, divupdate, line=TOPBAR_LINE, top=WELL_TOP, sides=WELL_SIDES):
    """cave: where the routines go: build_tiger_stripes' (for its stripes
    routine), then 'wdivider' (view r3, ctx r4), standing in for the splitter
    Draw's call of sub_3f304, and its constants, among them 'wmargin' (the
    float margin, the sidebar's margins and the divider's width), 'wone'
    (1.0), 'wzero' (0.0) and 'wmone' (-1.0, the file pane's top margin).
    Returns (bytes, entries)."""
    scode, sent = build_tiger_stripes(cave, stubs, only_stripes=True)
    base = (cave + len(scode) + 15) & ~15
    consts = struct.pack('>7f', 1.0, float(margin), 0.0, line / 255.0, sides / 255.0, top / 255.0, -1.0)
    ONE, MARGIN, ZERO, LINE, SIDES, TOP, MONE = 0, 4, 8, 12, 16, 20, 24
    a = Asm(base)
    a.data(consts)
    hi, lo = (base + 0x8000) >> 16, base & 0xffff
    K = 31
    def fill(rect_off, gray):             # (the rect is always at 0x50)
        assert rect_off == 0x50
        a.lfs(1, gray, K)
        a.bl('wfill')
    # wfill(f1 gray): fill {0x50} with it, on wdivider's frame (LR at 0x80:
    # its locals end at 0x88, where the saved r26..r31 start)
    a.label('wfill')
    a.mflr(0)
    a.stw(0, 0x80, 1)
    a.mr(3, 28)
    a.fmr(2, 1); a.fmr(3, 1); a.lfs(4, ONE, K)
    a.bl(stubs['_CGContextSetRGBFillColor'])
    a.mr(3, 28)
    a.addi(9, 1, 0x50)
    a.lswi(4, 9, 16)
    a.bl(stubs['_CGContextFillRect'])
    a.lwz(0, 0x80, 1)
    a.mtlr(0)
    a.blr()
    a.label('wdivider')
    a.mflr(0)
    _stmw(a, 26, -24, 1)
    a.stw(0, 8, 1)
    a.stwu(1, -0xa0, 1)
    a.lis(K, hi)
    a.addi(K, K, lo)
    a.mr(27, 3)                             # view
    a.mr(28, 4)                             # ctx
    a.bl(TIGER_BAR_FILL)                    # the splitter's own background
    a.addi(9, 27, TIGER_DIVIDER_RECT)       # divider rect {x, y, w, h} at 0x40
    a.lswi(4, 9, 16)
    a.addi(29, 1, 0x40)
    a.stswi(4, 29, 16)
    # the strip left of the files, striped: {0, y, x + w, h}
    a.lfs(0, ZERO, K); a.stfs(0, 0x50, 1)
    a.lfs(0, 0x44, 1); a.stfs(0, 0x54, 1)
    a.lfs(0, 0x40, 1); a.lfs(13, 0x48, 1); a.fadds(0, 0, 13); a.stfs(0, 0x58, 1)
    a.lfs(0, 0x4c, 1); a.stfs(0, 0x5c, 1)
    a.mr(3, 28)
    a.addi(4, 1, 0x50)
    a.mr(5, 27)
    a.bl(sent['stripes_fn'])
    # the line: {x + w - 1, y, 1, h}
    a.lfs(0, 0x58, 1); a.lfs(13, ONE, K); a.fsubs(0, 0, 13); a.stfs(0, 0x50, 1)
    a.stfs(13, 0x58, 1)
    fill(0x50, LINE)
    # the divider for the status bar's edge (build_tiger_divupdate)
    a.mr(3, 27)
    a.bl(divupdate)
    # collapsed (the divider at the left edge): no frame
    a.lfs(0, 0x40, 1); a.lfs(13, ZERO, K); a.fcmpu(0, 13)
    a.ble('wdone')
    # the frame, 1 px around the sidebar {m, y, x - 1 - m, h - m}: o = {m - 1,
    # y - 1, x - m + 1, h - m + 2} at 0x60 (its top row, the status bar's
    # last, is the bar's top edge: clipped here, build_tiger_edge draws it)
    a.lfs(0, MARGIN, K); a.lfs(13, ONE, K); a.fsubs(0, 0, 13); a.stfs(0, 0x60, 1)      # m - 1
    a.lfs(0, 0x44, 1); a.fsubs(0, 0, 13); a.stfs(0, 0x64, 1)                           # y - 1
    a.lfs(0, 0x40, 1); a.lfs(13, 0x60, 1); a.fsubs(0, 0, 13); a.stfs(0, 0x68, 1)      # x - (m - 1)
    a.lfs(0, 0x4c, 1); a.fsubs(0, 0, 13); a.lfs(13, ONE, K); a.fadds(0, 0, 13); a.fadds(0, 0, 13)
    a.fadds(0, 0, 13); a.stfs(0, 0x6c, 1)                                               # h - (m - 1) + 2
    # left {ox, oy, 1, oh}, right {ox + ow - 1, oy, 1, oh}
    for k, src in enumerate((0x60, 0x64, 0x68, 0x6c)):
        a.lfs(0, src, 1); a.stfs(0, 0x50 + 4 * k, 1)
    a.lfs(0, ONE, K); a.stfs(0, 0x58, 1)
    fill(0x50, SIDES)
    a.lfs(0, 0x60, 1); a.lfs(13, 0x68, 1); a.fadds(0, 0, 13); a.lfs(13, ONE, K); a.fsubs(0, 0, 13)
    a.stfs(0, 0x50, 1)
    fill(0x50, SIDES)
    # bottom {ox, oy + oh - 1, ow, 1} (HIView: y down)
    a.lfs(0, 0x60, 1); a.stfs(0, 0x50, 1)
    a.lfs(0, 0x64, 1); a.lfs(13, 0x6c, 1); a.fadds(0, 0, 13); a.lfs(13, ONE, K); a.fsubs(0, 0, 13)
    a.stfs(0, 0x54, 1)
    a.lfs(0, 0x68, 1); a.stfs(0, 0x58, 1)
    a.lfs(0, ONE, K); a.stfs(0, 0x5c, 1)
    fill(0x50, SIDES)
    a.label('wdone')
    a.lwz(0, 0xa8, 1)
    a.addi(1, 1, 0xa0)
    a.mtlr(0)
    _lmw(a, 26, -24, 1)
    a.blr()
    code = scode + bytes(base - cave - len(scode)) + a.assemble()
    return code, {'wdivider': a.labels['wdivider'], 'wmargin': base + MARGIN, 'wone': base + ONE,
                  'wzero': base + ZERO, 'wmone': base + MONE}


# The top edge of 'header' and 'well' on Tiger (cave.EDGE_*): the status
# bar's Draw ends in a fill of its last row in its line gray; that fill goes
# to build_tiger_edge's routine instead: the row in the edge's gray (the list
# header's top line, or the well's frame top), and, for the well, its first
# margin - 1 columns in the bar's pinstripe there (left of the well's frame).
# The file pane and the sidebar start under it, as on Panther (Tiger's
# splitter can't draw outside itself: no CGContextResetClip there).
TIGER_EDGE_STUBS = ['_CGContextSetRGBFillColor', '_CGContextFillRect']


TIGER_BAR_STASH = 0x3bd540            # __DATA's zero-fill tail, past __common: the status bar view (build_tiger_bar)


def build_tiger_well_edge(cave, stubs, margin, top=WELL_TOP, stripe=WELL_BAR_STRIPE, stash=TIGER_BAR_STASH):
    """The well's edge(ctx r3, rect r4..r7 by value: the bar's last row): the
    row in the bar's pinstripe gray; over the sidebar, from its frame's left
    (margin - 1) to the divider, its frame's top line, and from the divider's
    line on, the files' top edge, both `top` gray. The divider is the
    splitter's window property (build_tiger_well), the window the status
    bar's, whose view the bar routine left at `stash` earlier in this draw;
    with no property yet, the line runs from the frame's left on. Returns
    (bytes, {'edge': entry})."""
    consts = struct.pack('>4f', 1.0, top / 255.0, stripe / 255.0, float(margin - 1))
    ONE, TOP, STRIPE, MM1 = 0, 4, 8, 12
    a = Asm(cave)
    a.data(consts)
    hi, lo = (cave + 0x8000) >> 16, cave & 0xffff
    K = 31
    a.label('fill')                         # fill(f1 gray, r29 rect), on edge's frame (0x90: LR
    a.mflr(0)                               # at 0x78, the saved r29..r31 at 0x84..0x8f)
    a.stw(0, 0x78, 1)
    a.mr(3, 30)
    a.fmr(2, 1); a.fmr(3, 1); a.lfs(4, ONE, K)
    a.bl(stubs['_CGContextSetRGBFillColor'])
    a.mr(3, 30)
    a.lswi(4, 29, 16)
    a.bl(stubs['_CGContextFillRect'])
    a.lwz(0, 0x78, 1)
    a.mtlr(0)
    a.blr()
    a.label('edge')
    a.mflr(0)
    _stmw(a, 29, -12, 1)
    a.stw(0, 8, 1)
    a.stwu(1, -0x90, 1)
    a.lis(K, hi)
    a.addi(K, K, lo)
    a.mr(30, 3)
    a.addi(29, 1, 0x50)                     # the row at 0x50 (for the files' edge) and 0x40
    a.stswi(4, 29, 16)
    a.addi(29, 1, 0x40)
    a.stswi(4, 29, 16)
    a.lfs(0, MM1, K); a.stfs(0, 0x60, 1); a.stfs(0, 0x64, 1)   # the divider {x, line x, ...}: none yet
    a.lis(9, (stash + 0x8000) >> 16)       # (set: the bar routine ran earlier in this draw)
    a.lwz(3, stash & 0xffff, 9)
    a.lwz(3, TIGER_HIVIEW, 3)
    a.stw(3, 0x70, 1)
    a.bl(stubs['_HIViewGetWindow'])
    a.stw(3, 0x7c, 1)                       # this window's status bar, for build_tiger_divupdate
    a.lis(4, _ostype('Aqfn') >> 16); a.emit(d_form(24, 4, 4, _ostype('Aqfn') & 0xffff))
    a.lis(5, _ostype('barv') >> 16); a.emit(d_form(24, 5, 5, _ostype('barv') & 0xffff))
    a.li(6, 4)
    a.addi(7, 1, 0x70)
    a.bl(stubs['_SetWindowProperty'])
    a.lwz(3, 0x7c, 1)
    a.lis(4, _ostype('Aqfn') >> 16); a.emit(d_form(24, 4, 4, _ostype('Aqfn') & 0xffff))
    a.lis(5, _ostype('divx') >> 16); a.emit(d_form(24, 5, 5, _ostype('divx') & 0xffff))
    a.li(6, TIGER_DIVX_SIZE)
    a.li(7, 0)
    a.addi(8, 1, 0x60)
    a.bl(stubs['_GetWindowProperty'])
    a.lfs(1, STRIPE, K)
    a.bl('fill')                            # the row, pinstripe gray
    a.lfs(0, 0x60, 1); a.lfs(13, MM1, K); a.fcmpu(0, 13)
    a.ble('files')
    a.fsubs(0, 0, 13); a.stfs(0, 0x48, 1)  # the frame's top: {m - 1, y, x - (m - 1), 1}
    a.stfs(13, 0x40, 1)
    a.lfs(1, TOP, K)
    a.bl('fill')
    a.label('files')                        # the files' top edge: {line x, y, row w, 1}
    a.addi(29, 1, 0x50)
    a.lfs(0, 0x64, 1); a.stfs(0, 0x50, 1)
    a.lfs(1, TOP, K)
    a.bl('fill')
    a.lwz(0, 0x98, 1)
    a.addi(1, 1, 0x90)
    a.mtlr(0)
    _lmw(a, 29, -12, 1)
    a.blr()
    return a.assemble(), {'edge': a.labels['edge']}


TIGER_WELL_EDGE_STUBS = ['_CGContextSetRGBFillColor', '_CGContextFillRect', '_HIViewGetWindow', '_GetWindowProperty',
                         '_SetWindowProperty']


def build_tiger_edge(cave, stubs, gray, stripe_cols=0, stripe=WELL_BAR_STRIPE):
    """edge(ctx r3, rect r4..r7 by value: the bar's last row). Returns
    (bytes, {'edge': entry})."""
    consts = struct.pack('>4f', 1.0, gray / 255.0, stripe / 255.0, float(stripe_cols))
    ONE, GRAY, STRIPE, COLS = 0, 4, 8, 12
    a = Asm(cave)
    a.data(consts)
    hi, lo = (cave + 0x8000) >> 16, cave & 0xffff
    a.label('edge')
    a.mflr(0)
    _stmw(a, 30, -8, 1)
    a.stw(0, 8, 1)
    a.stwu(1, -0x60, 1)
    a.lis(31, hi)
    a.addi(31, 31, lo)
    a.mr(30, 3)
    a.addi(9, 1, 0x40)
    a.stswi(4, 9, 16)
    for g, cols in ((GRAY, False), (STRIPE, True)):
        if cols and not stripe_cols:
            continue
        if cols:
            a.lfs(0, COLS, 31); a.stfs(0, 0x48, 1)
        a.mr(3, 30)
        a.lfs(1, g, 31); a.fmr(2, 1); a.fmr(3, 1); a.lfs(4, ONE, 31)
        a.bl(stubs['_CGContextSetRGBFillColor'])
        a.mr(3, 30)
        a.addi(9, 1, 0x40)
        a.lswi(4, 9, 16)
        a.bl(stubs['_CGContextFillRect'])
    a.lwz(0, 0x68, 1)
    a.addi(1, 1, 0x60)
    a.mtlr(0)
    _lmw(a, 30, -8, 1)
    a.blr()
    return a.assemble(), {'edge': a.labels['edge']}


# Jaguar's toolbar buttons on Tiger (patch.py 'toolbar', images: toolbar.py
# TIGER_IDS). Tiger's Back/Forward and View controls are HISegmentedViews
# (2 and 3 segments, both made by sub_34650), drawn by the theme. Each gets a
# Carbon event handler, installed as its segments are counted, that draws
# Jaguar's images instead (kEventControlDraw) and hit-tests by their slots
# (kEventControlHitTest: HIView's tracking asks the view for the part under
# the mouse, so clicks follow the new layout). Part n is segment n, as in
# HISegmentView::IsHitByPointInternal; a disabled segment is part 0.
#
# A segment's image: its first id + its record's state table, indexed by
#   0 inactive (window inactive, view or segment disabled), not selected
#   1 inactive, selected       2 pressed      3 pressed (Graphite)
#   4 selected                 5 selected (Graphite)        6 normal
# In the search window the View control's last segment is Group instead of
# Column (command 'Vgrp'): its images are the next 6 ids (toolbar.TIGER_GROUP).
# Images are read from Finder.rsrc at each draw (GetResource keeps the data
# loaded; the CGImage lives for the draw only), so nothing is stored.
TIGER_GRAPHITE = 0x1931c0          # sub_1931c0(): 1 when the appearance is Graphite (CopyThemeIdentifier)
TIGER_TOOLBAR_STUBS = ['_GetControlEventTarget', '_InstallEventHandler', '_HISegmentedViewSetSegmentCount',
                       '_HISegmentedViewGetSegmentCount', '_HISegmentedViewIsSegmentEnabled',
                       '_GetEventKind', '_GetEventParameter', '_SetEventParameter', '_HIViewGetBounds',
                       '_IsControlActive', '_IsControlEnabled', '_GetControlHilite', '_GetControl32BitValue',
                       '_HISegmentedViewGetSegmentCommand',
                       '_GetResource', '_GetHandleSize', '_CGDataProviderCreateWithData',
                       '_CGImageCreateWithPNGDataProvider', '_CGDataProviderRelease', '_HIViewDrawCGImage',
                       '_CGImageRelease']
# per segment count (2, 3): first id, ids per segment, slot width, state table
TIGER_SEGMENTS = [
    (8910, 4, 28.0, (2, 2, 1, 3, 0, 0, 0)),     # Back, Forward: normal, pressed, disabled, pressed (Graphite)
    (8620, 6, 26.0, (0, 1, 2, 2, 3, 4, 5)),     # View (toolbar.VIEW_STATES)
]
TIGER_BUTTON_HEIGHT = 25.0
GROUP_COMMAND = 'Vgrp'             # the search window's third View segment (sub_34fb4), images after Column's
EVENT_NOT_HANDLED = -9874


def _fdivs(a, ft, fa, fb): a.emit((59 << 26) | (ft << 21) | (fa << 16) | (fb << 11) | (18 << 1))
def _mulli(a, rt, ra, v): a.emit(d_form(7, rt, ra, v))
def _clrlwi24(a, ra, rs): _rlwinm(a, ra, rs, 0, 24, 31)
def _bgt(a, t): a._br('bc', t, 12, 29)
def _lhz(a, rt, d, ra): a.emit(d_form(40, rt, ra, d))
def _lbz(a, rt, d, ra): a.emit(d_form(34, rt, ra, d))
def _add(a, rt, ra, rb): a.emit((31 << 26) | (rt << 21) | (ra << 16) | (rb << 11) | (266 << 1))
def _extsh(a, ra, rs): a.emit((31 << 26) | (rs << 21) | (ra << 16) | (922 << 1))


def _ostype(s):
    return struct.unpack('>I', s.encode('mac_roman'))[0]


def build_tiger_toolbar(cave, stubs, graphite=TIGER_GRAPHITE, segments=TIGER_SEGMENTS):
    """cave: where the routines go (constants first). Entry points:
      segviews(view r3, count r4): stands in for sub_34650's
        HISegmentedViewSetSegmentCount: installs the handler on the view
        (userData = the view), then counts its segments
      handler(callRef r3, event r4, view r5): the Carbon event handler
    Returns (bytes, {'segviews': addr})."""
    REC = 20                                   # record: u16 first id, u16 ids per segment, u16 count, pad, f32 slot, 7 states, pad
    consts = struct.pack('>4I', _ostype('cntl'), 4, _ostype('cntl'), 3)      # 0  SPECS
    consts += struct.pack('>2f', 0.0, TIGER_BUTTON_HEIGHT)                   # 16 ZERO HEIGHT
    RECS = len(consts)
    for n, (first, per, slot, states) in enumerate(segments, start=2):
        consts += struct.pack('>3HH f 7B x', first, per, n, 0, slot, *states)
    assert len(consts) == RECS + REC * len(segments)
    SPECS, ZERO, HEIGHT = 0, 16, 20
    a = Asm(cave)
    a.data(consts)
    hi, lo = (cave + 0x8000) >> 16, cave & 0xffff
    K = 31

    # segviews(view, count)
    a.label('segviews')
    a.mflr(0)
    _stmw(a, 30, -8, 1)
    a.stw(0, 8, 1)
    a.stwu(1, -0x50, 1)
    a.mr(31, 3)
    a.mr(30, 4)
    a.bl(stubs['_GetControlEventTarget'])
    a.lis(4, 0); a.addi(4, 4, 0)               # handler address, patched below
    fix_handler = len(a.words) - 2
    a.li(5, 2)
    a.lis(6, hi); a.addi(6, 6, lo + SPECS)
    a.mr(7, 31)
    a.li(8, 0)
    a.bl(stubs['_InstallEventHandler'])
    a.mr(3, 31)
    a.mr(4, 30)
    a.lwz(0, 0x58, 1)
    a.addi(1, 1, 0x50)
    a.mtlr(0)
    _lmw(a, 30, -8, 1)
    a.b(stubs['_HISegmentedViewSetSegmentCount'])

    # handler(callRef, event, view); frame 0xa0: 0x40 bounds, 0x50 image rect,
    # 0x60 ctx (draw) or point (hit test), 0x68 selected (draw) / part,
    # fctiwz (hit test), 0x6c ids to add for Group (draw), 0x70 Graphite,
    # 0x74 handle, 0x78 provider, 0x7c image; 0x80.. the saved r24..r31
    # r24 value, r25 hilite, r26 active, r27 segment, r28 record, r29 event, r30 view
    a.label('handler')
    a.mflr(0)
    _stmw(a, 24, -32, 1)
    a.stw(0, 8, 1)
    a.stwu(1, -0xa0, 1)
    a.lis(K, hi); a.addi(K, K, lo)
    a.mr(30, 5)
    a.mr(29, 4)
    a.mr(3, 30)
    a.bl(stubs['_HISegmentedViewGetSegmentCount'])
    a.addi(28, 3, -2)
    a.cmpwi(28, 0); a.blt('pass')
    a.cmpwi(28, len(segments) - 1); _bgt(a, 'pass')
    _mulli(a, 28, 28, REC)
    _add(a, 28, 28, K)
    a.addi(28, 28, RECS)
    a.mr(3, 29)
    a.bl(stubs['_GetEventKind'])
    a.cmpwi(3, 3); a.beq('hit')
    a.cmpwi(3, 4); a.bne('pass')

    # --- kEventControlDraw
    a.mr(3, 29)
    a.lis(4, _ostype('cntx') >> 16); a.emit(d_form(24, 4, 4, _ostype('cntx') & 0xffff))   # ori
    a.mr(5, 4)
    a.li(6, 0); a.li(7, 4); a.li(8, 0)
    a.addi(9, 1, 0x60)
    a.bl(stubs['_GetEventParameter'])
    a.cmpwi(3, 0); a.bne('pass')
    a.mr(3, 30); a.addi(4, 1, 0x40)
    a.bl(stubs['_HIViewGetBounds'])
    a.mr(3, 30)
    a.bl(stubs['_IsControlActive'])
    _clrlwi24(a, 26, 3)
    a.mr(3, 30)
    a.bl(stubs['_IsControlEnabled'])
    _clrlwi24(a, 3, 3)
    a.cmpwi(3, 0); a.bne('enabled')
    a.li(26, 0)
    a.label('enabled')
    a.mr(3, 30)
    a.bl(stubs['_GetControlHilite'])
    _extsh(a, 25, 3)
    a.mr(3, 30)
    a.bl(stubs['_GetControl32BitValue'])
    a.mr(24, 3)
    a.bl(graphite)
    _clrlwi24(a, 3, 3)
    a.stw(3, 0x70, 1)
    # the search window's View control: its last segment is Group ('Vgrp'),
    # whose images follow the segment's own (0x6c: ids to add for it)
    a.mr(3, 30)
    _lhz(a, 4, 4, 28)
    a.bl(stubs['_HISegmentedViewGetSegmentCommand'])
    a.lis(0, _ostype(GROUP_COMMAND) >> 16); a.emit(d_form(24, 0, 0, _ostype(GROUP_COMMAND) & 0xffff))
    a.cmpw(3, 0)
    a.li(0, 0)
    a.bne('nalt')
    _lhz(a, 0, 2, 28)
    a.label('nalt')
    a.stw(0, 0x6c, 1)
    # the image rect: {x, y, slot, 25}
    a.lfs(0, 0x40, 1); a.stfs(0, 0x50, 1)
    a.lfs(0, 0x44, 1); a.stfs(0, 0x54, 1)
    a.lfs(0, 8, 28); a.stfs(0, 0x58, 1)
    a.lfs(0, HEIGHT, K); a.stfs(0, 0x5c, 1)
    a.li(27, 1)
    a.label('seg')
    # state: r0 = selected (0/1), then the code in r9
    a.subf(0, 24, 27)                          # 0 when this segment is the value
    a.cmpwi(0, 0)
    a.li(0, 0); a.bne('nsel'); a.li(0, 1)
    a.label('nsel')
    a.stw(0, 0x68, 1)
    a.mr(3, 30); a.mr(4, 27)
    a.bl(stubs['_HISegmentedViewIsSegmentEnabled'])
    _clrlwi24(a, 3, 3)
    a.lwz(9, 0x68, 1)                          # inactive: 0 or 1
    a.cmpwi(3, 0); a.beq('state')
    a.cmpwi(26, 0); a.beq('state')
    a.lwz(0, 0x70, 1)
    a.cmpw(25, 27); a.bne('npress')
    a.addi(9, 0, 2); _add(a, 9, 9, 0); a.b('state')   # pressed: 2 + Graphite
    a.label('npress')
    a.cmpwi(9, 0); a.beq('normal')
    a.addi(9, 0, 4); _add(a, 9, 9, 0); a.b('state')   # selected: 4 + Graphite
    a.label('normal')
    a.li(9, 6)
    a.label('state')
    _add(a, 9, 9, 28)
    _lbz(a, 9, 12, 9)                          # the record's state table
    _lhz(a, 0, 2, 28)                          # ids per segment
    a.addi(4, 27, -1)
    a.emit((31 << 26) | (4 << 21) | (4 << 16) | (0 << 11) | (235 << 1))   # mullw r4,r4,r0
    _lhz(a, 0, 0, 28)
    _add(a, 4, 4, 0)
    _add(a, 4, 4, 9)                           # r4 = first + (segment - 1) * per + state
    _lhz(a, 0, 4, 28)
    a.cmpw(27, 0)
    a.bne('nlast')
    a.lwz(0, 0x6c, 1)
    _add(a, 4, 4, 0)                           # (+ per for Group)
    a.label('nlast')
    a.lis(3, _ostype('PNG ') >> 16); a.emit(d_form(24, 3, 3, _ostype('PNG ') & 0xffff))
    a.bl(stubs['_GetResource'])
    a.cmpwi(3, 0); a.beq('next')
    a.stw(3, 0x74, 1)
    a.bl(stubs['_GetHandleSize'])
    a.mr(5, 3)
    a.lwz(4, 0x74, 1); a.lwz(4, 0, 4)
    a.li(3, 0); a.li(6, 0)
    a.bl(stubs['_CGDataProviderCreateWithData'])
    a.cmpwi(3, 0); a.beq('next')
    a.stw(3, 0x78, 1)
    a.li(4, 0); a.li(5, 0); a.li(6, 0)
    a.bl(stubs['_CGImageCreateWithPNGDataProvider'])
    a.stw(3, 0x7c, 1)
    a.lwz(3, 0x78, 1)
    a.bl(stubs['_CGDataProviderRelease'])
    a.lwz(5, 0x7c, 1)
    a.cmpwi(5, 0); a.beq('next')
    a.lwz(3, 0x60, 1); a.addi(4, 1, 0x50)
    a.bl(stubs['_HIViewDrawCGImage'])
    a.lwz(3, 0x7c, 1)
    a.bl(stubs['_CGImageRelease'])
    a.label('next')
    a.lfs(0, 0x50, 1); a.lfs(13, 8, 28); a.fadds(0, 0, 13); a.stfs(0, 0x50, 1)
    a.addi(27, 27, 1)
    _lhz(a, 0, 4, 28)
    a.cmpw(27, 0)
    a.ble('seg')
    a.li(3, 0)
    a.b('out')

    # --- kEventControlHitTest: part = 1 + (x - left) / slot, if inside and enabled
    a.label('hit')
    a.mr(3, 29)
    a.lis(4, _ostype('mloc') >> 16); a.emit(d_form(24, 4, 4, _ostype('mloc') & 0xffff))
    a.lis(5, _ostype('hipt') >> 16); a.emit(d_form(24, 5, 5, _ostype('hipt') & 0xffff))
    a.li(6, 0); a.li(7, 8); a.li(8, 0)
    a.addi(9, 1, 0x60)
    a.bl(stubs['_GetEventParameter'])
    a.cmpwi(3, 0); a.bne('pass')
    a.mr(3, 30); a.addi(4, 1, 0x40)
    a.bl(stubs['_HIViewGetBounds'])
    a.li(27, 0)
    a.lfs(1, ZERO, K)
    a.lfs(0, 0x64, 1); a.lfs(13, 0x44, 1); a.fsubs(0, 0, 13)      # y - top
    a.fcmpu(0, 1); a.blt('part')
    a.lfs(13, 0x4c, 1); a.fcmpu(0, 13); a.bge('part')
    a.lfs(0, 0x60, 1); a.lfs(13, 0x40, 1); a.fsubs(0, 0, 13)      # x - left
    a.fcmpu(0, 1); a.blt('part')
    a.lfs(13, 8, 28); _fdivs(a, 0, 0, 13)
    _fctiwz(a, 0, 0)
    _stfd(a, 0, 0x68, 1)
    a.lwz(27, 0x6c, 1)
    a.addi(27, 27, 1)
    _lhz(a, 0, 4, 28)
    a.cmpw(27, 0)
    a.li(9, 0)
    _bgt(a, 'nopart')
    a.mr(3, 30); a.mr(4, 27)
    a.bl(stubs['_HISegmentedViewIsSegmentEnabled'])
    _clrlwi24(a, 3, 3)
    a.cmpwi(3, 0); a.bne('part')
    a.label('nopart')
    a.li(27, 0)
    a.label('part')
    a.sth(27, 0x68, 1)
    a.mr(3, 29)
    a.lis(4, _ostype('cprt') >> 16); a.emit(d_form(24, 4, 4, _ostype('cprt') & 0xffff))
    a.mr(5, 4)
    a.li(6, 2)
    a.addi(7, 1, 0x68)
    a.bl(stubs['_SetEventParameter'])
    a.li(3, 0)
    a.b('out')

    a.label('pass')
    a.li(3, EVENT_NOT_HANDLED)
    a.label('out')
    a.lwz(0, 0xa8, 1)
    a.addi(1, 1, 0xa0)
    a.mtlr(0)
    _lmw(a, 24, -32, 1)
    a.blr()

    h = a.labels['handler']
    a.words[fix_handler] = d_form(15, 4, 0, (h + 0x8000) >> 16)
    a.words[fix_handler + 1] = d_form(14, 4, 4, h & 0xffff)
    code = a.assemble()
    return code, {'segviews': a.labels['segviews']}
