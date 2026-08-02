#!/usr/bin/env python3
"""
Beat detector -> OSC/WebSocket bridge for QLC+ Sound-to-Light.

Two independent features, both driven by the same live audio stream:

1. Beat detection (original feature). Low-frequency spectral flux onset
   detection sends an OSC pulse on every detected beat, to a QLC+ "Cue
   List" widget's "Next Cue" external input, so a Chaser's steps advance
   in time with the music -- fully automatic, no human interaction
   required. Unrelated to feature 2 below, still OSC-based, unchanged.

2. Auto-layer (--auto). RMS-based intensity classification into 4 bands
   (Fade / Direkt / Alternierend / Alternierend mit Aus), with dwell-time
   hysteresis to avoid flapping at band boundaries. Deployment target is
   an unattended Raspberry Pi operated remotely via QLC+'s own Web
   Access (tablet browser) -- so this script must observe and drive the
   same "Auto <Farbe>" / layer buttons the tablet uses, not require a
   local keyboard/terminal.

   Uses QLC+ Web Access's own WebSocket protocol for this (ws://<host>:
   <web-port>/qlcplusWS, default port 9999) -- the exact channel the
   tablet's browser page itself uses, confirmed against
   webaccess/src/webaccess.cpp and webaccess/res/websocket.js at the
   QLC+_4.14.4 tag:
     - Press a button:   send "<widgetID>|1", then "<widgetID>|0"
       (goes straight to VCButton::pressFunction()/releaseFunction(),
       identical to a mouse click or a tablet tap).
     - State broadcast:  "<widgetID>|BUTTON|255" (Active) / "127"
       (Monitoring) / "0" (Inactive), pushed to every connected client
       whenever VCButton::stateChanged fires, from any cause.
   No OSC External Input, no Auto-Detect wizard, no QLC+ Feedback
   checkbox needed for any of this -- addressing is by plain widget ID
   from the .qxw, not a hashed/negotiated OSC channel.

   (An earlier version of this script tried OSC feedback instead
   (VCButton -> updateFeedback() -> OSCController) and separately a
   terminal-keypress color selector. Both abandoned: OSC feedback never
   arrived despite every prerequisite checking out in a long live-debug
   session -- see CLAUDE.md for the full writeup -- and a terminal
   selector doesn't fit the tablet-operated, unattended-Pi deployment
   at all. The Web Access WebSocket protocol above is the one QLC+
   feature that's actually built for exactly this job.)

See ../README.md for setup and ../CLAUDE.md's "Sound-to-Light wiring"
section for background.
"""

import argparse
import os
import queue
import socket
import threading
import time

import numpy as np
import pyaudio
import websocket
from pythonosc.udp_client import SimpleUDPClient

RATE = 44100
CHUNK = 1024
# The USB mic only exposes native 16-bit stereo capture (confirmed via
# `arecord -D hw:X,0 -f S16_LE -c 2 ...`, which runs cleanly, vs. a
# float32/mono open here which forces PortAudio to do the format+channel
# conversion in software -- suspected cause of a hang where the capture
# stream's internal poll() never returns again after some chunks, no
# error, no crash, confirmed independent of ALSA/hardware since raw
# `arecord` in the native format never hung). Open in the native format
# and downmix to mono float ourselves instead of asking PortAudio to.
CHANNELS = 2
FORMAT = pyaudio.paInt16

# Restrict spectral flux to a low-frequency band, since kicks/bass carry
# most of the rhythmic information in typical dance/pop music.
BAND_LOW_HZ = 40
BAND_HIGH_HZ = 200

HISTORY_SIZE = 43  # ~1s of history at ~23ms/chunk

COLORS = ["blau-rosa", "rot-weiss", "gruen-gelb", "blau-gelb", "bunt"]
# Ordered quiet -> intense; index == intensity band.
LAYERS = ["fade", "direkt", "alternierend", "altaus"]

# Virtual Console widget IDs, from qlcplus4/2026-07_kulturlichtung_v6.qxw.
# Auto row: SoloFrame 147, Buttons 148-152.
AUTO_BUTTON_ID = {
    "blau-rosa": 148,
    "rot-weiss": 149,
    "gruen-gelb": 150,
    "blau-gelb": 151,
    "bunt": 152,
}
# Fade/Direkt/Alternierend/Alternierend-mit-Aus rows, all under SoloFrame 90.
LAYER_BUTTON_ID = {
    "blau-rosa": {"fade": 115, "direkt": 91, "alternierend": 119, "altaus": 124},
    "rot-weiss": {"fade": 116, "direkt": 92, "alternierend": 120, "altaus": 125},
    "gruen-gelb": {"fade": 117, "direkt": 93, "alternierend": 121, "altaus": 126},
    "blau-gelb": {"fade": 113, "direkt": 94, "alternierend": 114, "altaus": 127},
    "bunt": {"fade": 118, "direkt": 95, "alternierend": 122, "altaus": 128},
}


def sd_notify(message):
    """Send a message to systemd's NOTIFY_SOCKET (sd_notify protocol),
    stdlib-only (no python-sdnotify dependency needed for two message
    types). No-op if not run under systemd (NOTIFY_SOCKET unset) --
    e.g. when run directly for --list-devices or local testing.

    Used for a Type=notify watchdog: the mic-capture hang documented in
    CLAUDE.md ("Beat detection silently hanging mid-session") leaves the
    process alive but stuck inside a blocking ALSA read -- it never
    crashes or exits, so plain Restart=on-failure can't detect it. A
    heartbeat sent right after each successful stream.read() naturally
    stops the moment that read blocks forever, so systemd's own
    WatchdogSec catches the hang and restarts the unit -- self-healing
    for the symptom while the root cause (see CLAUDE.md) is still being
    chased separately.
    """
    notify_socket = os.environ.get("NOTIFY_SOCKET")
    if not notify_socket:
        return
    if notify_socket.startswith("@"):
        notify_socket = "\0" + notify_socket[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.sendto(message.encode(), notify_socket)
    except OSError:
        pass


def list_devices():
    pa = pyaudio.PyAudio()
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0:
            print(f"[{i}] {info['name']} "
                  f"(in: {info['maxInputChannels']}, "
                  f"default sr: {int(info['defaultSampleRate'])})")
    pa.terminate()


def send_beat_press(osc, address):
    # QLC+'s External Input only fires on a press edge (value going
    # nonzero). Send a real press+release pulse every time, not a
    # persisted 1.0/0.0 toggle, so every call is its own edge.
    osc.send_message(address, 1.0)
    osc.send_message(address, 0.0)


class WebAccessState:
    """Tracks Auto/layer button state from QLC+ Web Access's WebSocket
    broadcasts. Never guesses or holds state QLC+ doesn't agree with --
    a tablet tap updates it exactly like this script's own presses do.
    Plain dict writes are atomic under the GIL, which is all the safety
    needed across the WebSocket thread and the main audio loop.
    """

    def __init__(self):
        self.auto = {c: False for c in COLORS}
        self.layer = {c: {l: False for l in LAYERS} for c in COLORS}
        self._auto_id_to_color = {v: k for k, v in AUTO_BUTTON_ID.items()}
        self._layer_id_to_key = {
            wid: (c, l)
            for c in COLORS
            for l, wid in LAYER_BUTTON_ID[c].items()
        }

    def handle_button(self, widget_id, value):
        on = value == 255
        if widget_id in self._auto_id_to_color:
            color = self._auto_id_to_color[widget_id]
            if on != self.auto[color]:
                print(f"[state] Auto {color}: {'ON' if on else 'off'}")
            self.auto[color] = on
        elif widget_id in self._layer_id_to_key:
            color, layer = self._layer_id_to_key[widget_id]
            if on != self.layer[color][layer]:
                print(f"[state] Layer {color}/{layer}: "
                      f"{'ON' if on else 'off'}")
            self.layer[color][layer] = on

    def active_auto_color(self):
        for c in COLORS:
            if self.auto[c]:
                return c
        return None

    def active_layer(self, color):
        for l in LAYERS:
            if self.layer[color][l]:
                return l
        return None


class QLCWebSocket:
    """Thin wrapper around QLC+ Web Access's WebSocket endpoint.

    Reconnects on drop (mirrors websocket.js's own 1s retry loop) since
    this is meant to run unattended for an entire event on the Pi.

    send_press() is called from the main audio-capture loop (via
    run_auto_layer_step) and must never block it -- a stalled/half-dead
    socket blocking indefinitely here previously froze the whole capture
    loop (no more beat/intensity processing at all, no crash, no log)
    the instant the first layer-switch press was attempted. Actual
    socket I/O is now done only by a dedicated sender thread, with a
    bounded timeout so a bad send fails loud instead of hanging forever;
    send_press() itself just enqueues and returns immediately.
    """

    def __init__(self, url, on_button, startup_auto_color=None):
        self.url = url
        self.on_button = on_button
        self._ws = None
        self._connected = threading.Event()
        self._startup_widget_id = AUTO_BUTTON_ID.get(startup_auto_color)
        self._startup_done = False
        self._send_queue = queue.Queue()

    def _on_open(self, ws):
        print(f"[ws] connected to {self.url}")
        self._connected.set()
        if self._startup_widget_id is not None and not self._startup_done:
            # Pre-select a color at boot (e.g. for unattended Pi startup)
            # by pressing its Auto button once, same as a tablet tap.
            self.send_press(self._startup_widget_id)
            self._startup_done = True

    def _on_close(self, ws, close_status_code, close_msg):
        print("[ws] connection closed, will retry in 1s")
        self._connected.clear()

    def _on_error(self, ws, error):
        print(f"[ws] error: {error}")

    def _on_message(self, ws, message):
        parts = message.split("|")
        if len(parts) >= 3 and parts[1] == "BUTTON":
            try:
                self.on_button(int(parts[0]), int(parts[2]))
            except ValueError:
                pass

    def run_forever(self):
        while True:
            self._ws = websocket.WebSocketApp(
                self.url, on_open=self._on_open, on_close=self._on_close,
                on_error=self._on_error, on_message=self._on_message)
            self._ws.run_forever()
            self._connected.clear()
            time.sleep(1)

    def send_press(self, widget_id):
        self._send_queue.put(widget_id)

    def sender_loop(self):
        while True:
            widget_id = self._send_queue.get()
            if not self._connected.is_set() or self._ws is None:
                print(f"[ws] not connected, dropping press for widget "
                      f"{widget_id}")
                continue
            try:
                # Bound the send instead of risking an indefinite block
                # on a half-dead/stalled socket -- a slow send now just
                # fails and logs, instead of freezing whoever's waiting
                # on this thread (nobody, now that this runs off the
                # audio loop -- but keep the bound anyway).
                if self._ws.sock is not None:
                    self._ws.sock.settimeout(2.0)
                self._ws.send(f"{widget_id}|1")
                self._ws.send(f"{widget_id}|0")
            except Exception as e:
                print(f"[ws] send failed for widget {widget_id}: {e}")


class IntensityClassifier:
    """RMS-based 4-band intensity classifier with dwell-time hysteresis.

    Classifies the *fast* (current, few-seconds) RMS level against a
    much *slower*-moving baseline EMA (minutes-scale), in dB, rather
    than against a single short rolling window's own mean/stddev. A
    single short window was tried first and doesn't work: once a loud
    section fills most of that window, the window's own mean/std shift
    up to match it, so "loud" reads as average relative to itself and
    the band never rises (confirmed with a synthetic quiet->loud test).
    A slow baseline that a normal-length loud section (order of the
    existing 30s Chaser Hold, or longer) can't itself drag up avoids
    that self-baselining trap.
    """

    def __init__(self, baseline_alpha, thresholds_db, ema_alpha,
                 band_hold_s):
        self.baseline_alpha = baseline_alpha
        self.thresholds_db = thresholds_db  # (d1, d2, d3), d1 < d2 < d3
        self.ema_alpha = ema_alpha
        self.band_hold_s = band_hold_s

        self.fast = None
        self.slow = None
        self.committed_band = 0
        self.candidate_band = None
        self.candidate_since = 0.0

    def update(self, samples):
        rms = float(np.sqrt(np.mean(np.square(samples))))
        self.fast = (rms if self.fast is None else
                     self.ema_alpha * rms + (1 - self.ema_alpha) * self.fast)
        self.slow = (rms if self.slow is None else
                     self.baseline_alpha * rms +
                     (1 - self.baseline_alpha) * self.slow)

        level_db = 20 * np.log10((self.fast + 1e-9) / (self.slow + 1e-9))
        candidate = sum(1 for t in self.thresholds_db if level_db > t)

        now = time.monotonic()
        if candidate != self.committed_band:
            if candidate != self.candidate_band:
                self.candidate_band = candidate
                self.candidate_since = now
            elif now - self.candidate_since >= self.band_hold_s:
                self.committed_band = candidate
                self.candidate_band = None
        else:
            self.candidate_band = None

        return self.committed_band, level_db


def run_auto_layer_step(ws_client, state, band):
    active_color = state.active_auto_color()
    if active_color is None:
        return
    desired_layer = LAYERS[band]
    current_layer = state.active_layer(active_color)
    if current_layer != desired_layer:
        widget_id = LAYER_BUTTON_ID[active_color][desired_layer]
        ws_client.send_press(widget_id)
        print(f"[auto] {active_color}: {current_layer} -> {desired_layer} "
              f"(widget {widget_id})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-devices", action="store_true",
                         help="List audio input devices and exit")
    parser.add_argument("--device", type=int, default=None,
                         help="Audio input device index (see --list-devices)")
    parser.add_argument("--host", default="127.0.0.1",
                         help="Host running QLC+ (OSC input and Web "
                              "Access). Default: 127.0.0.1 (script and "
                              "QLC+ on the same machine)")
    parser.add_argument("--port", type=int, default=7700,
                         help="OSC target port for beat detection "
                              "(default: 7700 -- must match the OSC "
                              "input line configured in QLC+'s "
                              "Input/Output Manager)")
    parser.add_argument("--address", default="/beat",
                         help="OSC address sent on each beat (default: "
                              "/beat)")
    parser.add_argument("--sensitivity", type=float, default=3.5,
                         help="Beat threshold = mean + sensitivity * "
                              "stddev of recent flux history. Lower "
                              "value = more (and more false-positive) "
                              "triggers.")
    parser.add_argument("--refractory-ms", type=int, default=200,
                         help="Minimum time between two detected beats, "
                              "in ms (200ms caps detection at 300 BPM, "
                              "prevents double-triggering on one hit)")

    parser.add_argument("--auto", action="store_true",
                         help="Enable intensity-based auto-layer "
                              "switching, driven entirely via QLC+ Web "
                              "Access's WebSocket -- pick the active "
                              "color's 'Auto' button from the tablet/"
                              "QLC+ itself, same as any other button")
    parser.add_argument("--web-port", type=int, default=9999,
                         help="QLC+ Web Access port (default: 9999, "
                              "QLC+'s own default -- start QLC+ with "
                              "-w/--web, or -wp/--web-port to override)")
    parser.add_argument("--startup-auto-color", choices=COLORS, default=None,
                         help="Press this color's 'Auto' button once, "
                              "right after connecting -- for unattended "
                              "boot on the Pi, so a color is auto-active "
                              "without anyone touching the tablet")
    parser.add_argument("--intensity-thresholds-db", type=float, nargs=3,
                         default=(1.5, 4.0, 8.0), metavar=("D1", "D2", "D3"),
                         help="3 ascending dB boundaries between fast "
                              "(current) and slow (baseline) level for "
                              "Fade/Direkt/Alternierend/AltAus "
                              "(default: 1.5 4.0 8.0)")
    parser.add_argument("--baseline-seconds", type=float, default=120.0,
                         help="Time constant (seconds) of the slow "
                              "baseline EMA -- must be well above a "
                              "typical loud section's length so that "
                              "section can't drag the baseline up to "
                              "match itself (default: 120)")
    parser.add_argument("--intensity-ema-alpha", type=float, default=0.15,
                         help="Smoothing factor for the fast intensity "
                              "level, 0-1, higher = more reactive "
                              "(default: 0.15)")
    parser.add_argument("--band-hold-ms", type=int, default=2000,
                         help="Minimum time a new intensity band must "
                              "persist before a layer switch is sent, to "
                              "avoid flapping at a boundary (default: "
                              "2000)")
    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        return

    osc = SimpleUDPClient(args.host, args.port)

    state = WebAccessState()
    ws_client = None
    if args.auto:
        ws_url = f"ws://{args.host}:{args.web_port}/qlcplusWS"
        ws_client = QLCWebSocket(ws_url, on_button=state.handle_button,
                                  startup_auto_color=args.startup_auto_color)
        thread = threading.Thread(target=ws_client.run_forever, daemon=True)
        thread.start()
        sender_thread = threading.Thread(target=ws_client.sender_loop,
                                          daemon=True)
        sender_thread.start()

    chunk_dt = CHUNK / RATE
    baseline_alpha = 1 - np.exp(-chunk_dt / args.baseline_seconds)
    classifier = IntensityClassifier(
        baseline_alpha=baseline_alpha,
        thresholds_db=tuple(args.intensity_thresholds_db),
        ema_alpha=args.intensity_ema_alpha,
        band_hold_s=args.band_hold_ms / 1000.0)

    def send_beat():
        send_beat_press(osc, args.address)

    pa = pyaudio.PyAudio()
    stream = pa.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                      input=True, input_device_index=args.device,
                      frames_per_buffer=CHUNK)

    freqs = np.fft.rfftfreq(CHUNK, d=1.0 / RATE)
    band_mask = (freqs >= BAND_LOW_HZ) & (freqs <= BAND_HIGH_HZ)

    prev_mag = None
    flux_history = []
    last_beat_time = 0.0
    last_committed_band = None

    print(f"Listening (device={args.device}), sending OSC {args.address} "
          f"to {args.host}:{args.port} on each detected beat. "
          f"Ctrl+C to stop.")
    sd_notify("READY=1")
    last_watchdog_notify = time.monotonic()

    try:
        while True:
            raw = stream.read(CHUNK, exception_on_overflow=False)
            stereo = np.frombuffer(raw, dtype=np.int16).reshape(-1, CHANNELS)
            samples = stereo.mean(axis=1).astype(np.float32) / 32768.0

            # Sent right after stream.read() returns -- if that call
            # ever blocks forever (the hang this guards against), this
            # heartbeat simply stops, and systemd's WatchdogSec notices.
            now = time.monotonic()
            if now - last_watchdog_notify >= 2.0:
                sd_notify("WATCHDOG=1")
                last_watchdog_notify = now

            spectrum = np.fft.rfft(samples)
            mag = np.abs(spectrum)

            if prev_mag is not None:
                flux = np.sum(
                    np.maximum(0, mag[band_mask] - prev_mag[band_mask])
                )

                flux_history.append(flux)
                if len(flux_history) > HISTORY_SIZE:
                    flux_history.pop(0)

                if len(flux_history) >= HISTORY_SIZE:
                    mean = np.mean(flux_history)
                    std = np.std(flux_history)
                    threshold = mean + args.sensitivity * std

                    now = time.monotonic()
                    since_last_ms = (now - last_beat_time) * 1000
                    if (flux > threshold and flux > 0
                            and since_last_ms >= args.refractory_ms):
                        last_beat_time = now
                        send_beat()
                        print(f"beat  flux={flux:.1f}  "
                              f"threshold={threshold:.1f}")

            prev_mag = mag

            if args.auto:
                band, level_db = classifier.update(samples)
                if band != last_committed_band:
                    print(f"[intensity] band -> {LAYERS[band]} "
                          f"(level={level_db:+.1f} dB)")
                    last_committed_band = band
                run_auto_layer_step(ws_client, state, band)

    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()


if __name__ == "__main__":
    main()
