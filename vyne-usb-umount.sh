#!/bin/bash
DEVICE=/dev/$1
umount "$DEVICE" 2>/dev/null
for dir in /media/pi/*/; do
    mountpoint -q "$dir" || rmdir "$dir" 2>/dev/null
done
