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


def build_framedbox_fill(addr, stubs):
    """FramedBoxFill, called instead of the framed-box painter's
    `bl CGContextStrokeRect` (the search results' horizontal splitter, between
    the results and the path pane). Its metal fill is skipped ('gap'), so
    nothing erased the box: dragging the splitter left bits of the scroll bar
    behind in it. Same arguments as CGContextStrokeRect (r3 = context,
    r4..r7 = the CGRect, inset half a pixel for the 1px stroke):

        CGContextSetRGBFillColor(ctx, 1, 1, 1, 1)
        CGContextFillRect(ctx, rect)       the stroke covers the border after
        CGContextStrokeRect(ctx, rect)     (tail call)
    """
    a = Asm(addr)
    r0, r1, r3, r12 = 0, 1, 3, 12
    a.mflr(r0)
    a.stw(r0, 8, r1)
    a.stwu(r1, -0x60, r1)
    a.addi(r12, r1, 0x40)            # save ctx + rect (r3..r7) at 0x40..0x53
    a.stswi(r3, r12, 20)
    a.lis(r0, 0x3f80)                # 1.0f, for every color component
    a.stw(r0, 0x58, r1)
    a.lfs(1, 0x58, r1)
    a.fmr(2, 1)
    a.fmr(3, 1)
    a.fmr(4, 1)
    a.bl(stubs['_CGContextSetRGBFillColor'])     # r3 = ctx still
    a.addi(r12, r1, 0x40)
    a.lswi(r3, r12, 20)
    a.bl(stubs['_CGContextFillRect'])
    a.addi(r12, r1, 0x40)
    a.lswi(r3, r12, 20)
    a.addi(r1, r1, 0x60)
    a.lwz(r0, 8, r1)
    a.mtlr(r0)
    a.b(stubs['_CGContextStrokeRect'])
    return a.assemble()


FRAMEDBOX_STUBS = ['_CGContextSetRGBFillColor', '_CGContextFillRect', '_CGContextStrokeRect']


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
