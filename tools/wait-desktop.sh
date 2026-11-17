#!/bin/sh
# Wait until the Panther menu bar is visible in QEMU (max ~5 min).
S=/private/tmp/claude-501/-Users-manuel-panther-slim/b59bf558-a1a7-4477-b568-353560e2a9c4/scratchpad
T="$(dirname "$0")"
sleep 20
for i in $(seq 1 60); do
  sleep 5
  "$T/shot.sh" $S/wait.png 2>/dev/null || { echo "screendump failed"; exit 1; }
  r=$(python3 -c "
from PIL import Image; im=Image.open('$S/wait.png').convert('RGB')
top=[im.getpixel((x,8)) for x in range(100,700,50)]
print('up' if all(sum(p)>600 for p in top) and not all(abs(p[0]-191)<6 for p in top) else 'no')")
  [ "$r" = up ] && { sleep 8; echo "desktop up"; exit 0; }
done
echo timeout; exit 1
