#!/bin/sh
# Copy a binary into the (stopped) QEMU image, overwriting in place so the
# original owner/permissions are kept.
#   usage: install-into-vm.sh <binary> [image] [guest path]
#   image defaults to vm/panther.img, guest path to the Finder executable.
# Checks the source before touching the image, verifies the copy by md5, and
# always detaches the image again.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$1"
IMG="${2:-$ROOT/vm/panther.img}"
GUEST="${3:-/System/Library/CoreServices/Finder.app/Contents/MacOS/Finder}"
die() { echo "install-into-vm: $*" >&2; exit 1; }

[ -n "$SRC" ] || die "usage: $0 <binary> [image] [guest path]"
[ -f "$SRC" ] && [ -s "$SRC" ] || die "source '$SRC' is missing or empty; image untouched"
[ "$(xxd -p -l 4 "$SRC")" = feedface ] || die "source '$SRC' is not a PPC Mach-O; image untouched"
pgrep -f "qemu-system-ppc.*$(basename "$IMG")" >/dev/null && die "QEMU is using $(basename "$IMG"); stop it first"

OUT=$(hdiutil attach -nobrowse -noverify -mountrandom /private/tmp \
      -imagekey diskimage-class=CRawDiskImage "$IMG") || die "attach failed"
DEV=$(printf '%s\n' "$OUT" | awk -F'\t' '/Apple_HFS/ {print $1}' | tr -d ' ')
MNT=$(printf '%s\n' "$OUT" | awk -F'\t' '/Apple_HFS/ {print $NF}')
trap 'sync; hdiutil detach "$DEV" >/dev/null 2>&1 || hdiutil detach -force "$DEV" >/dev/null 2>&1' EXIT
[ -d "$MNT/System" ] || die "no Panther volume in $IMG"

F="$MNT$GUEST"
[ -f "$F" ] || die "no $GUEST in the image"
cat "$SRC" > "$F" || die "copy failed: $F may be damaged; rerun with a valid source"
[ "$(md5 -q "$F")" = "$(md5 -q "$SRC")" ] || die "verification failed after copy; rerun"
md5 -q "$F"
echo "installed $(basename "$SRC") into $(basename "$IMG")"
