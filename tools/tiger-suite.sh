#!/bin/sh
# Aquafinder test suite for Tiger 10.4.11, run as root in the VM with
# dist/aquafinder.sh copied to /tmp/aquafinder.sh:
#   sh tiger-suite.sh quick   status, the stripes option on and off (from the plain Finder and
#                             from the original), the Finder round trip (with its Finder.rsrc,
#                             which keeps one style), bad args, non-root
#                             (STRIPES_MD5=<md5 of build/Finder-10.4.11-stripes> also checks it)
#   sh tiger-suite.sh full    install all (no-op), restore all, install all: files as at the start
# Prints PASS/FAIL per check and a summary. It runs with NO_RESTART=1: nothing
# is restarted, so reboot afterwards (full restores and reinstalls AppKit).
S=/tmp/aquafinder.sh
CS=/System/Library/CoreServices
F=$CS/Finder.app/Contents/MacOS/Finder
R=$CS/Finder.app/Contents/Resources/Finder.rsrc
T=/System/Library/Frameworks/Carbon.framework/Versions/A/Frameworks/HIToolbox.framework/Versions/A/Resources/Extras.rsrc
A=/System/Library/Frameworks/AppKit.framework/Versions/C/AppKit
ALL="$F $R $T $A $CS/loginwindow.app/Contents/Resources/MacOSX.tif $CS/Finder.app/Contents/Resources/Finder.icns $CS/CoreTypes.bundle/Contents/Resources/FinderIcon.icns $CS/Dock.app/Contents/Resources/finder.png $CS/SecurityAgent.app/Contents/Resources/MacOSX.tif"
export NO_RESTART=1
PASS=0; FAIL=0
cd /tmp
snap() { for f in $ALL; do [ -f "$f" ] && echo "$f $(md5 -q "$f")"; done; }
ok()   { PASS=$((PASS+1)); echo "PASS $*"; }
bad()  { FAIL=$((FAIL+1)); echo "FAIL $*"; }
# run <label> <expected exit> <args...>: OUT, RCODE
run() { L="$1"; E="$2"; shift 2; OUT=$(sh $S "$@" 2>&1); RCODE=$?
        echo "---- $L: sh aquafinder.sh $*  (exit $RCODE)"; echo "$OUT" | sed 's/^/     /'
        [ "$RCODE" = "$E" ] && ok "$L: exit $E" || bad "$L: exit $RCODE, expected $E"; }
has()  { echo "$OUT" | grep -q "$2" && ok "$1: says '$2'" || bad "$1: no '$2'"; }
hasnt(){ echo "$OUT" | grep -q "$2" && bad "$1: says '$2'" || ok "$1: no '$2'"; }
same() { snap > /tmp/suite.now; cmp -s /tmp/suite.now /tmp/suite.$2 && ok "$1: files as at '$2'" || { bad "$1: files differ from '$2'"; diff /tmp/suite.$2 /tmp/suite.now | sed 's/^/     /'; }; }
save() { snap > /tmp/suite.$1; }
FM() { md5 -q "$F"; }

save start

if [ "$1" = quick ]; then
  run status 0 status
  has status 'finder: Aquafinder installed (Finder 10.4.11, plain sidebar)'
  has status 'grip: Aquafinder installed (Finder images 10.4.11)'
  has status 'stripes: original (plain sidebar)'
  same status start

  # the stripes option, from the plain Finder and back
  run 'install stripes' 0 install stripes
  has 'install stripes' 'stripes: switched to the pinstriped sidebar (Finder 10.4.11)'
  has 'install stripes' 'grip: already installed (Finder images 10.4.11).'
  [ -z "$STRIPES_MD5" ] || { [ "$(FM)" = "$STRIPES_MD5" ] && ok 'install stripes: Finder = the stripes build' || bad "install stripes: Finder $(FM) != $STRIPES_MD5"; }
  [ "$(md5 -q $R)" = "$(grep "^$R " /tmp/suite.start | cut -d' ' -f2)" ] && ok 'install stripes: Finder.rsrc untouched' || bad 'install stripes: Finder.rsrc changed'
  save stripes
  run 'status (stripes)' 0 status
  has 'status (stripes)' 'finder: Aquafinder installed (Finder 10.4.11, pinstriped sidebar)'
  has 'status (stripes)' 'stripes: Aquafinder installed (pinstriped sidebar)'
  run 'install stripes (stripes)' 0 install stripes
  has 'install stripes (stripes)' 'stripes: already installed (Finder 10.4.11).'
  same 'install stripes (stripes)' stripes
  run 'install finder (stripes)' 0 install finder
  has 'install finder (stripes)' 'finder: already installed (Finder 10.4.11).'
  same 'install finder (stripes)' stripes
  run 'restore stripes' 0 restore stripes
  has 'restore stripes' 'stripes: switched to the plain sidebar (Finder 10.4.11)'
  same 'restore stripes' start
  run 'restore stripes (plain)' 0 restore stripes
  has 'restore stripes (plain)' 'stripes: already off (Finder 10.4.11).'
  same 'restore stripes (plain)' start

  run 'install finder (installed)' 0 install finder
  has 'install finder (installed)' 'finder: already installed (Finder 10.4.11).'
  has 'install finder (installed)' 'grip: already installed (Finder images 10.4.11).'
  same 'install finder (installed)' start

  # the original Finder: restore, the option on and off from there
  run 'restore finder' 0 restore finder
  has 'restore finder' 'finder: restored original (Finder 10.4.11).'
  has 'restore finder' 'grip: restored original (Finder images 10.4.11).'
  [ "$(FM)" = "$(md5 -q /Library/Aquafinder/Finder-finder10411.orig)" ] && ok 'restore finder: Finder = its backup' || bad 'restore finder: Finder != backup'
  save restored
  run 'status (restored)' 0 status
  has 'status (restored)' 'finder: original (Finder 10.4.11)'
  has 'status (restored)' 'grip: original (Finder images 10.4.11)'
  has 'status (restored)' 'stripes: original (Aqua Finder not installed)'
  run 'restore finder (original)' 0 restore finder
  has 'restore finder (original)' 'finder: already original'
  same 'restore finder (original)' restored
  run 'restore stripes (original)' 0 restore stripes
  has 'restore stripes (original)' "stripes: off (the Aqua Finder isn't installed)."
  same 'restore stripes (original)' restored

  run 'install stripes (original)' 0 install stripes
  has 'install stripes (original)' 'stripes: installed (Finder 10.4.11)'
  same 'install stripes (original)' stripes
  run 'restore finder (stripes)' 0 restore finder
  has 'restore finder (stripes)' 'finder: restored original (Finder 10.4.11).'
  same 'restore finder (stripes)' restored

  run 'install finder' 0 install finder
  has 'install finder' 'finder: installed (Finder 10.4.11)'
  same 'install finder' start

  run 'bad component' 1 install bogus
  has 'bad component' 'unknown component: bogus'
  run 'bad verb' 1 frobnicate
  has 'bad verb' 'usage:'
  same 'bad args' start

  OUT=$(su quad8 -c "sh $S install stripes" 2>&1); RCODE=$?
  echo "---- non-root install: (exit $RCODE)"; echo "$OUT" | sed 's/^/     /'
  [ "$RCODE" = 1 ] && ok 'non-root install: exit 1' || bad "non-root install: exit $RCODE"
  has 'non-root install' 'run with sudo'
  OUT=$(su quad8 -c "sh $S status" 2>&1); RCODE=$?
  [ "$RCODE" = 0 ] && ok 'non-root status: exit 0' || bad "non-root status: exit $RCODE"
  has 'non-root status' 'stripes: original (plain sidebar)'
  same 'non-root' start
fi

if [ "$1" = full ]; then
  run 'install (all, installed)' 0 install
  hasnt 'install (all, installed)' 'unrecognised'
  same 'install (all, installed)' start
  run 'restore (all)' 0 restore
  has 'restore (all)' 'grip: restored original (Finder images 10.4.11).'
  run 'status (all restored)' 0 status
  hasnt 'status (all restored)' 'Aquafinder installed'
  save allrestored
  run 'install (all)' 0 install
  hasnt 'install (all)' 'unrecognised'
  hasnt 'install (all)' 'failed'
  same 'install (all)' start
  run 'status (all installed)' 0 status
  has 'status (all installed)' 'stripes: original (plain sidebar)'
  OUT=$(echo "$OUT" | grep -v '^stripes:')   # (the option is off: 'original')
  hasnt 'status (all installed)' 'original'
fi

echo "==== $1: $PASS passed, $FAIL failed"
