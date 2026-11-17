#!/bin/sh
# Copy a file into the running Panther VM over SSH and swap it in atomically,
# keeping the original owner and mode. No reboot, no disk image mounting.
#   usage: vm-push.sh <local file> [guest path] [--restart-finder]
#   guest path defaults to the Finder executable; --restart-finder is implied then.
# A running process keeps its old copy (new inode); restart the app to load it.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FINDER=/System/Library/CoreServices/Finder.app/Contents/MacOS/Finder
SRC="$1"; DST="${2:-$FINDER}"; RESTART="$3"
[ "$DST" = "$FINDER" ] && RESTART=--restart-finder
die() { echo "vm-push: $*" >&2; exit 1; }
[ -f "$SRC" ] && [ -s "$SRC" ] || die "usage: $0 <local file> [guest path] [--restart-finder]"
SUM=$(md5 -q "$SRC")
ssh() { command ssh -F "$ROOT/vm/ssh/config" panther "$@"; }

ssh "cat > /tmp/vm-push.$$" < "$SRC" || die "upload failed"
ssh "set -e
  [ -f '$DST' ] || { echo 'no $DST in the VM'; rm -f /tmp/vm-push.$$; exit 1; }
  [ \"\$(md5 -q /tmp/vm-push.$$)\" = $SUM ] || { echo 'upload corrupted'; rm -f /tmp/vm-push.$$; exit 1; }
  cp -p '$DST' '$DST.vm-push-new'
  cat /tmp/vm-push.$$ > '$DST.vm-push-new'
  rm -f /tmp/vm-push.$$
  mv -f '$DST.vm-push-new' '$DST'
  echo \"installed \$(md5 -q '$DST') -> $DST\"" || die "install failed"

if [ "$RESTART" = --restart-finder ]; then
  # no killall without the BSD Subsystem; loginwindow relaunches the Finder
  ssh 'for P in $(ps -axc | awk '"'"'$NF == "Finder" {print $1}'"'"'); do kill $P; done; echo "Finder restarted"'
fi
