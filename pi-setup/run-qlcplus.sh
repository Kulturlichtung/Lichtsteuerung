#!/bin/bash
# Started by qlcplus.service. Reads the USB stick's config file and
# launches QLC+ headless (no display needed -- QT_QPA_PLATFORM=offscreen,
# see CLAUDE.md/README for why QApplication still needs this even with
# -n/--nogui) with Web Access enabled, loading whichever project the
# config points at.
set -euo pipefail

USB_MOUNT="/mnt/usbdata"
CONFIG="$USB_MOUNT/lichtsteuerung.conf"

if [ ! -f "$CONFIG" ]; then
    echo "Config not found at $CONFIG -- USB stick plugged in and mounted?" >&2
    exit 1
fi
# shellcheck source=/dev/null
source "$CONFIG"

if [ ! -f "$USB_MOUNT/$QXW_FILE" ]; then
    echo "QXW_FILE '$QXW_FILE' not found under $USB_MOUNT" >&2
    exit 1
fi

export QT_QPA_PLATFORM=offscreen

exec qlcplus -o "$USB_MOUNT/$QXW_FILE" -n -p -w -wp "${WEB_PORT:-9999}"
