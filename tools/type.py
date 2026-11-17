"""Type text into the QEMU guest via QMP send-key. usage: type.py 'text' [--enter]"""
import json, socket, sys, time, os
if os.environ.get('QMPPORT'):    # TCP QMP (ppcosx run --monitor uses 4445)
    sock = socket.create_connection(('127.0.0.1', int(os.environ['QMPPORT'])))
else:
    sock = socket.socket(socket.AF_UNIX)
    sock.connect(os.path.join(os.path.dirname(__file__), '..', 'vm', os.environ.get('SOCK','qemu') + '-qmp.sock'))
f = sock.makefile('rw'); f.readline()
def cmd(c, **a):
    f.write(json.dumps({'execute': c, 'arguments': a}) + '\n'); f.flush()
    while True:
        r = json.loads(f.readline())
        if 'return' in r or 'error' in r: return r
cmd('qmp_capabilities')
PLAIN = {' ': 'spc', '/': 'slash', '.': 'dot', '-': 'minus', '=': 'equal', ',': 'comma',
         ';': 'semicolon', "'": 'apostrophe', '[': 'bracket_left', ']': 'bracket_right',
         '\\': 'backslash', '`': 'grave_accent', '\n': 'ret'}
SHIFT = {'_': 'minus', '+': 'equal', ':': 'semicolon', '"': 'apostrophe', '<': 'comma', '>': 'dot',
         '?': 'slash', '|': 'backslash', '~': 'grave_accent', '{': 'bracket_left', '}': 'bracket_right',
         '!': '1', '@': '2', '#': '3', '$': '4', '%': '5', '^': '6', '&': '7', '*': '8', '(': '9', ')': '0'}
def key(*names):
    cmd('send-key', keys=[{'type': 'qcode', 'data': n} for n in names], **{'hold-time': 40})
    time.sleep(0.06)
text = sys.argv[1] + ('\n' if '--enter' in sys.argv else '')
for ch in text:
    if ch.isalpha() and ch.isupper(): key('shift', ch.lower())
    elif ch.isalnum(): key(ch)
    elif ch in PLAIN: key(PLAIN[ch])
    elif ch in SHIFT: key('shift', SHIFT[ch])
    else: raise SystemExit('cannot type %r' % ch)
