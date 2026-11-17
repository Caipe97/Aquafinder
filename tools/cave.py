"""Jaguar-style bottom-bar shadow for the Panther Finder.

The status bar's background eraser (EraseViewBackground, see patch.py
'statusbar') ends in an Aqua branch:

    li r3,0x34 ; li r4,0x20 ; li r5,1 ; bl SetThemeBackground
    mr r3,r30  ; bl EraseRect           ; (falls through to the epilogue)

r30 = Rect* to erase (local coordinates, port already focused), r31 = view.
We replace the first instruction with a branch into the free space at the end
of __TEXT, where this routine runs instead (a float constant for the
lighter pane border lines lives right after it, see patch.py 'softlines'):

    if view->metal (+0x120) == 0:      (status bar at the top, toolbar hidden)
        do the original two calls
    else:                               (toolbar shown, status bar at the bottom)
        paint the rect row by row with a gray picked by the row's distance
        from the bottom of the port, Jaguar's 15-row curve resampled to 19 rows
        (the bar's 18 rows take rows 1..18; row 0's gray is the pane border color)

Stack use stays inside the host function's own frame (0x38..0x57 are free on
this path; the callee-saved r28 is spilled there and restored).
"""
import struct

# Jaguar 10.2.8 Finder window bottom, measured top->bottom on a running Jaguar
# Finder: a 15-row strip starting at 212.
JAGUAR_STRIP = [212, 217, 222, 229, 233, 239, 243, 247, 250, 252, 253, 253, 251, 248, 245]

# Panther's bar height in the patched Finder (patch.py 'slimbar': 15, which
# matches the resize handle; stock is 18).
BAR_HEIGHT = 15


def gradient_for(bar_height=BAR_HEIGHT, strip=JAGUAR_STRIP):
    """Top->bottom grays for the panes' 1px border row (row 0, 212) plus the
    bar's rows: Jaguar's strip resampled to bar_height + 1 rows."""
    n = bar_height + 1
    out = []
    for i in range(n):
        x = i * (len(strip) - 1) / (n - 1)
        k = int(x); f = x - k
        out.append(round(strip[k] * (1 - f) + strip[min(k + 1, len(strip) - 1)] * f))
    return out


GRADIENT_TOP_TO_BOTTOM = gradient_for()

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


def build(cave, hook, stubs, gradient=GRADIENT_TOP_TO_BOTTOM, line_gray=None):
    """cave: address of the routine; hook: address of the hooked 'li r3,0x34'
    (the host epilogue is at hook+0x18);
    stubs: dict of import name -> stub address.
    Returns (bytes, address of the float border-line gray)."""
    if line_gray is None:
        line_gray = gradient[0] / 255.0    # the bar's darkest row

    a = Asm(cave)
    ret = hook + 0x18
    r0, r1, r3, r4, r5, r28, r30, r31 = 0, 1, 3, 4, 5, 28, 30, 31
    n = len(gradient)
    table_bottom_up = list(reversed(gradient))   # index 0 = bottom row

    a.lwz(r0, 0x120, r31)            # view->metal (status bar at the bottom)?
    a.cmpwi(r0, 0)
    a.beq('original')

    a.stw(r28, 0x38, r1)
    a.addi(r3, r1, 0x40)             # save pen color -> 0x40
    a.bl(stubs['_GetForeColor'])
    a.addi(r3, r1, 0x50)             # GetPort(0x50); GetPortBounds(port, 0x50)
    a.bl(stubs['_GetPort'])
    a.lwz(r3, 0x50, r1)
    a.addi(r4, r1, 0x50)
    a.bl(stubs['_GetPortBounds'])
    a.lha(r0, 0x54, r1)              # port bottom -> 0x46 (16-bit spare slot)
    a.sth(r0, 0x46, r1)
    a.lha(r28, 0, r30)               # y = rect.top - 1: also paint the row the panes'
    a.addi(r28, r28, -1)             # bottom borders sit on, so it's 212 under the divider too

    a.label('loop')
    a.lha(r0, 4, r30)                # while y < rect.bottom
    a.cmpw(r28, r0)
    a.bge('done')
    a.lha(r4, 0x46, r1)              # k = port.bottom - y - 1, clamped to [0, n-1]
    a.subf(r4, r28, r4)
    a.addi(r4, r4, -1)
    a.cmpwi(r4, n - 1)
    a.ble('inrange')
    a.li(r4, n - 1)
    a.label('inrange')
    a.lis(r5, (a.labels.get('table', 0) >> 16))   # patched after layout
    lis_idx = len(a.words) - 1
    a.addi(r5, r5, 0)
    addi_idx = len(a.words) - 1
    a.lbzx(r0, r5, r4)               # v = table[k]; v16 = v * 0x101
    a.rlwimi(r0, r0, 8, 16, 23)
    a.sth(r0, 0x48, r1)
    a.sth(r0, 0x4a, r1)
    a.sth(r0, 0x4c, r1)
    a.addi(r3, r1, 0x48)
    a.bl(stubs['_RGBForeColor'])
    a.sth(r28, 0x50, r1)             # row = {y, left, y+1, right}
    a.lha(r0, 2, r30)
    a.sth(r0, 0x52, r1)
    a.addi(r0, r28, 1)
    a.sth(r0, 0x54, r1)
    a.lha(r0, 6, r30)
    a.sth(r0, 0x56, r1)
    a.addi(r3, r1, 0x50)
    a.bl(stubs['_PaintRect'])
    a.addi(r28, r28, 1)
    a.b('loop')

    a.label('done')
    a.addi(r3, r1, 0x40)             # restore pen color and r28/r29
    a.bl(stubs['_RGBForeColor'])
    a.lwz(r28, 0x38, r1)
    a.b(ret)

    a.label('original')              # toolbar hidden: original Aqua erase
    a.li(r3, 0x34)                   # the instruction the hook replaced
    a.b(hook + 4)                    # ... then the rest of the host code

    a.label('table')
    a.data(table_bottom_up)
    a.label('line_gray')             # float gray for the panes' 1px border lines
    a.data(struct.pack('>f', line_gray))

    t = a.labels['table']
    hi, lo = (t + 0x8000) >> 16, t & 0xffff       # ha/lo for lis+addi
    a.words[lis_idx] = d_form(15, r5, 0, hi)
    a.words[addi_idx] = d_form(14, r5, r5, lo)
    return a.assemble(), a.labels['line_gray']


STUBS_NEEDED = ['_GetForeColor', '_RGBForeColor', '_PaintRect', '_GetPort',
                '_GetPortBounds', '_SetThemeBackground', '_EraseRect']


def build_fill_white(addr, stubs, one_addr):
    """CGFillRectWhite(CGContextRef ctx /*r3*/, const CGRect *clipped /*r4*/,
                       const CGRect *view /*r5*/).

    Used by the sidebar splitter repaint, which runs inside a
    QDBeginCGContext/QDEndCGContext bracket, so a QuickDraw EraseRgn there is
    never seen (stale pixels while dragging the divider). Fills with the
    window's white background through CoreGraphics instead -- except the
    view's bottom row, which is the line the panes' borders sit on (the
    gradient routine paints it 212), so the divider never shows a white notch.
    one_addr: address of a float 1.0 constant reachable with lis/lfs."""
    a = Asm(addr)
    r0, r1, r3, r4, r5, r9, r31 = 0, 1, 3, 4, 5, 9, 31
    a.mflr(r0)
    a.stw(r0, 8, r1)
    a.stwu(r1, -0x60, r1)
    a.stw(r31, 0x5c, r1)
    a.mr(r31, r3)                    # ctx
    a.lfs(5, 4, r5)                  # f5 = view.origin.y (CG: the bottom edge)
    a.lswi(r5, r4, 16)               # copy the clipped CGRect (r5..r8) into our frame
    a.addi(r9, r1, 0x40)
    a.stswi(r5, r9, 16)
    a.lis(r9, (one_addr + 0x8000) >> 16)
    a.lfs(1, one_addr & 0xffff, r9)  # f1 = 1.0
    a.lfs(3, 0x44, r1)               # if clipped.y == view.y: skip the bottom row
    a.fcmpu(3, 5)
    a.bne('fill')
    a.fadds(3, 3, 1)                 #   y += 1
    a.stfs(3, 0x44, r1)
    a.lfs(4, 0x4c, r1)               #   h -= 1
    a.fsubs(4, 4, 1)
    a.stfs(4, 0x4c, r1)
    a.label('fill')
    a.fmr(2, 1)                      # gray = 1.0, alpha = 1.0 (r3 still = ctx)
    a.bl(stubs['_CGContextSetGrayFillColor'])
    a.mr(r3, r31)
    a.addi(r9, r1, 0x40)
    a.lswi(r4, r9, 16)               # rect by value in r4..r7
    a.bl(stubs['_CGContextFillRect'])
    a.lwz(r31, 0x5c, r1)
    a.addi(r1, r1, 0x60)
    a.lwz(r0, 8, r1)
    a.mtlr(r0)
    a.blr()
    return a.assemble()


FILL_STUBS = ['_CGContextSetGrayFillColor', '_CGContextFillRect']


def build_divider_entry(addr, cg_rect_fn, fill_body):
    """Second entry into CGFillRectWhite for the sidebar divider's draw routine.

    The divider draws its grip image and the pane borders inside a
    QDBeginCGContext bracket but never erases its own background; in a metal
    window the Window Manager repainted metal behind it on every update, in an
    Aqua window nothing does, so resizing the window leaves a trail of grips.
    The draw routine's `bl cg_rect_fn` (QD frame -> CGRect into r29) is
    redirected here: do that call, then fill the view's CGRect white (all but
    its bottom row, the border line) before returning to draw the grip.
    Host registers: r27 = &CGContextRef, r29 = the view's CGRect."""
    a = Asm(addr)
    r0, r1, r3, r4, r5, r27, r29, r31 = 0, 1, 3, 4, 5, 27, 29, 31
    a.mflr(r0)                       # same prologue/frame as CGFillRectWhite
    a.stw(r0, 8, r1)
    a.stwu(r1, -0x60, r1)
    a.stw(r31, 0x5c, r1)
    a.bl(cg_rect_fn)                 # the call we replaced (args set by the host)
    a.lwz(r3, 0, r27)                # ctx
    a.mr(r4, r29)                    # clipped = view rect
    a.mr(r5, r29)                    # view rect (bottom row is skipped)
    a.b(fill_body)                   # shared body + epilogue returns to the host
    return a.assemble()
