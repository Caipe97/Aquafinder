"""Minimal 32-bit big-endian (PPC) Mach-O parser for old Panther binaries
that modern Apple tools refuse to read (obsolete load commands)."""
import struct, sys

LC_SEGMENT, LC_SYMTAB, LC_DYSYMTAB = 0x1, 0x2, 0xb
S_NON_LAZY, S_LAZY, S_STUBS = 0x6, 0x7, 0x8

class MachO:
    def __init__(self, path):
        self.data = open(path, 'rb').read()
        d = self.data
        magic, cpu, sub, ftype, ncmds, sz, flags = struct.unpack_from('>7I', d, 0)
        assert magic == 0xfeedface, hex(magic)
        self.segments, self.sections = [], []
        self.symtab = self.dysymtab = None
        off = 28
        for _ in range(ncmds):
            cmd, csz = struct.unpack_from('>2I', d, off)
            if cmd == LC_SEGMENT:
                name = d[off+8:off+24].rstrip(b'\0').decode()
                vmaddr, vmsize, fileoff, filesize, maxp, initp, nsects, fl = struct.unpack_from('>8I', d, off+24)
                self.segments.append(dict(name=name, vmaddr=vmaddr, vmsize=vmsize, fileoff=fileoff, filesize=filesize))
                so = off + 56
                for _ in range(nsects):
                    sect = d[so:so+16].rstrip(b'\0').decode()
                    seg = d[so+16:so+32].rstrip(b'\0').decode()
                    addr, size, offset, align, reloff, nreloc, sflags, r1, r2 = struct.unpack_from('>9I', d, so+32)
                    self.sections.append(dict(sect=sect, seg=seg, addr=addr, size=size, offset=offset,
                                              type=sflags & 0xff, reserved1=r1, reserved2=r2))
                    so += 68
            elif cmd == LC_SYMTAB:
                self.symtab = struct.unpack_from('>4I', d, off+8)
            elif cmd == LC_DYSYMTAB:
                self.dysymtab = struct.unpack_from('>18I', d, off+8)
            off += csz
        self._load_symbols()

    def _load_symbols(self):
        symoff, nsyms, stroff, strsize = self.symtab
        d = self.data
        self.syms = []
        for i in range(nsyms):
            strx, ntype, nsect, ndesc, value = struct.unpack_from('>IBBhI', d, symoff + i*12)
            end = d.index(b'\0', stroff + strx)
            self.syms.append((d[stroff+strx:end].decode('latin1'), ntype, nsect, value))
        indirectsymoff, nindirect = self.dysymtab[12], self.dysymtab[13]
        self.indirect = list(struct.unpack_from('>%dI' % nindirect, d, indirectsymoff))
        # map stub / pointer addresses -> imported symbol name
        self.imports = {}
        for s in self.sections:
            if s['type'] in (S_STUBS, S_LAZY, S_NON_LAZY):
                esize = s['reserved2'] if s['type'] == S_STUBS else 4
                for k in range(s['size'] // esize):
                    idx = self.indirect[s['reserved1'] + k]
                    if idx & 0xc0000000:
                        continue
                    self.imports[s['addr'] + k*esize] = self.syms[idx][0]
        self.local = {}
        for name, ntype, nsect, value in self.syms:
            if (ntype & 0x0e) == 0x0e and value:  # N_SECT
                self.local.setdefault(value, name)

    def off2addr(self, off):
        for s in self.segments:
            if s['fileoff'] <= off < s['fileoff'] + s['filesize']:
                return s['vmaddr'] + off - s['fileoff']
    def addr2off(self, addr):
        for s in self.segments:
            if s['vmaddr'] <= addr < s['vmaddr'] + s['filesize']:
                return s['fileoff'] + addr - s['vmaddr']
    def section(self, sect, seg='__TEXT'):
        for s in self.sections:
            if s['sect'] == sect and s['seg'] == seg:
                return s

if __name__ == '__main__':
    m = MachO(sys.argv[1])
    for s in m.sections:
        print('%-16s %-10s addr=%08x size=%08x off=%08x type=%d' % (s['sect'], s['seg'], s['addr'], s['size'], s['offset'], s['type']))
    print('symbols:', len(m.syms), 'imports:', len(m.imports), 'local:', len(m.local))
