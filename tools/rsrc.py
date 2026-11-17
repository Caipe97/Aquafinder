"""Classic Mac resource file (data-fork .rsrc) reader/writer."""
import struct, sys
from collections import OrderedDict

class ResFile:
    def __init__(self, data):
        self.raw = data
        doff, moff, dlen, mlen = struct.unpack_from('>4I', data, 0)
        m = data[moff:moff+mlen]
        self.attrs = struct.unpack_from('>H', m, 22)[0]
        tl_off, nl_off = struct.unpack_from('>HH', m, 24)
        ntypes = struct.unpack_from('>h', m, tl_off)[0] + 1
        self.res = OrderedDict()   # (type, id) -> dict(name, attrs, data)
        for t in range(ntypes):
            rtype, cnt, ref_off = struct.unpack_from('>4sHH', m, tl_off + 2 + 8*t)
            for r in range(cnt + 1):
                rid, name_off, a_and_off, _ = struct.unpack_from('>hhII', m, tl_off + ref_off + 12*r)
                attrs, roff = a_and_off >> 24, a_and_off & 0xffffff
                name = None
                if name_off != -1:
                    nlen = m[nl_off + name_off]
                    name = m[nl_off+name_off+1:nl_off+name_off+1+nlen].decode('mac_roman')
                dl = struct.unpack_from('>I', data, doff + roff)[0]
                self.res[(rtype.decode('mac_roman'), rid)] = dict(
                    name=name, attrs=attrs, data=data[doff+roff+4:doff+roff+4+dl],
                    offset=doff+roff+4)

    def patched_in_place(self, changes):
        """Return the original file bytes with same-length resource data
        replaced in place. changes: {(type, id): new_bytes}"""
        out = bytearray(self.raw)
        for key, new in changes.items():
            r = self.res[key]
            assert len(new) == len(r['data']), '%s %d changes size' % key
            out[r['offset']:r['offset'] + len(new)] = new
        return bytes(out)

    def with_added(self, rtype, rid, name, new):
        """Return the file bytes with a new resource appended: its data goes
        at the end of the data section, so every existing resource keeps its
        offset and only the header and the map (rebuilt after it) change."""
        assert (rtype, rid) not in self.res, '%s %d exists' % (rtype, rid)
        doff = struct.unpack_from('>I', self.raw, 0)[0]
        moff, dlen = struct.unpack_from('>I', self.raw, 4)[0], struct.unpack_from('>I', self.raw, 8)[0]
        assert doff + dlen <= moff
        data_end = doff + dlen
        items = [(k, dict(r, roff=r['offset'] - 4 - doff)) for k, r in self.res.items()]
        items.append(((rtype, rid), dict(name=name, attrs=0, roff=dlen)))
        bytypes = OrderedDict()
        for (t, i), r in items: bytypes.setdefault(t, []).append((i, r))
        names = bytearray(); reflists = []
        for t, its in bytypes.items():
            refs = []
            for i, r in its:
                if r['name'] is not None:
                    noff = len(names); nb = r['name'].encode('mac_roman')
                    names += bytes([len(nb)]) + nb
                else:
                    noff = -1
                refs.append(struct.pack('>hhII', i, noff, (r['attrs'] << 24) | r['roff'], 0))
            reflists.append((t, refs))
        tl = bytearray(struct.pack('>h', len(reflists) - 1))
        refblob = bytearray(); ref_base = 2 + 8 * len(reflists)
        for t, refs in reflists:
            tl += struct.pack('>4sHH', t.encode('mac_roman'), len(refs) - 1, ref_base + len(refblob))
            for r in refs: refblob += r
        body = self.raw[:data_end] + struct.pack('>I', len(new)) + new
        mapb = bytearray(28) + tl + refblob + names
        struct.pack_into('>HHH', mapb, 22, self.attrs, 28, 28 + len(tl) + len(refblob))
        hdr = struct.pack('>4I', doff, len(body), dlen + 4 + len(new), len(mapb))
        struct.pack_into('>4I', mapb, 0, *struct.unpack('>4I', hdr))
        return hdr + body[16:] + bytes(mapb)

    def types(self):
        out = OrderedDict()
        for (t, i) in self.res: out.setdefault(t, []).append(i)
        return out

    def build(self):
        bytypes = OrderedDict()
        for (t, i), r in self.res.items(): bytypes.setdefault(t, []).append((i, r))
        data = bytearray(); names = bytearray(); reflists = []
        for t, items in bytypes.items():
            refs = []
            for i, r in items:
                roff = len(data)
                data += struct.pack('>I', len(r['data'])) + r['data']
                if r['name'] is not None:
                    noff = len(names); nb = r['name'].encode('mac_roman')
                    names += bytes([len(nb)]) + nb
                else:
                    noff = -1
                refs.append(struct.pack('>hhII', i, noff, (r['attrs'] << 24) | roff, 0))
            reflists.append((t, refs))
        ntypes = len(reflists)
        tl = bytearray(struct.pack('>h', ntypes - 1))
        refblob = bytearray(); ref_base = 2 + 8 * ntypes
        for t, refs in reflists:
            tl += struct.pack('>4sHH', t.encode('mac_roman'), len(refs) - 1, ref_base + len(refblob))
            for r in refs: refblob += r
        typelist = tl + refblob
        doff = 256
        mhdr = bytearray(28)
        struct.pack_into('>HHH', mhdr, 22, self.attrs, 28, 28 + len(typelist))
        mapb = mhdr + typelist + names
        moff = doff + len(data)
        hdr = struct.pack('>4I', doff, moff, len(data), len(mapb)).ljust(256, b'\0')
        struct.pack_into('>4I', mapb, 0, doff, moff, len(data), len(mapb))
        return bytes(hdr) + bytes(data) + bytes(mapb)

if __name__ == '__main__':
    rf = ResFile(open(sys.argv[1], 'rb').read())
    for t, ids in rf.types().items():
        print('%-5s %4d  ids %s%s' % (t, len(ids), ids[:12], ' ...' if len(ids) > 12 else ''))
