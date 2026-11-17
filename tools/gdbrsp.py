"""Minimal GDB remote-serial-protocol client for QEMU's gdbstub (ppc32).

Start QEMU with `-s` (gdbstub on tcp:1234). Breakpoints and memory reads use
guest virtual addresses of whichever process is running when the CPU stops.
"""
import socket, struct, time


class GDB:
    def __init__(self, host='127.0.0.1', port=1234):
        self.s = socket.create_connection((host, port))
        self.s.settimeout(None)
        self.buf = b''
        self.cmd('qSupported')
        self.stop = self.cmd('?')      # QEMU halts the guest when gdb attaches
        try:                           # drain anything left over from an earlier session
            while True:
                self._recv(0.5)
        except (socket.timeout, TimeoutError):
            pass

    # --- packet layer
    def _send(self, data):
        pkt = b'$' + data.encode() + b'#' + ('%02x' % (sum(data.encode()) & 0xff)).encode()
        self.s.sendall(pkt)

    def _recv(self, timeout=None):
        self.s.settimeout(timeout)
        try:
            while True:
                i = self.buf.find(b'$')
                j = self.buf.find(b'#', i + 1) if i >= 0 else -1
                if i >= 0 and j >= 0 and len(self.buf) >= j + 3:
                    data = self.buf[i + 1:j]
                    self.buf = self.buf[j + 3:]
                    self.s.sendall(b'+')
                    return data.decode()
                chunk = self.s.recv(65536)
                if not chunk:
                    raise EOFError
                self.buf += chunk
                k = self.buf.find(b'$')          # drop acks/noise before a packet
                self.buf = self.buf[k:] if k >= 0 else b''
        finally:
            self.s.settimeout(None)

    def cmd(self, data, timeout=10):
        self._send(data)
        return self._recv(timeout)

    # --- target control
    def interrupt(self):
        self.s.sendall(b'\x03')
        return self._recv(10)

    def cont(self, timeout=None):
        """Continue; returns the stop reply, or None on timeout."""
        self._send('c')
        try:
            return self._recv(timeout)
        except socket.timeout:
            return None

    def step(self):
        self._send('s')
        r = self._recv(10)
        while not (r.startswith('T') or r.startswith('S')):
            r = self._recv(10)
        return r

    def resume_from(self, pc, armed):
        """Continue from a breakpoint at pc without re-hitting it."""
        if pc in armed:
            self.bp(pc, on=False)
            self.step()
            self.bp(pc)

    def bp(self, addr, on=True):
        r = self.cmd('%s0,%x,4' % ('Z' if on else 'z', addr))
        while r.startswith('T') or r.startswith('S'):   # stale stop reply
            r = self._recv(10)
        assert r == 'OK', 'breakpoint %x: %r' % (addr, r)

    def regs(self):
        h = self.cmd('g')
        b = bytes.fromhex(h)
        gpr = list(struct.unpack('>32I', b[:128]))
        base = 384 if len(b) >= 408 else 128    # with or without the 32 FPRs
        pc, msr, cr, lr, ctr, xer = struct.unpack('>6I', b[base:base + 24])
        return dict(r=gpr, pc=pc, lr=lr, cr=cr, ctr=ctr)

    def mem(self, addr, n):
        h = self.cmd('m%x,%x' % (addr, n))
        if h.startswith('E'):
            return None
        return bytes.fromhex(h)

    def word(self, addr):
        b = self.mem(addr, 4)
        return struct.unpack('>I', b)[0] if b and len(b) == 4 else None
