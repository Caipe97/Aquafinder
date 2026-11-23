"""Generate dist/aquafinder.sh: a self-contained shell script for Mac OS X
10.3.9 (Panther) and 10.4.11 (Tiger) that installs/restores independent
components (files are recognised by fingerprint, so one script serves both):

  finder     Aqua (non-brushed-metal) Finder windows with toolbar + sidebar,
             the status bar under the toolbar and the toolbar buttons (Jaguar)
  stripes    sidebar styles of finder, one at a time (none: the plain sidebar):
  header     pinstriped with a slim, shadowed divider ('stripes'), under an
  well       Aqua list header ('header'), or an inset list on pinstripes
             ('well'); patch.py's style sets, on Panther also grip.py's
             images for each
  titlebars  Jaguar's pinstriped, translucent title bars (theme Extras.rsrc,
             plus AppKit so Cocoa windows can show the translucency)
  logo       Jaguar branding: the Garamond "Mac OS X" wordmark in About This
             Mac and the login panel, and Jaguar's Finder icon (Finder + Dock)
"""
import sys, hashlib, os
sys.path.insert(0, os.path.dirname(__file__))
import patch, theme, appkit_patch, logo, grip, toolbar

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FINDER_PATH = '/System/Library/CoreServices/Finder.app/Contents/MacOS/Finder'
THEME_PATH = ('/System/Library/Frameworks/Carbon.framework/Versions/A/Frameworks/'
              'HIToolbox.framework/Versions/A/Resources/Extras.rsrc')
APPKIT_PATH = '/System/Library/Frameworks/AppKit.framework/Versions/C/AppKit'
GRIP_PATH = '/System/Library/CoreServices/Finder.app/Contents/Resources/Finder.rsrc'
GRIP_SRC = 'orig/Finder.rsrc'                        # 10.3.9 (same as 10.3.4's)
TIGER_GRIP_SRC = 'orig/tiger-10.4.11/Finder.rsrc'    # 10.4.11 (8S165)
FINDER_BUILDS = [('10.3.9', 'orig/Finder-10.3.9'),
                 ('10.4.11', 'orig/tiger-10.4.11/Finder')]   # 8S165
APPKIT_SRC = 'orig/appkit/AppKit-10.3.9'             # stock, from the 10.3.9 Combo
THEME_SRC = 'theme/panther-10.3.9/Extras.rsrc'      # unchanged since 10.3.0 (the Combo doesn't ship it)
TIGER_APPKIT_SRC = 'orig/tiger-10.4.11/AppKit'       # stock 10.4.11 (8S165)
TIGER_THEME_SRC = 'theme/tiger-10.4.11/Extras.rsrc'  # stock 10.4.11 (from the 10.4.11 Combo)
JAGUAR_SRC = 'theme/jaguar/Extras.rsrc'              # from Mac OS X 10.2.8
CS = '/System/Library/CoreServices/'
LOGO_FILES = [   # (key, label, installed path, Panther original in orig/logo)
    ('about', 'About This Mac logo', CS + 'loginwindow.app/Contents/Resources/MacOSX.tif', 'panther-MacOSX.tif'),
    ('loginart', 'login panel logo', CS + 'SecurityAgent.app/Contents/Resources/MacOSXart.tif', 'panther-MacOSXart.tif'),
    ('loginart', 'login panel logo', CS + 'SecurityAgentPlugins/loginwindow.bundle/Contents/Resources/MacOSXart.tif', 'panther-MacOSXart.tif'),
    ('findericon', 'Finder icon', CS + 'Finder.app/Contents/Resources/Finder.icns', 'panther-Finder.icns'),
    ('findericon', 'Finder icon', CS + 'SystemIcons.bundle/Contents/Resources/FinderIcon.icns', 'panther-Finder.icns'),
    ('dockfinder', 'Dock Finder icon', CS + 'Dock.app/Contents/Resources/finder.png', 'panther-dock-finder.png'),
    # Tiger 10.4.11: the login panel art is MacOSX.tif (Myriad, 140x24), and
    # the system Finder icon moved to CoreTypes.bundle (Panther's bytes).
    # Neither path exists on Panther, nor Panther's MacOSXart.tif / SystemIcons
    # copies on Tiger: the script skips files that aren't there.
    ('loginarttiger', 'login panel logo', CS + 'SecurityAgent.app/Contents/Resources/MacOSX.tif', 'tiger-login-MacOSX.tif'),
    ('loginarttiger', 'login panel logo', CS + 'SecurityAgentPlugins/loginwindow.bundle/Contents/Resources/MacOSX.tif', 'tiger-login-MacOSX.tif'),
    ('findericon', 'Finder icon', CS + 'CoreTypes.bundle/Contents/Resources/FinderIcon.icns', 'panther-Finder.icns'),
]
THEME_IDS = [2004, 2005, 2267, 4330]                 # title bar caps/stretch, modal caps, toolbar bg


def md5(b):
    return hashlib.md5(b).hexdigest()


def runs(a, b, gap=16):
    d = [i for i in range(len(a)) if a[i] != b[i]]
    out, s, p = [], d[0], d[0]
    for i in d[1:]:
        if i - p > gap:
            out.append((s, p)); s = i
        p = i
    out.append((s, p))
    return [(s, b[s:e+1]) for s, e in out]


def put_lines(runs_):
    lines = []
    for off, chunk in runs_:
        for k in range(0, len(chunk), 1024):   # keep each printf argument modest
            part = chunk[k:k+1024]
            lines.append("    put %d %d '%s'" % (off + k, len(part), ''.join('\\%03o' % c for c in part)))
    return lines


def edit_lines(a, b):
    if len(b) > len(a):
        # a grown file that keeps its bytes' places (a resource appended to
        # Finder.rsrc): edit the common part, then write the rest past its
        # end (put's dd extends the copy)
        head = runs(a, b[:len(a)]) if a != b[:len(a)] else []
        if sum(len(c) for _, c in head) < len(a) // 4:
            return '\n'.join(put_lines(head + [(len(a), b[len(a):])]))
    if len(a) != len(b):   # a different-sized file: truncate the copy and write all of it
        return '    : > "$TMP"\n' + '\n'.join(put_lines([(0, b)]))
    return '\n'.join(put_lines(runs(a, b)))


from macho import MachO

def text_region(path, a, b, outside=()):
    """4 KiB-aligned block span covering __TEXT from its first section on.
    update_prebinding rewrites the header/load commands and __DATA pointers
    but never the code, so this identifies a Finder build however often it
    has been re-prebound -- and it covers the bar routine that lives in
    __TEXT's tail padding. It starts at the first whole block after the
    first section's start, not after the load commands: re-prebinding
    against newer dylibs (QuickTime 7.5 pulls in Accelerate, AudioToolbox...)
    appends LC_PREBOUND_DYLIB commands that grow into the zero padding before
    the code, and the block holding the code's start can share bytes with
    the header."""
    m = MachO(path)
    seg = [x for x in m.segments if x['name'] == '__TEXT'][0]
    first = min(s['offset'] for s in m.sections if s['seg'] == '__TEXT' and s['offset'])
    skip = -(-first // 4096)
    count = (seg['fileoff'] + seg['filesize']) // 4096 - skip
    lo, hi = skip * 4096, (skip + count) * 4096
    for off, chunk in runs(a, b):
        if lo <= off and off + len(chunk) <= hi:
            continue
        # only the edits patch.stripes_outside_text names may lie outside (they
        # sit at the same offsets in every 10.3.9 copy; not verified by WANT)
        assert any(o <= off and off + len(chunk) <= o + n for o, n in outside), 'patch outside identification region'
    return skip, count, md5(a[lo:hi]), md5(b[lo:hi])

entries = []   # (component, key, label, skip, count, orig md5, patched md5, edit lines)
# The Finder and its resources come in sidebar styles: plain (the default),
# and patch.STYLE_SET_NAMES' (STYLES). All styles of a file share its key (so
# one backup); a style's edits are listed under <key><style>. styled:
# (component, key, label, skip, count, orig, {style: md5}), style None for
# plain; a style missing from the dict has no build of that file (plain
# stands in); styles may share a fingerprint (Tiger's Finder.rsrc).
assert patch.STRIPES_WIDTH == grip.STRIPES_WIDTH
STYLES = patch.STYLE_SET_NAMES
STYLE_LABELS = {'stripes': 'pinstriped sidebar', 'header': 'sidebar header', 'well': 'inset sidebar'}
STYLE_BUILDS = ('10.3.9', '10.4.11')
styled = []
for ver, rel in FINDER_BUILDS:
    src = os.path.join(ROOT, rel)
    key, lbl = 'finder' + ver.replace('.', ''), 'Finder ' + ver
    a = open(src, 'rb').read()
    out = os.path.join(ROOT, 'build', 'Finder-%s-slim' % ver)
    patch.apply(src, out, quiet=True)
    b = open(out, 'rb').read()
    skip, count, mo, mp = text_region(src, a, b)
    entries.append(('finder', key, lbl, skip, count, mo, mp, edit_lines(a, b)))
    hashes = {None: mp}
    if ver in STYLE_BUILDS:
        for st in STYLES:
            out = os.path.join(ROOT, 'build', 'Finder-%s-%s' % (ver, st))
            patch.apply(src, out, patch.SET_NAMES + [st], quiet=True)
            b = open(out, 'rb').read()
            outside = patch.stripes_outside_text(MachO(src)) if st == 'stripes' else []
            sk2, cn2, mo2, ms = text_region(src, a, b, outside)
            assert (sk2, cn2, mo2) == (skip, count, mo)
            entries.append(('finder', key + st, '%s, %s' % (lbl, STYLE_LABELS[st]), skip, count, mo, ms, edit_lines(a, b)))
            hashes[st] = ms
    styled.append(('finder', key, lbl, skip, count, mo, hashes))

# The Finder's resources: on Panther the sidebar divider's image (the column
# view's divider instead of the metal dimple, or a style's), the sidebar
# header's images ('header'), and Jaguar's toolbar buttons (installed and
# restored with the Finder).
a = open(os.path.join(ROOT, GRIP_SRC), 'rb').read()
b = grip.build(a)
entries.append(('grip', 'finderrsrc', 'Finder images', 0, 0, md5(a), md5(b), edit_lines(a, b)))
hashes = {None: md5(b)}
for st in STYLES:
    c = grip.build(a, st)
    entries.append(('grip', 'finderrsrc' + st, 'Finder images, ' + STYLE_LABELS[st], 0, 0, md5(a), md5(c), edit_lines(a, c)))
    hashes[st] = md5(c)
styled.append(('grip', 'finderrsrc', 'Finder images', 0, 0, md5(a), hashes))
# Tiger's: Jaguar's toolbar buttons (toolbar.build_tiger), and for 'header'
# the sidebar header's images (Tiger draws its sidebar dividers in code, so
# the other styles share the plain file)
a = open(os.path.join(ROOT, TIGER_GRIP_SRC), 'rb').read()
b = toolbar.build_tiger(a)
entries.append(('grip', 'finderrsrctiger', 'Finder images 10.4.11', 0, 0, md5(a), md5(b), edit_lines(a, b)))
hashes = {None: md5(b)}
for st in STYLES:
    c = toolbar.build_tiger(a, st)
    if c != b:
        entries.append(('grip', 'finderrsrctiger' + st, 'Finder images 10.4.11, ' + STYLE_LABELS[st], 0, 0, md5(a), md5(c),
                        edit_lines(a, c)))
    hashes[st] = md5(c)
styled.append(('grip', 'finderrsrctiger', 'Finder images 10.4.11', 0, 0, md5(a), hashes))

import contextlib, io
# Tiger's title bar, toolbar and spinner art is Panther's (byte for byte), so
# both themes get the same transplant.
for rel, key, lbl, out in ((THEME_SRC, 'theme', 'Panther theme', 'Extras-jaguarbars.rsrc'),
                           (TIGER_THEME_SRC, 'themetiger', 'Tiger theme', 'Extras-tiger-jaguarbars.rsrc')):
    theme_out = os.path.join(ROOT, 'build', out)
    with contextlib.redirect_stdout(io.StringIO()):
        theme.transplant(os.path.join(ROOT, rel), os.path.join(ROOT, JAGUAR_SRC), theme_out, THEME_IDS)
        # loading spinner art 16 -> 13 px (it was sized for the 15 px bottom bar)
        theme.shrink_frames(theme_out, theme_out, 390, 13, 2)
        # toolbar background brush -> Jaguar's pinstripes, as the toolbar art above
        # (the Finder erases the status bar with it)
        theme.jaguar_toolbar_brush(theme_out, theme_out)
        # Jaguar's close/minimize/zoom buttons in Aqua title bars (Tiger's have
        # more states: theme.EXTRA_STATES)
        theme.jaguar_window_buttons(theme_out, os.path.join(ROOT, JAGUAR_SRC), theme_out)
    a, b = open(os.path.join(ROOT, rel), 'rb').read(), open(theme_out, 'rb').read()
    entries.append(('titlebars', key, lbl, 0, 0, md5(a), md5(b), edit_lines(a, b)))

for rel, ver in ((APPKIT_SRC, '10.3.9'), (TIGER_APPKIT_SRC, '10.4.11')):
    src = os.path.join(ROOT, rel); out = os.path.join(ROOT, 'build', 'AppKit-%s-slim' % ver)
    appkit_patch.apply(src, out, quiet=True)
    a, b = open(src, 'rb').read(), open(out, 'rb').read()
    skip, count, mo, mp = text_region(src, a, b)
    entries.append(('appkit', 'appkit' + ver.replace('.', ''), 'AppKit ' + ver, skip, count, mo, mp, edit_lines(a, b)))

new_logo = logo.build(); seen = set()   # reuses a/b/src below: keep AppKit's entry above
for key, lbl, path, src in LOGO_FILES:
    if key in seen: continue          # two installed copies of one file share an entry
    seen.add(key)
    a, b = open(os.path.join(ROOT, 'orig', 'logo', src), 'rb').read(), new_logo[key]
    entries.append(('logo', key, lbl, 0, 0, md5(a), md5(b), edit_lines(a, b)))

# Every patched fingerprint ever released (tools/released.txt), so the script
# can recognise files patched by an older Aquafinder and upgrade them.
RELEASED = os.path.join(ROOT, 'tools', 'released.txt')
released = []
for line in open(RELEASED):
    if line.strip() and not line.startswith('#'):
        k, sk, cn, h = line.split()
        released.append((k, int(sk), int(cn), h))
for c, key, lbl, skip, count, o, n, e in entries:
    if (key, skip, count, n) not in released:
        released.append((key, skip, count, n))
        with open(RELEASED, 'a') as f:
            f.write('%s %d %d %s\n' % (key, skip, count, n))

def ident_block(comp):
    out = []
    for c, key, lbl, skip, count, o, n, e in entries:
        if c != comp: continue
        out.append('  R=$(region "$1" %d %d)' % (skip, count))
        out.append('  case "$R" in')
        out.append("    %s) KEY=%s; LABEL='%s'; STATE=original; SKIP=%d; COUNT=%d; WANT=%s; ORIG=%s; return ;;" % (o, key, lbl, skip, count, n, o))
        out.append("    %s) KEY=%s; LABEL='%s'; STATE=patched;  SKIP=%d; COUNT=%d; WANT=%s; ORIG=%s; return ;;" % (n, key, lbl, skip, count, n, o))
        for k, sk, cn, h in released:
            if k in (key, key + 'top') and h != n:
                if (sk, cn) != (skip, count):   # an old release hashed a different span
                    out.append('  esac')
                    out.append('  R2=$(region "$1" %d %d)' % (sk, cn))
                    out.append('  case "$R2" in')
                out.append("    %s) KEY=%s; LABEL='%s'; STATE=oldpatch; SKIP=%d; COUNT=%d; WANT=%s; ORIG=%s; return ;;" % (h, key, lbl, skip, count, n, o))
                if (sk, cn) != (skip, count):
                    out.append('  esac')
                    out.append('  case "$R" in')
        out.append('  esac')
    return '\n'.join(out)
def styled_ident(comp):
    """identify_<comp> for a file with sidebar styles: STYLE = the style found
    (plain or one of STYLES; none when the file looks the same in several),
    STATE as usual, R its fingerprint and H_<style> each style's (H_plain
    plain's; empty: no build of that style, plain stands in); then
    style_target picks WANT/EDITKEY for FINDER_STYLE (keep = the style found,
    plain for an original file). A file patched in another style counts as
    oldpatch, so install re-patches it from the backup. Older releases'
    fingerprints (tools/released.txt) are plain, or the style their key ends
    in (the old 'top' status bar option was folded into plain)."""
    out = []
    for c, key, lbl, skip, count, o, hashes in styled:
        if c != comp: continue
        spans = {}   # (skip, count) -> [(md5, style)]
        for k, sk, cn, h in released:
            st = next((x for x in STYLES if k == key + x), 'plain' if k in (key, key + 'top') else None)
            if st and h not in hashes.values():
                spans.setdefault((sk, cn), []).append((h, st))
        out.append('  ' + '; '.join('H_%s=%s' % (st or 'plain', hashes.get(st, '')) for st in [None] + STYLES))
        out.append('  R=$(region "$1" %d %d)' % (skip, count))
        out.append('  case "$R" in')
        out.append('    %s) STATE=original ;;' % o)
        # a fingerprint shared by several styles reports none
        by_hash = {}
        for st in [None] + STYLES:
            if st in hashes:
                by_hash.setdefault(hashes[st], []).append(st or 'plain')
        sty = lambda sts: '; STYLE=%s' % sts[0] if len(sts) == 1 and len(by_hash) > 1 else ''
        for h, sts in by_hash.items():
            out.append('    %s) STATE=patched%s ;;' % (h, sty(sts)))
        sty = lambda st: '; STYLE=%s' % st if len(by_hash) > 1 else ''
        for h, st in spans.pop((skip, count), []):
            out.append('    %s) STATE=oldpatch%s ;;' % (h, sty(st)))
        out.append('  esac')
        for (sk, cn), hs_ in spans.items():   # older releases hashed a different span
            out.append('  [ "$STATE" = unknown ] && case "$(region "$1" %d %d)" in' % (sk, cn))
            for h, st in hs_:
                out.append('    %s) STATE=oldpatch%s ;;' % (h, sty(st)))
            out.append('  esac')
        out.append('  if [ "$STATE" != unknown ]; then')
        out.append("    KEY=%s; LABEL='%s'; SKIP=%d; COUNT=%d; ORIG=%s; style_target; return" % (key, lbl, skip, count, o))
        out.append('  fi')
    return '\n'.join(out)
known_finder = styled_ident('finder')
known_theme, known_appkit = ident_block('titlebars'), ident_block('appkit')
known_logo = ident_block('logo')
known_grip = styled_ident('grip')
logo_paths = ' '.join(p for k, l, p, s in LOGO_FILES)
assert ' ' not in ''.join(p for k, l, p, s in LOGO_FILES), 'LOGO_FILES is word-split in sh'
edits = '\n'.join("  %s)\n%s\n    ;;" % (key, e) for c, key, lbl, sk, cn, o, n, e in entries)

script = r'''#!/bin/sh
# Aquafinder for Mac OS X 10.3.9 (Panther) and 10.4.11 (Tiger).
#
#   finder     Aqua (non-brushed-metal) Finder windows that keep toolbar + sidebar,
#              the status bar under the toolbar as in Jaguar, and a sidebar divider
#              drawn like the column view's, and Jaguar's toolbar buttons (plus
#              the Finder's resources: the divider's image, the buttons)
#   stripes    sidebar styles of finder, one at a time: pinstriped with a slim,
#   header     shadowed divider; under an Aqua list header; or an inset list on
#   well       pinstripes (restore <style> puts the plain sidebar back)
#   titlebars  Jaguar-style pinstriped, translucent window title bars
#              (the HIToolbox theme, plus AppKit so Cocoa windows blend too)
#
#   sh aquafinder.sh status
#   logo       Jaguar branding: Garamond "Mac OS X" in About This Mac and the
#              login panel, and Jaguar's Finder icon in the Finder and Dock
#
#   sudo sh aquafinder.sh install [finder|stripes|header|well|titlebars|logo]   (default: all)
#   sudo sh aquafinder.sh restore [finder|stripes|header|well|titlebars|logo]   (default: all)
#
# install finder (and install all) keeps the Finder's current sidebar style.
#
# Only recognised files are touched (the Finder is identified by its code
# section, so re-prebinding by Software Update doesn't matter). Each is backed up, patched
# on a copy, verified, then swapped in atomically. Generated by
# tools/mkinstaller.py; do not edit by hand.

PATH=/bin:/sbin:/usr/bin:/usr/sbin; export PATH
FINDER="${FINDER:-__FINDER__}"
THEME="${THEME:-__THEME__}"
APPKIT="${APPKIT:-__APPKIT__}"
GRIP="${GRIP:-__GRIP__}"
BACKUP_DIR="${BACKUP_DIR:-/Library/Aquafinder}"
OLD_BACKUP_DIR=/Library/PantherSlim   # backups made under the old name

die() { echo "aquafinder: $*" >&2; [ -n "$TMP" ] && rm -f "$TMP"; exit 1; }
sum() { md5 < "$1" | awk '{print $NF}'; }

put() {   # put <offset> <count> <bytes as \ooo escapes>
  # The bytes go in printf's *format*: bash 2.05b's %b drops an all-NUL
  # argument, but format escapes are emitted byte by byte (NULs included).
  printf "$3" | dd of="$TMP" bs=1 seek="$1" count="$2" conv=notrunc 2>/dev/null \
    || die "write failed at offset $1"
}

region() {   # region <file> <skip> <count>: md5 of 4 KiB blocks, or whole file if count=0
  if [ "$3" = 0 ]; then sum "$1"
  else dd if="$1" bs=4096 skip="$2" count="$3" 2>/dev/null | md5 | awk '{print $NF}'; fi
}

identify() {   # identify <file> <component>: sets KEY LABEL STATE SKIP COUNT WANT ORIG CUR
  [ -f "$1" ] || die "missing $1"
  KEY=; LABEL=; STATE=unknown; STYLE=; EDITKEY=; SWITCH=; CUR=$(sum "$1")
  case "$2" in
    finder|stripes|header|well) identify_finder "$1" ;;
    titlebars) identify_theme "$1" ;;
    appkit)    identify_appkit "$1" ;;
    grip)      identify_grip "$1" ;;
    logo)      identify_logo "$1" ;;
  esac
}
STYLES="stripes header well"
style_name() { case "$1" in stripes) echo pinstriped ;; header) echo "header" ;; well) echo "inset" ;; *) echo "$1" ;; esac; }
style_target() {   # WANT/EDITKEY for FINDER_STYLE (plain|<style>|keep) given the STYLE found
  W="${FINDER_STYLE:-keep}"; [ "$W" = keep ] && W="${STYLE:-plain}"
  eval "WANT=\$H_$W"
  [ -z "$WANT" ] && { W=plain; WANT=$H_plain; }      # no build of that style for this file
  if [ "$WANT" = "$H_plain" ]; then EDITKEY=$KEY; else EDITKEY=$KEY$W; fi
  if [ "$STATE" = patched ] && [ "$R" != "$WANT" ]; then STATE=oldpatch; SWITCH=$W; fi
}
identify_finder() {
__KNOWN_FINDER__
}
identify_theme() {
__KNOWN_THEME__
}
identify_appkit() {
__KNOWN_APPKIT__
}
identify_logo() {
__KNOWN_LOGO__
}
identify_grip() {
__KNOWN_GRIP__
}
LOGO_FILES="${LOGO_FILES:-__LOGO_PATHS__}"   # each is a separate file; status/install/restore go through
                                             # those present (Panther and Tiger each have only some)

apply_edits() {
  case "$1" in
__EDITS__
  *) die "no edits for $1" ;;
  esac
}

swap_in() {   # swap_in <src> <file>: atomic replace keeping owner/mode
  TMP="$2.aquafinder-tmp"; rm -f "$TMP"
  cp -p "$1" "$TMP" || die "cannot copy to $TMP"
}

find_backup() {   # find_backup <file>: sets BK to a verified original, or fails
  BK="$BACKUP_DIR/${1##*/}-$KEY.orig"
  [ -f "$BK" ] || BK="$OLD_BACKUP_DIR/${1##*/}-$KEY.orig"
  [ -f "$BK" ] && [ "$(region "$BK" $SKIP $COUNT)" = "$ORIG" ]
}

install_one() {   # install_one <file> <name>
  F="$1"; identify "$F" "$2"; HOW=installed
  case "$STATE" in
    patched) echo "$2: already installed ($LABEL)."; return 0 ;;
    unknown) echo "$2: unrecognised $F (md5 $CUR), skipped. Nothing changed."; return 1 ;;
    oldpatch)
      # patched by an older Aquafinder: re-patch starting from the saved original
      find_backup "$F" || { echo "$2: patched by an older Aquafinder, but its original backup is missing; skipped."; return 1; }
      SRC="$BK"; HOW="updated from an older Aquafinder"
      [ -n "$SWITCH" ] && HOW="switched to the $(style_name $SWITCH) sidebar" ;;
    original)
      mkdir -p "$BACKUP_DIR" || die "cannot create $BACKUP_DIR"
      BK="$BACKUP_DIR/${F##*/}-$KEY.orig"
      if [ ! -f "$BK" ] || [ "$(region "$BK" $SKIP $COUNT)" != "$ORIG" ]; then
        cp -p "$F" "$BK" || die "backup failed"
      fi
      SRC="$F" ;;
  esac
  swap_in "$F" "$F"                                 # copy keeps owner and mode
  [ "$SRC" = "$F" ] || cat "$SRC" > "$TMP" || die "cannot copy $SRC"
  apply_edits "${EDITKEY:-$KEY}"
  [ "$(region "$TMP" $SKIP $COUNT)" = "$WANT" ] || die "$2: patched copy failed verification; nothing changed."
  mv -f "$TMP" "$F" || die "could not replace $F"; TMP=
  echo "$2: $HOW ($LABEL). Backup: $BK"
  CHANGED="$CHANGED $2"
}

restore_one() {   # restore_one <file> <name>
  F="$1"; identify "$F" "$2"
  case "$STATE" in
    original) echo "$2: already original ($LABEL)."; return 0 ;;
    unknown)  echo "$2: unrecognised file (md5 $CUR), skipped."; return 1 ;;
  esac
  find_backup "$F" || die "$2: backup $BK missing or damaged."
  swap_in "$BK" "$F"
  mv -f "$TMP" "$F" || die "could not restore $F"; TMP=
  echo "$2: restored original ($LABEL)."
  CHANGED="$CHANGED $2"
}

status_one() {
  identify "$1" "$2"
  case "$STATE" in
    original) echo "$2: original ($LABEL)" ;;
    patched)  echo "$2: Aquafinder installed ($LABEL${STYLE:+, $(style_name $STYLE) sidebar})" ;;
    oldpatch) echo "$2: older Aquafinder installed ($LABEL); run install to update" ;;
    *)        echo "$2: not recognised (md5 $CUR)" ;;
  esac
}

need_root() {
  [ -n "$NO_ROOT_CHECK" ] && return 0
  [ "$(id -u)" = 0 ] || die "run with sudo: sudo sh $0 $*"
}

finder_style() {   # FINDER_STYLE for install finder: the installed Finder's (plain if none)
  [ -n "$FINDER_STYLE" ] && return 0
  identify "$FINDER" finder; FINDER_STYLE="${STYLE:-plain}"
}

install_finder() {   # install_finder <finder|style>: the Finder and its resources, in FINDER_STYLE
  finder_style
  install_one "$FINDER" "$1" || RC=1
  install_one "$GRIP" grip || RC=1
  FINDER_STYLE=
}

style_off() {   # restore <style>: that sidebar style goes back to the plain sidebar
  identify "$FINDER" finder
  case "$STATE" in
    original|unknown) echo "$1: off (the Aqua Finder isn't installed)."; return 0 ;;
  esac
  [ "$STYLE" = "$1" ] || { echo "$1: already off ($LABEL)."; return 0; }
  FINDER_STYLE=plain; install_finder "$1"
}

status_styles() {   # one line per style: installed = the Finder's sidebar is in that style
  identify "$FINDER" finder
  for S in $STYLES; do
    case "$STATE" in
      unknown) echo "$S: not recognised (md5 $CUR)" ;;
      original) echo "$S: original (Aqua Finder not installed)" ;;
      *) if [ "$STYLE" = "$S" ]; then echo "$S: Aquafinder installed ($(style_name $S) sidebar)"
         else echo "$S: original ($(style_name ${STYLE:-plain}) sidebar)"; fi ;;
    esac
  done
}

finish() {
  [ -n "$NO_RESTART" ] && return 0
  case "$CHANGED" in *finder*|*grip*|*stripes*|*header*|*well*)
    # no killall without the optional BSD Subsystem; ps is in /bin
    for P in $(ps -axc | awk '$NF == "Finder" {print $1}'); do kill "$P" 2>/dev/null; done
    echo "Finder restarted." ;;
  esac
  case "$CHANGED" in
    *appkit*)    echo "Restart the Mac: AppKit stays loaded until a restart, so Cocoa apps change only after it." ;;
    *titlebars*) echo "Log out and back in (or restart) so every app picks up the title bars." ;;
  esac
  case "$CHANGED" in *logo*)
    # the Dock keeps its own per-user icon cache across logins; it rebuilds it on launch
    rm -f /Library/Caches/com.apple.dock.iconcache.* /Users/*/Library/Caches/com.apple.dock.iconcache.* 2>/dev/null
    for P in $(ps -axc | awk '$NF == "Dock" {print $1}'); do kill "$P" 2>/dev/null; done
    touch /System/Library/CoreServices/Finder.app   # refresh the Finder's cached icon
    echo "Dock restarted. The login panel shows the new logo after you log out." ;;
  esac
}

WHAT="${2:-all}"
case "$WHAT" in finder|stripes|header|well|titlebars|logo|all) ;; *) echo "unknown component: $WHAT"; exit 1 ;; esac
want() { [ "$WHAT" = all ] || [ "$WHAT" = "$1" ]; }
is_style() { case "$1" in stripes|header|well) return 0 ;; esac; return 1; }
CHANGED=; RC=0
case "$1" in
  install)
    need_root install
    want finder    && install_finder finder
    is_style "$WHAT" && { FINDER_STYLE=$WHAT; install_finder "$WHAT"; }
    want titlebars && { install_one "$THEME" titlebars || RC=1; install_one "$APPKIT" appkit || RC=1; }
    want logo      && for F in $LOGO_FILES; do [ -f "$F" ] || continue; install_one "$F" logo || RC=1; done
    finish ;;
  restore|uninstall)
    need_root restore
    want finder    && { restore_one "$FINDER" finder || RC=1; restore_one "$GRIP" grip || RC=1; }
    is_style "$WHAT" && { style_off "$WHAT" || RC=1; }
    want titlebars && { restore_one "$THEME" titlebars || RC=1; restore_one "$APPKIT" appkit || RC=1; }
    want logo      && for F in $LOGO_FILES; do [ -f "$F" ] || continue; restore_one "$F" logo || RC=1; done
    finish ;;
  status|"")
    status_one "$FINDER" finder
    status_one "$GRIP" grip
    status_styles
    status_one "$THEME" titlebars
    status_one "$APPKIT" appkit
    for F in $LOGO_FILES; do [ -f "$F" ] && status_one "$F" logo; done ;;
  *) echo "usage: sudo sh $0 [status|install|restore] [finder|stripes|header|well|titlebars|logo]"; exit 1 ;;
esac
exit $RC
'''
script = (script.replace('__KNOWN_FINDER__', known_finder).replace('__KNOWN_THEME__', known_theme).replace('__KNOWN_APPKIT__', known_appkit).replace('__KNOWN_LOGO__', known_logo).replace('__KNOWN_GRIP__', known_grip).replace('__LOGO_PATHS__', logo_paths).replace('__EDITS__', edits)
          .replace('__FINDER__', FINDER_PATH).replace('__THEME__', THEME_PATH).replace('__APPKIT__', APPKIT_PATH).replace('__GRIP__', GRIP_PATH))
os.makedirs(os.path.join(ROOT, 'dist'), exist_ok=True)
path = os.path.join(ROOT, 'dist', 'aquafinder.sh')
open(path, 'w').write(script)
os.chmod(path, 0o755)
for c, key, lbl, sk, cn, o, n, e in entries:
    print('%-9s %-14s %s -> %s (%d writes; %s)' % (c, lbl, o, n, e.count('    put '),
          'whole file' if not cn else '__text blocks %d+%d' % (sk, cn)))
print('wrote %s (%d KB)' % (path, len(script) // 1024))
