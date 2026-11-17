"""Extract one file from an HFS+ volume inside a QCOW2 (or raw) disk image,
reading only the blocks needed (useful when the image lives on a flaky drive).

usage: qcowhfs.py <disk.qcow2|disk.img> </path/in/volume> <out-file>
"""
import struct, sys, zlib


class Qcow2:
    def __init__(self, path):
        self.f = open(path, 'rb')
        h = self.f.read(104)
        magic, ver = struct.unpack_from('>4sI', h, 0)
        if magic != b'QFI\xfb':
            self.raw = True
            return
        self.raw = False
        self.cluster_bits = struct.unpack_from('>I', h, 20)[0]
        self.size = struct.unpack_from('>Q', h, 24)[0]
        self.l1_size, self.l1_off = struct.unpack_from('>IQ', h, 36)
        self.cs = 1 << self.cluster_bits
        self.l2_bits = self.cluster_bits - 3
        self.f.seek(self.l1_off)
        self.l1 = struct.unpack('>%dQ' % self.l1_size, self.f.read(8 * self.l1_size))
        self.l2cache = {}

    def _cluster(self, vcluster):
        l1i, l2i = vcluster >> self.l2_bits, vcluster & ((1 << self.l2_bits) - 1)
        l2off = self.l1[l1i] & 0x00fffffffffffe00 if l1i < len(self.l1) else 0
        if not l2off:
            return None
        if l2off not in self.l2cache:
            self.f.seek(l2off)
            self.l2cache[l2off] = self.f.read(self.cs)
        e = struct.unpack_from('>Q', self.l2cache[l2off], 8 * l2i)[0]
        if e & (1 << 62):
            raise NotImplementedError('compressed qcow2 clusters')
        if e & 1 and not (e & 0x00fffffffffffe00):
            return None  # zero cluster
        return e & 0x00fffffffffffe00 or None

    def read(self, off, n):
        if self.raw:
            self.f.seek(off)
            return self.f.read(n)
        out = bytearray()
        while n:
            vc, within = off >> self.cluster_bits, off & (self.cs - 1)
            take = min(n, self.cs - within)
            host = self._cluster(vc)
            if host is None:
                out += bytes(take)
            else:
                self.f.seek(host + within)
                out += self.f.read(take)
            off += take
            n -= take
        return bytes(out)


class HFSPlus:
    def __init__(self, disk, part_off):
        self.d, self.base = disk, part_off
        vh = disk.read(part_off + 1024, 512)
        sig = vh[:2]
        if sig == b'BD':   # HFS wrapper with embedded HFS+
            ablk = struct.unpack_from('>I', vh, 20)[0]
            alst = struct.unpack_from('>H', vh, 28)[0]
            emb_start = struct.unpack_from('>H', vh, 0x7e)[0]
            self.base = part_off + alst * 512 + emb_start * ablk
            vh = disk.read(self.base + 1024, 512)
            sig = vh[:2]
        assert sig in (b'H+', b'HX'), 'not HFS+: %r' % sig
        self.bs = struct.unpack_from('>I', vh, 40)[0]
        self.cat_extents = self._extents(vh, 0x110 + 16)
        self.cat_size = struct.unpack_from('>Q', vh, 0x110)[0]
        hdr = self.read_fork(self.cat_extents, 0, 512)
        self.node_size = struct.unpack_from('>H', hdr, 14 + 18)[0]
        self.root = struct.unpack_from('>I', hdr, 14 + 2)[0]

    @staticmethod
    def _extents(buf, off):
        return [struct.unpack_from('>II', buf, off + 8*i) for i in range(8)]

    def read_fork(self, extents, off, n):
        out = bytearray()
        for start, count in extents:
            if not count:
                break
            ext_bytes = count * self.bs
            if off < ext_bytes:
                take = min(n - len(out), ext_bytes - off)
                out += self.d.read(self.base + start * self.bs + off, take)
                off = 0
                if len(out) == n:
                    break
            else:
                off -= ext_bytes
        if len(out) != n:
            raise IOError('fork extents exhausted (file uses the extents overflow file?)')
        return bytes(out)

    def node(self, i):
        return self.read_fork(self.cat_extents, i * self.node_size, self.node_size)

    @staticmethod
    def _key(parent, name):
        return (parent, name.lower())

    def _records(self, nd):
        n = struct.unpack_from('>H', nd, 10)[0]
        offs = [struct.unpack_from('>H', nd, self.node_size - 2*(k+1))[0] for k in range(n)]
        for o in offs:
            klen = struct.unpack_from('>H', nd, o)[0]
            parent = struct.unpack_from('>I', nd, o + 2)[0]
            nlen = struct.unpack_from('>H', nd, o + 6)[0]
            name = nd[o+8:o+8+2*nlen].decode('utf-16-be')
            yield (parent, name), nd, o + 2 + klen

    def lookup(self, parent, name):
        target = self._key(parent, name)
        i = self.root
        while True:
            nd = self.node(i)
            kind = struct.unpack_from('>b', nd, 8)[0]
            if kind == 0:   # index node: follow last child whose key <= target
                child = None
                for (p, nm), buf, ro in self._records(nd):
                    if self._key(p, nm) <= target:
                        child = struct.unpack_from('>I', buf, ro)[0]
                    else:
                        break
                if child is None:
                    return None
                i = child
            elif kind == -1:   # leaf
                for (p, nm), buf, ro in self._records(nd):
                    if self._key(p, nm) == target:
                        return buf[ro:]
                return None
            else:
                raise ValueError('unexpected node kind %d' % kind)

    def open(self, path):
        cnid = 2
        parts = [p for p in path.split('/') if p]
        for k, comp in enumerate(parts):
            rec = self.lookup(cnid, comp)
            if rec is None:
                raise FileNotFoundError(path + ' (at %r)' % comp)
            rtype = struct.unpack_from('>h', rec, 0)[0]
            if rtype == 1:      # folder
                cnid = struct.unpack_from('>I', rec, 8)[0]
            elif rtype == 2:    # file
                assert k == len(parts) - 1, 'file in the middle of a path'
                size = struct.unpack_from('>Q', rec, 88)[0]
                return self.read_fork(self._extents(rec, 88 + 16), 0, size)
            else:
                raise ValueError('record type %d' % rtype)
        raise IsADirectoryError(path)


def find_hfs_partition(disk):
    blk0 = disk.read(0, 512)
    if blk0[:2] != b'ER':
        return 0
    n = struct.unpack_from('>I', disk.read(512, 512), 4)[0]
    for k in range(1, n + 1):
        e = disk.read(512 * k, 512)
        start, count = struct.unpack_from('>II', e, 8)
        ptype = e[48:80].rstrip(b'\0')
        if ptype == b'Apple_HFS':
            return start * 512
    raise ValueError('no Apple_HFS partition')


if __name__ == '__main__':
    disk = Qcow2(sys.argv[1])
    fs = HFSPlus(disk, find_hfs_partition(disk))
    data = fs.open(sys.argv[2])
    open(sys.argv[3], 'wb').write(data)
    print('%s: %d bytes' % (sys.argv[2], len(data)))
