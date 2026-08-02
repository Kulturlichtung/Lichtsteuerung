#!/bin/bash
# Started by beat-osc.service. Reads the same USB config as
# run-qlcplus.sh and launches beat_osc.py --auto against it. The
# code/venv itself lives on the Pi's own (overlay-protected) root under
# REPO_DIR, not on the USB stick -- only the project file + config are
# meant to be swapped/edited externally.
set -euo pipefail

USB_MOUNT="/mnt/usbdata"
CONFIG="$USB_MOUNT/lichtsteuerung.conf"
REPO_DIR="/opt/lichtsteuerung"

if [ ! -f "$CONFIG" ]; then
    echo "Config not found at $CONFIG -- USB stick plugged in and mounted?" >&2
    exit 1
fi
# shellcheck source=/dev/null
source "$CONFIG"

cd "$REPO_DIR/beat-detector"

startup_color_args=()
if [ -n "${AUTO_COLOR:-}" ]; then
    startup_color_args=(--startup-auto-color "$AUTO_COLOR")
fi

# INTENSITY_THRESHOLDS_DB is "D1 D2 D3" (space-separated) in the config --
# deliberately unquoted below so it word-splits into 3 separate args, since
# beat_osc.py's --intensity-thresholds-db takes 3 (nargs=3).
# shellcheck disable=SC2086
exec "$REPO_DIR/beat-detector/venv/bin/python3" -u beat_osc.py --auto \
    --device "${MIC_DEVICE:?MIC_DEVICE not set in $CONFIG}" \
    --audio-backend "${AUDIO_BACKEND:-alsaaudio}" \
    --alsa-device "${ALSA_DEVICE:-hw:2,0}" \
    --web-port "${WEB_PORT:-9999}" \
    --sensitivity "${SENSITIVITY:-3.5}" \
    --refractory-ms "${REFRACTORY_MS:-200}" \
    --intensity-thresholds-db ${INTENSITY_THRESHOLDS_DB:-1.5 4.0 8.0} \
    --baseline-seconds "${BASELINE_SECONDS:-120}" \
    --intensity-ema-alpha "${INTENSITY_EMA_ALPHA:-0.15}" \
    --band-hold-ms "${BAND_HOLD_MS:-2000}" \
    "${startup_color_args[@]}"
