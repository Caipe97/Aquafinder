"""Log PowerPlant sizing calls made by the Finder while a window opens, then
report the ones aimed at the status bar view (found via the gradient routine)."""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(__file__))
from gdbrsp import GDB

STUBS = {0x1c2a88: 'LView::ResizeFrameBy', 0x1c2e58: 'LPane::ResizeFrameTo',
         0x1c3be8: 'LPane::PlaceInSuperFrameAt', 0x1c3ed8: 'LWindow::ResizeFrameBy',
         0x1c69f8: 'LView::AdaptToSuperFrameSize'}
CAVE = 0x29ff10
FINDER_SIG = 0x801f0120

g = GDB()
for a in list(STUBS) + [CAVE]:
    g.bp(a)
print('armed', flush=True)
log, status_view, deadline = [], None, time.time() + float(sys.argv[1] if len(sys.argv) > 1 else 120)
armed = set(STUBS) | {CAVE}
last_pc = None
while time.time() < deadline:
    if last_pc is not None:
        g.resume_from(last_pc, armed)
    stop = g.cont(timeout=max(1, deadline - time.time()))
    if stop is None:
        g.interrupt(); break
    r = g.regs()
    pc = last_pc = r['pc']
    if g.word(CAVE) != FINDER_SIG:          # another process at this address
        continue
    if pc == CAVE:
        rect = g.mem(r['r'][30], 8)
        status_view = r['r'][31]
        print('gradient routine: view=%08x rect=%s' % (status_view, rect.hex() if rect else None), flush=True)
        break
    a = r['r']
    log.append(dict(fn=STUBS[pc], this=a[3], r4=a[4], r5=a[5], r6=a[6], lr=r['lr']))
for a in list(STUBS) + [CAVE]:
    g.bp(a, on=False)
g.cont(timeout=0.5)
from collections import Counter
print('hits by (fn, caller):', Counter((e['fn'], hex(e['lr'] - 4)) for e in log).most_common(12))
def s16(v): v &= 0xffff; return v - 0x10000 if v & 0x8000 else v
print('%d sizing calls logged' % len(log))
for e in log:
    mark = '  <== status view' if e['this'] == status_view else ''
    print('%-30s this=%08x args=(%d, %d, %d) from %08x%s' % (e['fn'], e['this'], s16(e['r4']), s16(e['r5']), e['r6'] & 0xff, e['lr'] - 4, mark))
