"""Write a 32 KiB Apple Partition Map header for wrapping a raw HFS+ volume,
so OpenBIOS (qemu-system-ppc -M mac99) can boot it.
usage: mkapm.py <hfs-volume-bytes> <out-header>"""
import struct, sys
vol_bytes = int(sys.argv[1])
assert vol_bytes % 512 == 0
hdr_blocks = 64
vol_blocks = vol_bytes // 512
total = hdr_blocks + vol_blocks

def entry(nmap, start, count, name, ptype, status):
    e = struct.pack('>2sHIII32s32sIII', b'PM', 0, nmap, start, count,
                    name.encode().ljust(32, b'\0'), ptype.encode().ljust(32, b'\0'),
                    0, count, status)
    return e.ljust(512, b'\0')

ddm = struct.pack('>2sHIHHI', b'ER', 512, total, 1, 1, 0).ljust(512, b'\0')
hdr = ddm + entry(2, 1, hdr_blocks - 1, 'Apple', 'Apple_partition_map', 0x3) \
          + entry(2, hdr_blocks, vol_blocks, 'Panther', 'Apple_HFS', 0x40000033)
open(sys.argv[2], 'wb').write(hdr.ljust(hdr_blocks * 512, b'\0'))
