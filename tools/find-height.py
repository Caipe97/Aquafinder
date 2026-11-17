"""Find which field of the status bar view holds its height, then catch the
code that writes it when a new window's status view is created."""
import sys, os, struct, time
sys.path.insert(0, os.path.dirname(__file__))
from gdbrsp import GDB

CAVE, SIG = 0x29ff10, 0x801f0120
CTOR_RET = int(sys.argv[1], 16)      # address right after 'bl <status view ctor>'
g = GDB()

def finder_stop(addrs, timeout):
    """Continue until one of addrs is hit inside the Finder; returns regs."""
    for a in addrs: g.bp(a)
    last, end = None, time.time() + timeout
    try:
        while time.time() < end:
            if last is not None: g.resume_from(last, set(addrs))
            if g.cont(timeout=max(1, end - time.time())) is None:
                g.interrupt(); return None
            r = g.regs(); last = r['pc']
            if g.word(CAVE) == SIG and r['pc'] in addrs:
                return r
    finally:
        for a in addrs: g.bp(a, on=False)

# 1. status view of an existing window: dump it
r = finder_stop([CAVE], 60)
view = r['r'][31]; rect = struct.unpack('>4h', g.mem(r['r'][30], 8))
h = rect[2] - rect[0]
print('status view %08x paint rect %s (height %d)' % (view, rect, h))
obj = g.mem(view, 0x200)
cands = [o for o in range(0, 0x1fe, 2) if struct.unpack_from('>h', obj, o)[0] == h]
print('int16 fields == %d at offsets: %s' % (h, [hex(o) for o in cands]))
open(os.path.join(os.path.dirname(__file__), '..', 'build', 'statusview-dump.bin'), 'wb').write(obj)
g.cont(timeout=0.5); g.interrupt()
print('READY', flush=True)

# 2. next window: catch the new status view right after construction,
#    then watch writes to each candidate field
r = finder_stop([CTOR_RET], 120)
if r is None:
    print('no new status view seen'); sys.exit(1)
nv = r['r'][31]
print('new status view %08x' % nv, flush=True)
for o in cands:
    assert g.cmd('Z2,%x,2' % (nv + o)) == 'OK'
hits = []
end = time.time() + 60
while time.time() < end and len(hits) < 12:
    if g.cont(timeout=max(1, end - time.time())) is None:
        g.interrupt(); break
    rr = g.regs()
    val = [struct.unpack('>h', g.mem(nv + o, 2))[0] for o in cands]
    hits.append((rr['pc'], rr['lr'], val))
    print('write: pc=%08x lr=%08x fields=%s' % (rr['pc'], rr['lr'], val), flush=True)
for o in cands:
    g.cmd('z2,%x,2' % (nv + o))
g.cont(timeout=0.5)
