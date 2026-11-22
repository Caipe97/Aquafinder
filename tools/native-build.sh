#!/bin/sh
# Runs ON a Panther (10.3) Mac with the Developer Tools, from a work folder
# holding gui/, pkg/ and aquafinder.sh. Builds:
#   build/Aquafinder.app    the Cocoa front end (aquafinder.sh inside)
#   build/Aquafinder.pkg    Installer package: puts the app in /Applications
#                           and applies both parts
#   build/Aquafinder.dmg    the package on a compressed disk image
# Needs sudo only to give the payload root:admin ownership. Over SSH it can't
# ask for a password, so if sudo needs one, run this in Terminal on the Mac.
#   usage: sh native-build.sh <version>      e.g. sh native-build.sh 1.0
set -e
V="${1:?version}"; MAJOR=${V%%.*}; MINOR=${V#*.}; MINOR=${MINOR%%.*}
cd "$(dirname "$0")"
sub() { sed -e "s/__VERSION__/$V/g" -e "s/__MAJOR__/$MAJOR/g" -e "s/__MINOR__/$MINOR/g" "$1" > "$2"; }
if [ -t 0 ]; then SUDO() { sudo "$@"; }   # in Terminal: sudo may ask
else SUDO() { sudo -S -p '' "$@" </dev/null 2>/dev/null; }; fi
rm -rf build 2>/dev/null || SUDO rm -rf build; mkdir build

# --- app
APP=build/Aquafinder.app/Contents
mkdir -p "$APP/MacOS" "$APP/Resources"
gcc -O2 -Wall -o "$APP/MacOS/Aquafinder" gui/main.m \
    -framework Cocoa -framework Security -framework ApplicationServices
strip -x "$APP/MacOS/Aquafinder"
sub gui/Info.plist "$APP/Info.plist"
printf 'APPL????' > "$APP/PkgInfo"
cp aquafinder.sh "$APP/Resources/"
[ -f gui/Aquafinder.icns ] && cp gui/Aquafinder.icns "$APP/Resources/" || true
cp gui/preview/*.png "$APP/Resources/"     # before/after pictures (tools/previews.py)

SUDO true || { echo "native-build: app built in build/Aquafinder.app; the package needs root."
               echo "native-build: run it in Terminal on the Mac so sudo can ask for the password."; exit 2; }

# --- package payload, owned and moded like the system folders it lands in
ROOT=build/root
mkdir -p "$ROOT/Applications"
cp -R build/Aquafinder.app "$ROOT/Applications/"
chmod -R u=rwX,go=rX "$ROOT/Applications/Aquafinder.app"
chmod 1775 "$ROOT"; chmod 775 "$ROOT/Applications"
SUDO chown -R root:admin "$ROOT"

PKG=build/Aquafinder.pkg/Contents
mkdir -p "$PKG/Resources/English.lproj"
sub pkg/Info.plist "$PKG/Info.plist"
printf 'pmkrpkg1' > "$PKG/PkgInfo"
cp pkg/InstallationCheck pkg/postflight aquafinder.sh "$PKG/Resources/"
chmod 755 "$PKG/Resources/InstallationCheck" "$PKG/Resources/postflight"
sub pkg/Welcome.rtf "$PKG/Resources/English.lproj/Welcome.rtf"
sub pkg/Description.plist "$PKG/Resources/English.lproj/Description.plist"
cp pkg/InstallationCheck.strings "$PKG/Resources/English.lproj/"
(cd "$ROOT" && SUDO pax -w -x cpio .) | gzip -9 > "$PKG/Archive.pax.gz"
SUDO mkbom "$ROOT" "$PKG/Archive.bom"
SUDO chown "$(id -un)" "$PKG/Archive.bom"
N=$(find "$ROOT" | wc -l | tr -d ' ')
KB=$(du -sk "$ROOT" | awk '{print $1}')
CKB=$(du -sk "$PKG/Archive.pax.gz" | awk '{print $1}')
printf 'NumFiles %s\nInstalledSize %s\nCompressedSize %s\n' "$N" "$KB" "$CKB" > "$PKG/Resources/Archive.sizes"

# --- disk image
mkdir build/dmg
cp -R build/Aquafinder.pkg build/dmg/
hdiutil create -quiet -srcfolder build/dmg -volname "Aquafinder $V" -format UDZO -ov build/Aquafinder.dmg
md5 build/Aquafinder.dmg
