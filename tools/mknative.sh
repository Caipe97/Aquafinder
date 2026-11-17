#!/bin/sh
# Build Aquafinder.app, Aquafinder.pkg and dist/Aquafinder.dmg on a real
# Panther Mac over SSH (nothing here can compile PowerPC Cocoa code).
# The Mac needs the Developer Tools and passwordless sudo for this user.
#   tools/mknative.sh <version>           uses vm/ssh/imac.config, host "imac"
#   AQ_SSH="ssh -F vm/ssh/config panther" tools/mknative.sh 1.0
# Rebuild dist/aquafinder.sh first (python3 tools/mkinstaller.py).
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
V="${1:?usage: $0 <version>}"
SSH="${AQ_SSH:-ssh -F $ROOT/vm/ssh/imac.config imac}"
W=aquafinder-build   # in the remote home, so a restart (which clears /tmp) keeps it
[ -n "$FETCH_ONLY" ] || tar --format ustar --no-mac-metadata --no-xattrs -cf - -C "$ROOT" gui pkg tools/native-build.sh -C "$ROOT/dist" aquafinder.sh \
  | $SSH "rm -rf $W/gui $W/pkg $W/tools && mkdir -p $W && cd $W && tar -xf - && mv tools/native-build.sh . && sh native-build.sh $V" \
  || { echo "mknative: if sudo was the problem, run this in Terminal on the Mac, then rerun with FETCH_ONLY=1:"
       echo "    cd ~/$W && sh native-build.sh $V"; exit 1; }
$SSH "cat $W/build/Aquafinder.dmg" > dist/Aquafinder.dmg
echo "fetched $(md5 -q dist/Aquafinder.dmg) -> dist/Aquafinder.dmg"
