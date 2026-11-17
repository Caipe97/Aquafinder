#!/bin/sh
# Boot a Panther test image at the iBook's 800x600 resolution.
#   IMG=panther.img (default)   SOCK=qemu (socket prefix: qemu-monitor.sock / qemu-qmp.sock)
#   SSH_PORT=2222: host port (localhost only) forwarded to the VM's sshd; see vm/ssh/config
cd "$(dirname "$0")"
IMG="${IMG:-panther.img}"; SOCK="${SOCK:-qemu}"; SSH_PORT="${SSH_PORT:-2222}"
exec qemu-system-ppc -M mac99,via=pmu -m 512 \
  -g 800x600x32 \
  -drive file="$IMG",format="${FMT:-raw}",media=disk \
  -device usb-tablet -device usb-kbd \
  -nic user,model=sungem,hostfwd=tcp:127.0.0.1:$SSH_PORT-:22 \
  -boot c \
  -prom-env 'auto-boot?=true' \
  -monitor unix:$SOCK-monitor.sock,server,nowait \
  -qmp unix:$SOCK-qmp.sock,server,nowait \
  -display cocoa \
  -name "Panther test ($IMG)" "$@"
