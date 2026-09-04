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


ALL_TRACKED_WIDGET_IDS = list(AUTO_BUTTON_ID.values()) + [
    wid for layers in LAYER_BUTTON_ID.values() for wid in layers.values()
]


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

    On connect, queries the real current state of every Auto/layer
    button (QLC+API|getWidgetStatus, confirmed against webaccess.cpp at
    the QLC+_4.14.4 tag) instead of assuming everything starts off. This
    replaces an earlier version that blindly pressed --startup-auto-color's
    Auto button on every connect: since these are Action=Toggle buttons,
    a press after a process restart (e.g. a watchdog-triggered restart of
    *this* script -- QLC+ itself keeps running and keeps its state) could
    silently flip an already-active Auto back off. See run_invariant_loop
    for what actually presses buttons based on this state now.

    Confirmed live 2026-09-04: QLC+ Web Access does not broadcast a
    state-change back to the socket that itself caused the change --
    only to *other* connected clients (a tablet). This script's own
    presses therefore never self-confirm via broadcast; sender_loop()
    applies the resulting state locally instead of waiting on one (see
    its comment for why that's safe for every press this script sends).
    """

    def __init__(self, url, on_button):
        self.url = url
        self.on_button = on_button
        self._ws = None
        self._connected = threading.Event()
        self._send_queue = queue.Queue()

    def _on_open(self, ws):
        print(f"[ws] connected to {self.url}")
        self._connected.set()
        # Sync local state with QLC+'s actual state before anything
        # decides whether to press a button -- see class docstring.
        for widget_id in ALL_TRACKED_WIDGET_IDS:
            self.query_status(widget_id)

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
        elif (len(parts) >= 4 and parts[0] == "QLC+API"
                and parts[1] == "getWidgetStatus"):
            # Reply to our own query_status() -- same wID|status shape
            # as a BUTTON broadcast, so it's fed through the same
            # on_button callback (WebAccessState.handle_button).
            try:
                self.on_button(int(parts[2]), int(parts[3]))
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
        self._send_queue.put(("press", widget_id))

    def query_status(self, widget_id):
        self._send_queue.put(("query", widget_id))

    def sender_loop(self):
        while True:
            kind, widget_id = self._send_queue.get()
            if not self._connected.is_set() or self._ws is None:
                print(f"[ws] not connected, dropping {kind} for widget "
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
                if kind == "press":
                    self._ws.send(f"{widget_id}|1")
                    self._ws.send(f"{widget_id}|0")
                    # QLC+ Web Access does NOT echo a state-change broadcast
                    # back to the socket that caused it (confirmed live
                    # 2026-09-04: a tablet tap on a different client reliably
                    # produced a [state] log line, this script's own presses
                    # never did, in a 10+ minute window) -- only reported by
                    # our own docstrings as an assumption before this. Every
                    # send_press() call in this script is only ever used to
                    # turn something ON (Auto button, layer button), so we
                    # can safely apply that as our own local state the
                    # instant the send succeeds, instead of waiting forever
                    # for a broadcast that will never arrive for a
                    # self-triggered change.
                    self.on_button(widget_id, 255)
                else:
                    self._ws.send(f"QLC+API|getWidgetStatus|{widget_id}")
            except Exception as e:
                print(f"[ws] send failed for {kind} widget {widget_id}: {e}")


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

    def __init__(self, live_config):
        # Reads live_config.* fresh every update() call (not cached at
        # construction) so the tuning web UI's edits take effect
        # immediately -- see web_ui.LiveConfig.
        self.live_config = live_config

        self.fast = None
        self.slow = None
        self.committed_band = 0
        self.candidate_band = None
        self.candidate_since = 0.0

    def update(self, samples):
        lc = self.live_config
        rms = float(np.sqrt(np.mean(np.square(samples))))
        self.fast = (rms if self.fast is None else
                     lc.intensity_ema_alpha * rms +
                     (1 - lc.intensity_ema_alpha) * self.fast)
        self.slow = (rms if self.slow is None else
                     lc.baseline_alpha * rms +
                     (1 - lc.baseline_alpha) * self.slow)

        level_db = 20 * np.log10((self.fast + 1e-9) / (self.slow + 1e-9))
        # thresholds_db is kept ascending by LiveConfig's own setter (a
        # web-UI drag can momentarily cross two handles; sorting there,
        # not here, is what makes this sum() meaningful).
        candidate = sum(1 for t in lc.intensity_thresholds_db if level_db > t)

        now = time.monotonic()
        if candidate != self.committed_band:
            if candidate != self.candidate_band:
                self.candidate_band = candidate
                self.candidate_since = now
            elif now - self.candidate_since >= lc.band_hold_s:
                self.committed_band = candidate
                self.candidate_band = None
        else:
            self.candidate_band = None

        return self.committed_band, level_db


# A fixed dB offset above/below the outermost thresholds, used only to
# give band 0 ("below D1") and band 3 ("above D3") a concrete reference
# point for the display line below -- see band_reference_levels().
BAND_REF_MARGIN_DB = 2.0


def band_reference_levels(thresholds_db):
    """One reference dB value per intensity band (0-3): the midpoint of
    that band's own range, or BAND_REF_MARGIN_DB beyond the outermost
    threshold for the two open-ended bands. Used to turn a possibly
    fractional "how far between band A and band B" progress value (see
    the display-level comment in main()) into an actual chart y-position.
    """
    t1, t2, t3 = thresholds_db
    return [t1 - BAND_REF_MARGIN_DB, (t1 + t2) / 2,
            (t2 + t3) / 2, t3 + BAND_REF_MARGIN_DB]


LAYER_PRESS_COOLDOWN_S = 1.0


def run_auto_layer_step(ws_client, state, band, last_command, last_command_lock):
    """last_command: {color: (desired_layer, monotonic_time_sent)}, mutated
    in place across calls. last_command_lock guards every check-then-act
    on it -- see the note on run_invariant_loop below for why a plain
    dict isn't enough even though individual get/set calls are GIL-atomic.

    Called every audio-loop tick (~23ms). QLC+'s Web Access feedback
    round-trip (state.active_layer() only updates once the button-press
    broadcast comes back) takes much longer than one tick, so comparing
    only against the *confirmed* state every tick re-fires a fresh press
    on every single tick until confirmation catches up -- and since these
    are Action=Toggle buttons, each extra press flips it again. An even
    number of these before confirmation arrives leaves the layer back off
    (reproduced live: logged 3 presses for one transition, net state
    landed on/off unpredictably by parity of how many got sent). Debounce
    by remembering what was last *commanded* for this color and not
    re-sending the same target again until either it's confirmed or
    LAYER_PRESS_COOLDOWN_S has passed (long enough for a normal round
    trip, short enough to retry a dropped press) -- still re-fires
    immediately for a genuinely new desired_layer, or if a human's own
    tablet tap changes the confirmed layer to something else.
    """
    active_color = state.active_auto_color()
    if active_color is None:
        return
    desired_layer = LAYERS[band]
    current_layer = state.active_layer(active_color)
    if current_layer == desired_layer:
        return
    with last_command_lock:
        prev_layer, prev_time = last_command.get(active_color, (None, 0.0))
        now = time.monotonic()
        if prev_layer == desired_layer and (now - prev_time) < LAYER_PRESS_COOLDOWN_S:
            return
        last_command[active_color] = (desired_layer, now)
    widget_id = LAYER_BUTTON_ID[active_color][desired_layer]
    ws_client.send_press(widget_id)
    print(f"[auto] {active_color}: {current_layer} -> {desired_layer} "
          f"(widget {widget_id})")


STARTUP_GRACE_S = 5.0


def run_invariant_loop(ws_client, state, startup_auto_color, last_command,
                        last_command_lock):
    """Independent safety-net thread, decoupled from the audio-capture
    loop on purpose -- so it keeps enforcing even if that loop is stuck
    in the still-unexplained mic-read hang documented in CLAUDE.md
    ("Beat detection silently hanging mid-session"). That hang is the
    likely explanation for "Auto activates on boot but the light often
    doesn't come on": the WebSocket thread that turns Auto on is
    independent of the audio thread, so Auto can end up confirmed ON
    while run_auto_layer_step (which only runs inside the audio loop's
    tick) never got a chance to press the matching layer button, e.g.
    because the loop hung before its first iteration during boot, right
    when USB audio is still settling.

    Two responsibilities, checked every 2s:
    1. --startup-auto-color: after a grace period for the connect-time
       getWidgetStatus queries to come back (see QLCWebSocket docstring),
       press that color's Auto button *only if* no color's Auto is
       confirmed active yet -- avoids blindly toggling an Auto that's
       already on from a prior run (a plain restart of this script does
       not restart QLC+, so its state persists across that restart).
    2. Whichever color currently has Auto confirmed active: if it has no
       layer confirmed active at all, press Fade as the default. Never
       touches an already-active layer -- that's run_auto_layer_step's
       job, driven by live intensity. This only fills the gap where
       Auto is on and *nothing* underneath it is running.

    last_command_lock is the *same* lock run_auto_layer_step uses:
    both threads do a check-then-act ("no fade commanded yet for this
    color" -> send press -> record it) against the shared last_command
    dict, and a plain dict's per-call atomicity doesn't cover that whole
    sequence. Without the lock, this loop's ~2s tick and the audio
    thread's ~23ms tick can both observe "not yet commanded" for the same
    color/layer at the same time and both fire a press -- two press+
    release toggles back to back on an Action=Toggle button cancel out
    to OFF net, which looks exactly like "the layer never came on" even
    though a press genuinely went out. Confirmed as a real gap 2026-09-04
    after a live Pi boot left Auto active with no layer lit.
    """
    start = time.monotonic()
    startup_done = False
    while True:
        time.sleep(2.0)

        if startup_auto_color and not startup_done:
            if time.monotonic() - start >= STARTUP_GRACE_S:
                if state.active_auto_color() is None:
                    widget_id = AUTO_BUTTON_ID[startup_auto_color]
                    ws_client.send_press(widget_id)
                    print(f"[invariant] no Auto color confirmed active "
                          f"after boot, pressing Auto {startup_auto_color} "
                          f"(widget {widget_id})")
                startup_done = True

        active_color = state.active_auto_color()
        if active_color is None:
            continue
        if state.active_layer(active_color) is not None:
            continue

        with last_command_lock:
            prev_layer, prev_time = last_command.get(active_color, (None, 0.0))
            now = time.monotonic()
            if (prev_layer == "fade"
                    and (now - prev_time) < LAYER_PRESS_COOLDOWN_S):
                continue
            last_command[active_color] = ("fade", now)
        widget_id = LAYER_BUTTON_ID[active_color]["fade"]
        ws_client.send_press(widget_id)
        print(f"[invariant] Auto {active_color} active with no layer, "
              f"forcing fade (widget {widget_id})")


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
    parser.add_argument("--default-sensitivity", type=float, default=3.1,
                         help="Value the tuning web UI's 'reset to "
                              "default' button sets --sensitivity to "
                              "(default: 3.1). Purely a reset target -- "
                              "does not itself change the live starting "
                              "value, that's still --sensitivity")
    parser.add_argument("--default-intensity-thresholds-db", type=float,
                         nargs=3, default=(0.7, 2.5, 8.0),
                         metavar=("D1", "D2", "D3"),
                         help="Values the tuning web UI's 'reset to "
                              "default' button sets "
                              "--intensity-thresholds-db to (default: "
                              "0.7 2.5 8.0)")
    parser.add_argument("--audio-backend", choices=("pyaudio", "alsaaudio"),
                         default="pyaudio",
                         help="Audio capture backend. 'pyaudio' (default) "
                              "is the normal PortAudio path. 'alsaaudio' "
                              "bypasses PortAudio entirely and talks to "
                              "ALSA directly (pyalsaaudio) -- diagnostic "
                              "bisection for the still-unexplained capture "
                              "hang documented in CLAUDE.md ('Beat "
                              "detection silently hanging mid-session'): "
                              "raw `arecord` in this format never hangs, "
                              "PyAudio/PortAudio does -- this backend "
                              "tests whether pyalsaaudio, a much thinner "
                              "wrapper around the same ALSA calls arecord "
                              "uses, hangs too or not")
    parser.add_argument("--alsa-device", default="hw:2,0",
                         help="ALSA device string for --audio-backend "
                              "alsaaudio, e.g. hw:2,0 (see `arecord -l` "
                              "for the card/device numbers -- NOT the "
                              "same numbering as --device/--list-devices, "
                              "which is PyAudio's own index)")

    parser.add_argument("--web-ui", action="store_true",
                         help="Enable the tuning web UI (live charts + "
                              "draggable threshold lines for sensitivity "
                              "and the 3 intensity-band boundaries). "
                              "Opt-in, mirrors --auto -- a plain local "
                              "test run doesn't unexpectedly open a "
                              "network port, and aiohttp is only "
                              "imported if this is set")
    parser.add_argument("--ui-host", default="0.0.0.0",
                         help="Bind address for the tuning web UI "
                              "(default: 0.0.0.0, so a tablet on the "
                              "Pi's own hotspot can reach it -- use "
                              "127.0.0.1 for local-only testing)")
    parser.add_argument("--ui-port", type=int, default=8080,
                         help="Port for the tuning web UI (default: "
                              "8080, unprivileged -- the Pi's own conf "
                              "overrides this to 80 for real deployment, "
                              "which needs CAP_NET_BIND_SERVICE, see "
                              "pi-setup/beat-osc.service)")
    parser.add_argument("--config-file", default=None,
                         help="Path to lichtsteuerung.conf, so edits "
                              "made in the tuning web UI persist back "
                              "to it. Without this, edits stay "
                              "live-only (in-memory) and are lost on "
                              "restart")
    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        return

    osc = SimpleUDPClient(args.host, args.port)

    state = WebAccessState()
    ws_client = None
    last_layer_command = {}
    last_layer_command_lock = threading.Lock()
    if args.auto:
        ws_url = f"ws://{args.host}:{args.web_port}/qlcplusWS"
        ws_client = QLCWebSocket(ws_url, on_button=state.handle_button)
        thread = threading.Thread(target=ws_client.run_forever, daemon=True)
        thread.start()
        sender_thread = threading.Thread(target=ws_client.sender_loop,
                                          daemon=True)
        sender_thread.start()
        invariant_thread = threading.Thread(
            target=run_invariant_loop,
            args=(ws_client, state, args.startup_auto_color,
                  last_layer_command, last_layer_command_lock),
            daemon=True)
        invariant_thread.start()

    chunk_dt = CHUNK / RATE

    metrics_queue = None
    if args.web_ui:
        import web_ui  # lazy: no hard aiohttp dependency unless --web-ui
        live_config = web_ui.LiveConfig(
            sensitivity=args.sensitivity,
            intensity_thresholds_db=args.intensity_thresholds_db,
            band_hold_ms=args.band_hold_ms,
            intensity_ema_alpha=args.intensity_ema_alpha,
            baseline_seconds=args.baseline_seconds,
            chunk_dt=chunk_dt,
            default_sensitivity=args.default_sensitivity,
            default_intensity_thresholds_db=
                args.default_intensity_thresholds_db)
        metrics_queue = queue.Queue(maxsize=4)
        web_ui.start_web_ui_thread(
            host=args.ui_host, port=args.ui_port, live_config=live_config,
            metrics_queue=metrics_queue, config_file=args.config_file)
    else:
        # No web UI -- a plain namespace with the same attributes
        # IntensityClassifier reads, so it doesn't need to know or care
        # whether live editing is available.
        class _StaticConfig:
            pass
        live_config = _StaticConfig()
        live_config.sensitivity = args.sensitivity
        live_config.intensity_thresholds_db = tuple(
            sorted(args.intensity_thresholds_db))
        live_config.band_hold_s = args.band_hold_ms / 1000.0
        live_config.intensity_ema_alpha = args.intensity_ema_alpha
        live_config.baseline_alpha = 1 - np.exp(
            -chunk_dt / args.baseline_seconds)

    classifier = IntensityClassifier(live_config)

    def send_beat():
        send_beat_press(osc, args.address)

    if args.audio_backend == "alsaaudio":
        import alsaaudio
        pcm = alsaaudio.PCM(alsaaudio.PCM_CAPTURE, alsaaudio.PCM_NORMAL,
                             device=args.alsa_device)
        pcm.setchannels(CHANNELS)
        pcm.setrate(RATE)
        pcm.setformat(alsaaudio.PCM_FORMAT_S16_LE)
        pcm.setperiodsize(CHUNK)

        def read_chunk():
            # length != CHUNK (a partial period, or <0 on an ALSA-level
            # error/xrun) would desync the FFT size below -- drop that
            # chunk rather than risk a shape mismatch against band_mask.
            length, data = pcm.read()
            if length != CHUNK:
                return None
            return data
    else:
        pa = pyaudio.PyAudio()
        stream = pa.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                          input=True, input_device_index=args.device,
                          frames_per_buffer=CHUNK)

        def read_chunk():
            return stream.read(CHUNK, exception_on_overflow=False)

    freqs = np.fft.rfftfreq(CHUNK, d=1.0 / RATE)
    band_mask = (freqs >= BAND_LOW_HZ) & (freqs <= BAND_HIGH_HZ)

    prev_mag = None
    flux_history = []
    last_beat_time = 0.0
    last_committed_band = None
    last_metrics_push = 0.0
    # last_layer_command is shared with run_invariant_loop (passed in
    # above) -- same dict object, so both callers' cooldown checks agree
    # on what was last commanded per color and never double-fire the
    # same target.

    print(f"Listening (device={args.device}), sending OSC {args.address} "
          f"to {args.host}:{args.port} on each detected beat. "
          f"Ctrl+C to stop.")
    sd_notify("READY=1")
    last_watchdog_notify = time.monotonic()

    try:
        while True:
            raw = read_chunk()
            if raw is None:
                continue
            stereo = np.frombuffer(raw, dtype=np.int16).reshape(-1, CHANNELS)
            samples = stereo.mean(axis=1).astype(np.float32) / 32768.0

            # Sent right after read_chunk() returns -- if that call ever
            # blocks forever (the hang this guards against), this
            # heartbeat simply stops, and systemd's WatchdogSec notices.
            now = time.monotonic()
            if now - last_watchdog_notify >= 2.0:
                sd_notify("WATCHDOG=1")
                last_watchdog_notify = now

            spectrum = np.fft.rfft(samples)
            mag = np.abs(spectrum)

            # None until flux_history has enough samples (~1s of
            # startup) -- expected, not a bug; the web UI sends these
            # through as null for that brief warm-up window.
            flux = mean = std = threshold = None
            beat_fired = False
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
                    threshold = mean + live_config.sensitivity * std

                    since_last_ms = (now - last_beat_time) * 1000
                    if (flux > threshold and flux > 0
                            and since_last_ms >= args.refractory_ms):
                        last_beat_time = now
                        beat_fired = True
                        send_beat()
                        print(f"beat  flux={flux:.1f}  "
                              f"threshold={threshold:.1f}")

            prev_mag = mag

            # Classification always runs (not just under --auto) so the
            # tuning web UI's intensity chart has live data even when
            # auto-layer switching itself is off. Only the actual QLC+
            # button press (run_auto_layer_step) stays gated on --auto.
            band, level_db = classifier.update(samples)
            # Chart-display value (replaces an earlier hold-progress-bar
            # UI, then an earlier still low-pass filter on raw level_db --
            # see CLAUDE.md's "Tuning web UI" section for why both of
            # those were superseded). A generic low-pass filter on the raw
            # signal turned out to *not* reliably track the real decision:
            # the actual commit requires the exact same candidate band
            # persisting continuously for band_hold_s, but raw level_db is
            # noisy enough that the candidate band itself flickers between
            # values without ever holding one long enough to commit, even
            # while its filtered average trends steadily upward -- exactly
            # the mismatch reported live (chart implied Stufe 2/3, real
            # system stayed on Stufe 1). Fixed by deriving the display
            # value directly from the same ground-truth state that drives
            # the real decision (classifier.candidate_band/.candidate_since),
            # instead of independently re-deriving something similar from
            # raw level_db: while no candidate is pending, show the real,
            # noisy level_db (nothing is building, no ramp to show); the
            # instant a candidate starts, override with a deterministic
            # ramp between the current and candidate band's reference
            # level, in exact lockstep with the real hold timer -- so it
            # can only ever finish rising at the same moment the real
            # system commits, by construction, not approximation.
            candidate_band = classifier.candidate_band
            if candidate_band is None:
                display_level = level_db
            else:
                refs = band_reference_levels(live_config.intensity_thresholds_db)
                frac = min(1.0, (now - classifier.candidate_since)
                           / max(live_config.band_hold_s, 1e-6))
                display_level = refs[band] + frac * (refs[candidate_band] - refs[band])
            if band != last_committed_band:
                print(f"[intensity] band -> {LAYERS[band]} "
                      f"(level={level_db:+.1f} dB)")
                last_committed_band = band
            if args.auto:
                run_auto_layer_step(ws_client, state, band, last_layer_command,
                                     last_layer_command_lock)

            # Pushed unthrottled (bypassing the 100ms gate below) on every
            # detected beat, in addition to the regular throttled push --
            # the chart's ~10Hz sampling otherwise misses most beat spikes
            # entirely, since a single knock's flux spike lasts only one
            # ~23ms chunk (see CLAUDE.md's "Tuning web UI" section for the
            # user-reported symptom this fixes: chart implied beats almost
            # never crossed the threshold, while QLC+ visibly advanced on
            # every real beat). Forcing a sample at the exact chunk that
            # crossed threshold guarantees the chart shows it, and
            # `beat=True` lets the client mark that point distinctly.
            if args.web_ui and (beat_fired or now - last_metrics_push >= 0.1):
                web_ui.push_metrics_nowait(
                    metrics_queue, t=now,
                    flux=float(flux) if flux is not None else None,
                    mean=float(mean) if mean is not None else None,
                    std=float(std) if std is not None else None,
                    threshold=(float(threshold)
                               if threshold is not None else None),
                    level_db=float(display_level), band=int(band),
                    beat=beat_fired)
                last_metrics_push = now

    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        if args.audio_backend == "alsaaudio":
            if hasattr(pcm, "close"):
                pcm.close()
        else:
            stream.stop_stream()
            stream.close()
            pa.terminate()


if __name__ == "__main__":
    main()
