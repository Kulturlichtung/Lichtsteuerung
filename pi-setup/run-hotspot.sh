#!/bin/bash
# Started by hotspot.service at boot. Reads the USB stick's config and
# (re)configures the Pi's own WLAN hotspot via NetworkManager, so SSID/
# password are changeable on the USB stick like everything else -- no
# Pi login needed to change them. Idempotent: creates the connection
# profile on first run, just updates it on every run after.
set -euo pipefail

USB_MOUNT="/mnt/usbdata"
CONFIG="$USB_MOUNT/lichtsteuerung.conf"
CON_NAME="Lichtsteuerung-Hotspot"
IFACE="wlan0"

if [ ! -f "$CONFIG" ]; then
    echo "Config not found at $CONFIG -- USB stick plugged in and mounted?" >&2
    exit 1
fi
# shellcheck source=/dev/null
source "$CONFIG"

: "${HOTSPOT_SSID:?HOTSPOT_SSID not set in $CONFIG}"
: "${HOTSPOT_PASSWORD:?HOTSPOT_PASSWORD not set in $CONFIG}"

if ! nmcli -t -f NAME connection show | grep -qx "$CON_NAME"; then
    nmcli connection add type wifi ifname "$IFACE" con-name "$CON_NAME" autoconnect yes ssid "$HOTSPOT_SSID"
fi

nmcli connection modify "$CON_NAME" \
    802-11-wireless.ssid "$HOTSPOT_SSID" \
    802-11-wireless.mode ap \
    802-11-wireless.band bg \
    ipv4.method shared \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "$HOTSPOT_PASSWORD"

exec nmcli connection up "$CON_NAME"
