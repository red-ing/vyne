#!/bin/bash
DEVICE=/dev/$1
LABEL=$(blkid -s LABEL -o value "$DEVICE" 2>/dev/null)
[ -z "$LABEL" ] && LABEL=$(blkid -s UUID -o value "$DEVICE" 2>/dev/null | cut -c1-8)
[ -z "$LABEL" ] && LABEL="$1"
LABEL=$(echo "$LABEL" | tr ' ' '_' | tr -cd '[:alnum:]_-')
MOUNT_POINT="/media/pi/$LABEL"
mkdir -p "$MOUNT_POINT"
mount -o uid=1000,gid=1000,umask=022 "$DEVICE" "$MOUNT_POINT" 2>/dev/null \
    || mount "$DEVICE" "$MOUNT_POINT"
