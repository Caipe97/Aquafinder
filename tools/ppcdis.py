"""Disassemble PPC Finder with capstone, resolving bl targets to import names."""
import sys, struct
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from macho import MachO
import capstone

cs = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_32 | capstone.CS_MODE_BIG_ENDIAN)

class Dis:
    def __init__(self, path):
        self.m = MachO(path)
        self.text = [s for s in self.m.sections if s['seg'] == '__TEXT' and s['sect'] in ('__text', '__textcoal_nt', '__StaticInit')]
        self.stubname = {}
        for s in self.m.sections:
            if s['type'] == 8:
                for a, n in self.m.imports.items():
                    if s['addr'] <= a < s['addr'] + s['size']:
                        self.stubname[a] = n
    def word(self, addr):
        return struct.unpack_from('>I', self.m.data, self.m.addr2off(addr))[0]
    def insn(self, addr):
        off = self.m.addr2off(addr)
        for i in cs.disasm(self.m.data[off:off+4], addr):
            return i
    def fmt(self, addr):
        i = self.insn(addr)
        if i is None:
            return '%08x: .long 0x%08x' % (addr, self.word(addr))
        s = '%08x: %08x  %-8s %s' % (addr, self.word(addr), i.mnemonic, i.op_str)
        if i.mnemonic in ('bl', 'b', 'bla') :
            t = int(i.op_str, 16)
            s += '   ; ' + self.stubname.get(t, self.m.local.get(t, 'sub_%x' % t))
        return s
    def calls_to(self, name):
        """Yield addresses of bl instructions targeting the stub for `name`."""
        targets = {a for a, n in self.stubname.items() if n == name}
        for s in self.text:
            base = s['addr']
            for k in range(0, s['size'], 4):
                w = struct.unpack_from('>I', self.m.data, s['offset'] + k)[0]
                if (w & 0xfc000003) == 0x48000001:
                    disp = w & 0x03fffffc
                    if disp & 0x02000000:
                        disp -= 0x04000000
                    if base + k + disp in targets:
                        yield base + k
    def bl_target(self, addr):
        w = self.word(addr)
        disp = w & 0x03fffffc
        if disp & 0x02000000: disp -= 0x04000000
        return addr + disp
    def func_start(self, addr):
        """Walk back to a likely prologue (mflr r0) or blr of previous function."""
        a = addr
        while a > addr - 0x4000:
            a -= 4
            w = self.word(a)
            if w == 0x7c0802a6:  # mflr r0
                return a
            if w == 0x4e800020:  # blr
                return a + 4
        return addr - 0x40
    def dump(self, start, end):
        for a in range(start, end, 4):
            print(self.fmt(a))

if __name__ == '__main__':
    d = Dis(sys.argv[1])
    for name in sys.argv[2:]:
        print('==', name)
        for a in d.calls_to(name):
            print('   call at %08x (func ~%08x)' % (a, d.func_start(a)))
