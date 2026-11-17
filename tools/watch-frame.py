"""Catch writes to a new status bar view's frame rect (+0xdc top, +0xe0 bottom)
and report the Finder call chain that made them."""
import sys, os, struct, time
sys.path.insert(0, os.path.dirname(__file__))
from gdbrsp import GDB

CTOR, CAVE, SIG = 0x4517c, 0x29ff10, 0x801f0120
TEXT_LO, TEXT_HI = 0x9000, 0x1c2000          # Finder __text
g = GDB()

def backtrace(r, depth=12):
    out, sp = [r['lr']], r['r'][1]
    for _ in range(depth):
        nsp = g.word(sp)
        if not nsp or nsp <= sp: break
        lr = g.word(nsp + 8)
        if lr: out.append(lr)
        sp = nsp
    return [hex(a - 4) for a in out if TEXT_LO <= a < TEXT_HI]

g.bp(CTOR)
obj, last, end = None, None, time.time() + 120
while time.time() < end:
    if last is not None: g.resume_from(last, {CTOR})
    if g.cont(timeout=max(1, end - time.time())) is None:
        g.interrupt(); break
    r = g.regs(); last = r['pc']
    if g.word(CAVE) == SIG and r['pc'] == CTOR:
        obj = r['r'][3]; break
g.bp(CTOR, on=False)
if obj is None:
    print('constructor not hit'); g.cont(timeout=0.5); sys.exit(1)
print('new status view %08x, watching +0xdc..+0xe3' % obj, flush=True)
assert g.cmd('Z2,%x,4' % (obj + 0xdc)) == 'OK'
assert g.cmd('Z2,%x,4' % (obj + 0xe0)) == 'OK'
end = time.time() + 90
n = 0
while time.time() < end and n < 10:
    if g.cont(timeout=max(1, end - time.time())) is None:
        g.interrupt(); break
    r = g.regs()
    rect = struct.unpack('>4h', g.mem(obj + 0xdc, 8))
    print('write pc=%08x rect=%s finder chain=%s' % (r['pc'], rect, backtrace(r)), flush=True)
    n += 1
g.cmd('z2,%x,4' % (obj + 0xdc)); g.cmd('z2,%x,4' % (obj + 0xe0))
g.cont(timeout=0.5)
print('done')
