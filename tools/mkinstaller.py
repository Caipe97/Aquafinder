"""Generate dist/aquafinder.sh: a self-contained Panther shell script that
installs/restores two independent components on an iBook:

  finder     Aqua (non-brushed-metal) Finder windows with toolbar + sidebar
  titlebars  Jaguar's pinstriped, translucent title bars (theme Extras.rsrc,
             plus AppKit so Cocoa windows can show the translucency)
"""
import sys, hashlib, os
sys.path.insert(0, os.path.dirname(__file__))
import patch, theme, appkit_patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FINDER_PATH = '/System/Library/CoreServices/Finder.app/Contents/MacOS/Finder'
THEME_PATH = ('/System/Library/Frameworks/Carbon.framework/Versions/A/Frameworks/'
              'HIToolbox.framework/Versions/A/Resources/Extras.rsrc')
APPKIT_PATH = '/System/Library/Frameworks/AppKit.framework/Versions/C/AppKit'
FINDER_BUILDS = [('10.3.9', 'orig/Finder-10.3.9')]
APPKIT_SRC = 'orig/appkit/AppKit-10.3.9'             # stock, from the 10.3.9 Combo
THEME_SRC = 'theme/panther-10.3.9/Extras.rsrc'      # unchanged since 10.3.0 (the Combo doesn't ship it)
JAGUAR_SRC = 'theme/jaguar/Extras.rsrc'              # from Mac OS X 10.2.8
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


def edit_lines(a, b):
    lines = []
    for off, chunk in runs(a, b):
        for k in range(0, len(chunk), 1024):   # keep each printf argument modest
            part = chunk[k:k+1024]
            lines.append("    put %d %d '%s'" % (off + k, len(part), ''.join('\\%03o' % c for c in part)))
    return '\n'.join(lines)


from macho import MachO

def text_region(path, a, b):
    """4 KiB-aligned block span covering __TEXT after the Mach-O header.
    update_prebinding rewrites the header/load commands and __DATA pointers
    but never the code segment, so this identifies a Finder build however
    often it has been re-prebound -- and it covers the gradient routine that
    lives in __TEXT's tail padding."""
    import struct as _s
    m = MachO(path)
    sizeofcmds = _s.unpack_from('>I', m.data, 20)[0]
    seg = [x for x in m.segments if x['name'] == '__TEXT'][0]
    skip = -(-(28 + sizeofcmds) // 4096)
    count = (seg['fileoff'] + seg['filesize']) // 4096 - skip
    lo, hi = skip * 4096, (skip + count) * 4096
    for off, chunk in runs(a, b):
        assert lo <= off and off + len(chunk) <= hi, 'patch outside identification region'
    return skip, count, md5(a[lo:hi]), md5(b[lo:hi])

entries = []   # (component, key, label, skip, count, orig md5, patched md5, edit lines)
for ver, rel in FINDER_BUILDS:
    src = os.path.join(ROOT, rel)
    out = os.path.join(ROOT, 'build', 'Finder-%s-slim' % ver)
    patch.apply(src, out, quiet=True)
    a, b = open(src, 'rb').read(), open(out, 'rb').read()
    skip, count, mo, mp = text_region(src, a, b)
    entries.append(('finder', 'finder' + ver.replace('.', ''), 'Finder ' + ver, skip, count, mo, mp, edit_lines(a, b)))

theme_out = os.path.join(ROOT, 'build', 'Extras-jaguarbars.rsrc')
import contextlib, io
with contextlib.redirect_stdout(io.StringIO()):
    theme.transplant(os.path.join(ROOT, THEME_SRC), os.path.join(ROOT, JAGUAR_SRC), theme_out, THEME_IDS)
    # loading spinner art 16 -> 13 px, so it fits the 15 px bottom bar
    theme.shrink_frames(theme_out, theme_out, 390, 13, 2)
a, b = open(os.path.join(ROOT, THEME_SRC), 'rb').read(), open(theme_out, 'rb').read()
entries.append(('titlebars', 'theme', 'Panther theme', 0, 0, md5(a), md5(b), edit_lines(a, b)))

src = os.path.join(ROOT, APPKIT_SRC); out = os.path.join(ROOT, 'build', 'AppKit-10.3.9-slim')
appkit_patch.apply(src, out, quiet=True)
a, b = open(src, 'rb').read(), open(out, 'rb').read()
skip, count, mo, mp = text_region(src, a, b)
entries.append(('appkit', 'appkit1039', 'AppKit 10.3.9', skip, count, mo, mp, edit_lines(a, b)))

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
            if k == key and h != n:
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
known_finder, known_theme, known_appkit = ident_block('finder'), ident_block('titlebars'), ident_block('appkit')
edits = '\n'.join("  %s)\n%s\n    ;;" % (key, e) for c, key, lbl, sk, cn, o, n, e in entries)

script = r'''#!/bin/sh
# Aquafinder for Mac OS X 10.3.9 (Panther).
#
#   finder     Aqua (non-brushed-metal) Finder windows that keep toolbar + sidebar,
#              a Jaguar-style soft shadow for the bottom bar and softer pane borders
#   titlebars  Jaguar-style pinstriped, translucent window title bars
#              (the HIToolbox theme, plus AppKit so Cocoa windows blend too)
#
#   sh aquafinder.sh status
#   sudo sh aquafinder.sh install [finder|titlebars]     (default: both)
#   sudo sh aquafinder.sh restore [finder|titlebars]     (default: both)
#
# Only recognised files are touched (the Finder is identified by its code
# section, so re-prebinding by Software Update doesn't matter). Each is backed up, patched
# on a copy, verified, then swapped in atomically. Generated by
# tools/mkinstaller.py; do not edit by hand.

PATH=/bin:/sbin:/usr/bin:/usr/sbin; export PATH
FINDER="${FINDER:-__FINDER__}"
THEME="${THEME:-__THEME__}"
APPKIT="${APPKIT:-__APPKIT__}"
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
  KEY=; LABEL=; STATE=unknown; CUR=$(sum "$1")
  case "$2" in
    finder)    identify_finder "$1" ;;
    titlebars) identify_theme "$1" ;;
    appkit)    identify_appkit "$1" ;;
  esac
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
      SRC="$BK"; HOW="updated from an older Aquafinder" ;;
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
  apply_edits "$KEY"
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
    patched)  echo "$2: Aquafinder installed ($LABEL)" ;;
    oldpatch) echo "$2: older Aquafinder installed ($LABEL); run install to update" ;;
    *)        echo "$2: not recognised (md5 $CUR)" ;;
  esac
}

need_root() {
  [ -n "$NO_ROOT_CHECK" ] && return 0
  [ "$(id -u)" = 0 ] || die "run with sudo: sudo sh $0 $*"
}

finish() {
  [ -n "$NO_RESTART" ] && return 0
  case "$CHANGED" in *finder*)
    # no killall without the optional BSD Subsystem; ps is in /bin
    for P in $(ps -axc | awk '$NF == "Finder" {print $1}'); do kill "$P" 2>/dev/null; done
    echo "Finder restarted." ;;
  esac
  case "$CHANGED" in
    *appkit*)    echo "Restart the Mac: AppKit stays loaded until a restart, so Cocoa apps change only after it." ;;
    *titlebars*) echo "Log out and back in (or restart) so every app picks up the title bars." ;;
  esac
}

WHAT="${2:-all}"
case "$WHAT" in finder|titlebars|all) ;; *) echo "unknown component: $WHAT"; exit 1 ;; esac
CHANGED=; RC=0
case "$1" in
  install)
    need_root install
    [ "$WHAT" != titlebars ] && { install_one "$FINDER" finder || RC=1; }
    [ "$WHAT" != finder ]    && { install_one "$THEME" titlebars || RC=1; install_one "$APPKIT" appkit || RC=1; }
    finish ;;
  restore|uninstall)
    need_root restore
    [ "$WHAT" != titlebars ] && { restore_one "$FINDER" finder || RC=1; }
    [ "$WHAT" != finder ]    && { restore_one "$THEME" titlebars || RC=1; restore_one "$APPKIT" appkit || RC=1; }
    finish ;;
  status|"")
    status_one "$FINDER" finder
    status_one "$THEME" titlebars
    status_one "$APPKIT" appkit ;;
  *) echo "usage: sudo sh $0 [status|install|restore] [finder|titlebars]"; exit 1 ;;
esac
exit $RC
'''
script = (script.replace('__KNOWN_FINDER__', known_finder).replace('__KNOWN_THEME__', known_theme).replace('__KNOWN_APPKIT__', known_appkit).replace('__EDITS__', edits)
          .replace('__FINDER__', FINDER_PATH).replace('__THEME__', THEME_PATH).replace('__APPKIT__', APPKIT_PATH))
os.makedirs(os.path.join(ROOT, 'dist'), exist_ok=True)
path = os.path.join(ROOT, 'dist', 'aquafinder.sh')
open(path, 'w').write(script)
os.chmod(path, 0o755)
for c, key, lbl, sk, cn, o, n, e in entries:
    print('%-9s %-14s %s -> %s (%d writes; %s)' % (c, lbl, o, n, e.count('    put '),
          'whole file' if not cn else '__text blocks %d+%d' % (sk, cn)))
print('wrote %s (%d KB)' % (path, len(script) // 1024))
