"""Transplant Appearance theme artwork (pxm# resources) from one Extras.rsrc
into another, e.g. Jaguar's pinstriped title bars into Panther.

usage: theme.py <panther Extras.rsrc> <jaguar Extras.rsrc> <out Extras.rsrc> id[,id...]
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from rsrc import ResFile
import pxm


def transplant(dst_path, src_path, out_path, ids, preview_dir=None):
    dst = ResFile(open(dst_path, 'rb').read())
    src = ResFile(open(src_path, 'rb').read())
    changes = {}
    for i in ids:
        key = ('pxm#', i)
        if key not in src.res:
            sys.exit('pxm# %d missing in %s' % (i, src_path))
        a, b = dst.res.get(key), src.res[key]
        ha, hb = (pxm.header(a['data']) if a else None), pxm.header(b['data'])
        print('pxm# %5d %-38s %s -> %s' % (i, (b['name'] or '')[:38],
              ha and '%dx%d n%d' % (ha['w'], ha['h'], ha['count']),
              '%dx%d n%d' % (hb['w'], hb['h'], hb['count'])))
        if preview_dir:
            for tag, r in (('before', a), ('after', b)):
                if r and pxm.header(r['data'])['depth'] == 32:
                    pxm.sheet(pxm.visible(*pxm.decode(r['data']))).save(
                        os.path.join(preview_dir, '%d-%s.png' % (i, tag)))
        new = dict(b)
        if a:   # keep Panther's name/attributes, take Jaguar's pixels
            new['name'], new['attrs'] = a['name'], a['attrs']
        if a and ha['count'] != hb['count']:
            # Re-encode into Panther's layout, mapping each Panther state to a
            # Jaguar state (extra Panther states reuse Jaguar's state 0, active).
            assert (ha['w'], ha['h']) == (hb['w'], hb['h']), 'size differs'
            ims, ms = pxm.decode(b['data'])
            pick = [k if k < hb['count'] else 0 for k in range(ha['count'])]
            _, pms = pxm.decode(a['data'])
            masks = [ms[min(k, len(ms)-1)] for k in pick][:len(pms)]
            new['data'] = pxm.encode(a['data'], [ims[k] for k in pick], masks)
            print('          states remapped Panther<-Jaguar: %s' % pick)
        changes[key] = new['data']
    out = dst.patched_in_place(changes)
    check = ResFile(out)
    for key, data in changes.items():
        assert check.res[key]['data'] == data
    open(out_path, 'wb').write(out)


if __name__ == '__main__':
    transplant(sys.argv[1], sys.argv[2], sys.argv[3],
               [int(x) for x in sys.argv[4].split(',')],
               preview_dir=os.environ.get('PREVIEW_DIR'))


def shrink_frames(in_path, out_path, res_id, size, offset):
    """Resample every frame of pxm# res_id to size x size, placed at
    (offset, offset) inside its unchanged canvas (rest transparent).
    Pixels are premultiplied RGBA; resampling premultiplied values is correct."""
    from PIL import Image
    rf = ResFile(open(in_path, 'rb').read())
    key = ('pxm#', res_id)
    d = rf.res[key]['data']
    ims, ms = pxm.decode(d)
    out = []
    for im in ims:
        small = im.resize((size, size), Image.LANCZOS)
        c = Image.new('RGBA', im.size, (0, 0, 0, 0))
        c.paste(small, (offset, offset))
        out.append(c)
    new = pxm.encode(d, out, ms)
    data = rf.patched_in_place({key: new})
    assert ResFile(data).res[key]['data'] == new
    open(out_path, 'wb').write(data)
