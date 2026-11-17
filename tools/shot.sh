#!/bin/sh
# Grab the QEMU screen as PNG. usage: shot.sh out.png
D=/private/tmp/claude-501/-Users-manuel-panther-slim/b59bf558-a1a7-4477-b568-353560e2a9c4/scratchpad
"$(dirname "$0")/qmon.sh" "screendump $D/shot.ppm" >/dev/null
sleep 1
python3 -c "from PIL import Image; Image.open('$D/shot.ppm').save('$1')"
