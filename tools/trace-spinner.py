"""Catch the Finder's chasing-arrows draw and print its rectangles."""
import sys, os, struct, time
sys.path.insert(0, os.path.dirname(__file__))
from gdbrsp import GDB
CALL, CAVE, SIG = 0x5e3b4, 0x29ff10, 0x801f0120
g = GDB()
g.bp(CALL)
print('armed', flush=True)
last, end, n = None, time.time() + float(sys.argv[1]), 0
while time.time() < end and n < 3:
    if last is not None: g.resume_from(last, {CALL})
    if g.cont(timeout=max(1, end - time.time())) is None:
        g.interrupt(); break
    r = g.regs(); last = r['pc']
    if r['pc'] != CALL or g.word(CAVE) != SIG: continue
    a = r['r']
    cg = struct.unpack('>4f', g.mem(a[3], 16))
    obj = a[31]
    qd = struct.unpack('>4h', g.mem(obj + 0xf4, 8))
    print('spinner obj %08x CGRect(x,y,w,h)=%s  QD rect(t,l,b,r)@+0xf4=%s  lr=%08x' % (obj, cg, qd, r['lr']), flush=True)
    dump = g.mem(obj, 0x120)
    print('  obj words:', ' '.join('%04x' % w for w in struct.unpack('>144H', dump)), flush=True)
    n += 1
g.bp(CALL, on=False); g.cont(timeout=0.5)
print('done', flush=True)
