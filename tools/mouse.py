"""Drive the QEMU usb-tablet via QMP with screen-pixel coordinates (800x600).
usage: mouse.py move X Y | click X Y | drag X1 Y1 X2 Y2"""
import json, socket, sys, time, os
W, H = map(int, os.environ.get('VMRES', '800x600').split('x'))
if os.environ.get('QMPPORT'):    # TCP QMP (ppcosx run --monitor uses 4445)
    sock = socket.create_connection(('127.0.0.1', int(os.environ['QMPPORT'])))
else:
    sock = socket.socket(socket.AF_UNIX)
    sock.connect(os.path.join(os.path.dirname(__file__), '..', 'vm', os.environ.get('SOCK','qemu') + '-qmp.sock'))
f = sock.makefile('rw')
f.readline()
def cmd(c, **a):
    f.write(json.dumps({'execute': c, 'arguments': a} if a else {'execute': c}) + '\n'); f.flush()
    while True:
        r = json.loads(f.readline())
        if 'return' in r or 'error' in r:
            return r
cmd('qmp_capabilities')
def move(x, y):
    cmd('input-send-event', events=[
        {'type': 'abs', 'data': {'axis': 'x', 'value': int(x * 32767 / (W - 1))}},
        {'type': 'abs', 'data': {'axis': 'y', 'value': int(y * 32767 / (H - 1))}}])
def btn(down):
    cmd('input-send-event', events=[{'type': 'btn', 'data': {'down': down, 'button': 'left'}}])
a = sys.argv[1]; n = list(map(int, sys.argv[2:]))
if a == 'move': move(*n)
elif a == 'click': move(*n); time.sleep(0.2); btn(True); time.sleep(0.1); btn(False)
elif a == 'drag':
    x1, y1, x2, y2 = n
    move(x1, y1); time.sleep(0.3); btn(True); time.sleep(0.3)
    for i in range(1, 11):
        move(x1 + (x2 - x1) * i / 10, y1 + (y2 - y1) * i / 10); time.sleep(0.1)
    time.sleep(0.3); btn(False)
if a == 'dblclick':
    move(*n); time.sleep(0.2)
    for _ in range(2):
        btn(True); time.sleep(0.05); btn(False); time.sleep(0.08)
if a == 'press':     # press X Y: move there and hold the button
    move(*n); time.sleep(0.3); btn(True)
if a == 'release':   # release X Y: move there and let go
    move(*n); time.sleep(0.3); btn(False)
if a == 'moveto':    # moveto X1 Y1 X2 Y2 [steps]: glide while (maybe) holding
    x1, y1, x2, y2 = n[:4]; st = n[4] if len(n) > 4 else 10
    for i in range(1, st + 1):
        move(x1 + (x2 - x1) * i / st, y1 + (y2 - y1) * i / st); time.sleep(0.08)
