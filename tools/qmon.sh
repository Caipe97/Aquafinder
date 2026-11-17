#!/bin/sh
# Send a command to the QEMU monitor. usage: qmon.sh "command"
# Unix socket vm/$SOCK-monitor.sock by default; set MONPORT for a TCP monitor
# (ppcosx run --monitor uses 4444).
if [ -n "$MONPORT" ]; then
  printf '%s\n' "$1" | nc -w 1 127.0.0.1 "$MONPORT"
else
  printf '%s\n' "$1" | nc -U -w 1 "$(dirname "$0")/../vm/${SOCK:-qemu}-monitor.sock"
fi | tr -d '\r' | grep -v '^(qemu)\|^QEMU'
true
