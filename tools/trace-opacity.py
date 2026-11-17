"""Log AppKit's window opacity / opaque-shape decisions (any Cocoa process)."""
import sys, os, time, struct
sys.path.insert(0, os.path.dirname(__file__))
from gdbrsp import GDB

def f32(g, a):
    b = g.mem(a, 16)
    return tuple(round(x, 1) for x in struct.unpack('>4f', b)) if b else None

BPS = {
    0x92f54524: lambda g, r: 'CGSNewWindowWithOpaqueShape(type=%d shape=%08x opaque=%08x)' % (r[4], r[7], r[8]),
    0x92f0345c: lambda g, r: '_commonAwake: about to SetWindowOpacity(NO)',
    0x932a2d5c: lambda g, r: 'CGSSetWindowOpacity(win=%d, opaque=%d) from %08x' % (r[4], r[5], r[-1]),
    0x932a351c: lambda g, r: 'CGSSetWindowOpaqueShape(win=%d, region=%08x) from %08x' % (r[4], r[5], r[-1]),
    0x92f97af0: lambda g, r: '_NSCreateShapeForRoundedWindow(topRound=%d bottomRound=%d) from %08x' % (r[8], r[9], r[-1]),
    0x92f97b9c: lambda g, r: '  inset path rect %s' % (f32(g, r[30]),),
    0x92f97ba4: lambda g, r: '  empty-region path',
    0x92f6d65c: lambda g, r: '_NSShapeRoundedWindowWithWeighting(flags %d %d) from %08x' % (r[9], r[10], r[-1]),
    0x92f95cd8: lambda g, r: '_NSCreateWindow from %08x' % r[-1],
    0x92f54398: lambda g, r: '_NSCreateWindowWithOpaqueShape from %08x' % r[-1],
    0x92f03368: lambda g, r: '_commonAwake: frame responds to opaque-shape selector = %d' % r[3],
    0x932a355c: lambda g, r: 'CGSSetWindowShape(win=%d) from %08x' % (r[4], r[-1]),
    0x932a319c: lambda g, r: 'CGSSetWindowShapeWithWeighting(win=%d) from %08x' % (r[4], r[-1]),
}
g = GDB()
# QEMU resolves a breakpoint through the MMU of the process on the CPU when it
# is inserted: stop inside a Cocoa process first (AppKit's objc_msgSend stub).
g.bp(0x932a10bc); g.cont(timeout=60); g.bp(0x932a10bc, on=False)
for a in BPS: g.bp(a)
print('armed', flush=True)
last, end, n = None, time.time() + float(sys.argv[1]), 0
while time.time() < end and n < 80:
    if last is not None: g.resume_from(last, set(BPS))
    if g.cont(timeout=max(1, end - time.time())) is None:
        g.interrupt(); break
    rr = g.regs(); last = rr['pc']
    if rr['pc'] in BPS:
        regs = rr['r'] + [rr['lr'] - 4]
        print(BPS[rr['pc']](g, regs), flush=True); n += 1
for a in BPS: g.bp(a, on=False)
g.cont(timeout=0.5)
print('done', flush=True)
