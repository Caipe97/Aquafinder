#!/bin/sh
# Grab the QEMU screen as PNG. usage: shot.sh out.png
D="${SHOTDIR:-${TMPDIR:-/tmp}}"
"$(dirname "$0")/qmon.sh" "screendump $D/shot.ppm" >/dev/null
sleep 1
python3 -c "from PIL import Image; Image.open('$D/shot.ppm').save('$1')"
