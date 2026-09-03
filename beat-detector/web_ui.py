"""Tuning web UI for beat_osc.py -- live charts + editable thresholds.

Runs an aiohttp HTTP+WebSocket server in its own thread with its own
asyncio event loop, alongside beat_osc.py's audio-capture thread and its
QLCWebSocket threads. Same isolation pattern already established for
QLCWebSocket in beat_osc.py: blocking I/O (here: the aiohttp event loop,
and file I/O for config persistence) never runs on the audio thread, and
the audio thread never blocks on this module -- see push_metrics_nowait.

Imported lazily by beat_osc.py, only when --web-ui is passed, so aiohttp
is not a hard dependency for users who never use this feature (mirrors
the existing lazy `import alsaaudio` for --audio-backend alsaaudio).

See CLAUDE.md's "Tuning web UI" section for the design rationale (why
aiohttp, why no lock on LiveConfig, why the config file rewrite is
atomic, why the beat-detection threshold line has to be inverted into a
sensitivity value client-side).
"""

import asyncio
import contextlib
import json
import math
import os
import queue
import re
import tempfile
import threading

from aiohttp import web

SENSITIVITY_MIN, SENSITIVITY_MAX = 0.1, 10.0
THRESH_MIN_DB, THRESH_MAX_DB = -20.0, 40.0
PERSIST_DEBOUNCE_S = 0.75
QLC_WEB_ACCESS_PORT = 9999  # QLC+'s own documented default (-wp), see README

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

_CONF_LINE_RE = re.compile(r'^([A-Z_][A-Z0-9_]*)="([^"]*)"\s*$')


class LiveConfig:
    """Mutable run-time config: read every audio-loop tick (~23ms) by
    IntensityClassifier/main(), written from the web-UI thread on every
    edit. Plain attributes, no lock -- same GIL-atomic-write reasoning
    already used for WebAccessState/last_command in beat_osc.py: every
    individual assignment (a float, or a whole new tuple for the 3
    thresholds) is a single atomic STORE_ATTR, so a reader mid-tick
    always sees either the old or the new value, never a torn one. No
    caller reads baseline_seconds and baseline_alpha jointly in the same
    expression, so there's no way to observe a mismatched pair either.
    """

    def __init__(self, sensitivity, intensity_thresholds_db, band_hold_ms,
                 intensity_ema_alpha, baseline_seconds, chunk_dt):
        self.sensitivity = sensitivity
        self.intensity_thresholds_db = tuple(sorted(intensity_thresholds_db))
        self.band_hold_s = band_hold_ms / 1000.0
        self.intensity_ema_alpha = intensity_ema_alpha
        self._chunk_dt = chunk_dt
        self.baseline_seconds = baseline_seconds
        self.baseline_alpha = 1 - math.exp(-chunk_dt / baseline_seconds)

    def set_sensitivity(self, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return
        self.sensitivity = min(max(value, SENSITIVITY_MIN), SENSITIVITY_MAX)

    def set_intensity_thresholds_db(self, values):
        try:
            vals = [min(max(float(v), THRESH_MIN_DB), THRESH_MAX_DB)
                    for v in values]
        except (TypeError, ValueError):
            return
        if len(vals) != 3:
            return
        # Always sort, never reject -- a drag can momentarily cross two
        # handles (normal UX), and IntensityClassifier.update()'s
        # sum(1 for t in thresholds if level_db > t) requires ascending
        # order to mean anything at all. Sorting here is what makes
        # that correct, not just tidy.
        self.intensity_thresholds_db = tuple(sorted(vals))

    def as_dict(self):
        return {
            "sensitivity": self.sensitivity,
            "intensity_thresholds_db": list(self.intensity_thresholds_db),
        }


def read_conf_values(path):
    """KEY="value" lines only; ignores comments/blanks/anything else.
    Not a bash interpreter (no $VAR expansion, no unquoted values) --
    lichtsteuerung.conf never needs those.
    """
    values = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = _CONF_LINE_RE.match(line.rstrip("\n"))
            if m:
                values[m.group(1)] = m.group(2)
    return values


def update_conf_file(path, updates):
    """Rewrite `path`, replacing the value of each key in `updates` on
    its existing line; every other line (comments, blanks, unrelated
    keys, order) is preserved byte-for-byte. Keys in `updates` not
    already present as a KEY="..." line are silently skipped -- this
    only ever edits keys the user's own conf already declares.

    Atomic: temp file in the same directory (same filesystem, so
    os.replace() is a rename not a copy) + fsync + os.replace() over
    the original -- survives a power cut mid-write, important since
    this file lives on an exFAT USB stick this Pi is designed to be
    power-cut, not cleanly shut down (see README/CLAUDE.md).
    """
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    remaining = dict(updates)
    out = []
    for line in lines:
        m = _CONF_LINE_RE.match(line.rstrip("\n"))
        if m and m.group(1) in remaining:
            out.append(f'{m.group(1)}="{remaining.pop(m.group(1))}"\n')
        else:
            out.append(line)
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(prefix=".lichtsteuerung.conf.",
                                     dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.writelines(out)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        raise


def push_metrics_nowait(q, **kwargs):
    """Never blocks the audio loop -- drops the sample if the web UI's
    consumer is behind (queue full). A dropped 100ms-throttled sample is
    invisible on a 30s rolling chart; a blocked audio loop would repeat
    the exact class of bug QLCWebSocket.send_press() was made
    enqueue-only to avoid (see its docstring in beat_osc.py).
    """
    try:
        q.put_nowait(kwargs)
    except queue.Full:
        pass


async def _metrics_broadcaster(app):
    loop = asyncio.get_running_loop()
    metrics_queue = app["metrics_queue"]
    while True:
        # Blocking get() runs in the default executor thread, not on
        # this event loop -- never stalls WS message pumping for
        # connected clients while waiting for the next sample.
        item = await loop.run_in_executor(None, metrics_queue.get)
        payload = json.dumps({"type": "metrics", **item})
        for ws in list(app["ws_clients"]):
            try:
                await ws.send_str(payload)
            except ConnectionResetError:
                app["ws_clients"].discard(ws)


def _config_message(live_config):
    return json.dumps({"type": "config", **live_config.as_dict()})


async def _broadcast_config(app):
    payload = _config_message(app["live_config"])
    for ws in list(app["ws_clients"]):
        try:
            await ws.send_str(payload)
        except ConnectionResetError:
            app["ws_clients"].discard(ws)


async def _do_persist(app):
    config_file = app["config_file"]
    if not config_file:
        return
    lc = app["live_config"]
    updates = {
        "SENSITIVITY": f"{lc.sensitivity:g}",
        "INTENSITY_THRESHOLDS_DB":
            " ".join(f"{v:g}" for v in lc.intensity_thresholds_db),
    }
    try:
        await asyncio.get_running_loop().run_in_executor(
            None, update_conf_file, config_file, updates)
        print(f"[web-ui] persisted config to {config_file}")
    except OSError as e:
        print(f"[web-ui] failed to persist config: {e}")


def _schedule_persist(app):
    # Debounced, not per-edit: a drag gesture emits many WS messages per
    # second. LiveConfig itself is already updated immediately (live
    # behavior), only the on-disk write is delayed/coalesced. No
    # flush-on-shutdown in this version -- worst case is losing the last
    # <PERSIST_DEBOUNCE_S of edits, recoverable by re-dragging; accepted
    # as a known, documented gap rather than added complexity.
    if app["pending_write"] is not None:
        app["pending_write"].cancel()
    loop = asyncio.get_running_loop()
    app["pending_write"] = loop.call_later(
        PERSIST_DEBOUNCE_S,
        lambda: asyncio.ensure_future(_do_persist(app)))


async def handle_ws(request):
    app = request.app
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    app["ws_clients"].add(ws)
    await ws.send_str(_config_message(app["live_config"]))
    try:
        async for msg in ws:
            if msg.type != web.WSMsgType.TEXT:
                continue
            try:
                data = json.loads(msg.data)
            except json.JSONDecodeError:
                continue
            msg_type = data.get("type")
            live_config = app["live_config"]
            changed = False
            if msg_type == "set_sensitivity":
                live_config.set_sensitivity(data.get("value"))
                changed = True
            elif msg_type == "set_intensity_thresholds":
                live_config.set_intensity_thresholds_db(
                    data.get("values", []))
                changed = True
            if changed:
                # Re-broadcast to *all* clients, not just the sender --
                # server is the single source of truth, so two tablets
                # never disagree and a clamped/sorted edit visibly snaps
                # every client's UI back into range.
                await _broadcast_config(app)
                _schedule_persist(app)
    finally:
        app["ws_clients"].discard(ws)
    return ws


async def handle_index(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "index.html"))


async def handle_get_config(request):
    return web.json_response(request.app["live_config"].as_dict())


def _build_app(live_config, metrics_queue, config_file):
    app = web.Application()
    app["live_config"] = live_config
    app["metrics_queue"] = metrics_queue
    app["config_file"] = config_file
    app["ws_clients"] = set()
    app["pending_write"] = None

    app.router.add_get("/", handle_index)
    app.router.add_get("/ws", handle_ws)
    app.router.add_get("/api/config", handle_get_config)
    app.router.add_static("/static/", STATIC_DIR, show_index=False)

    async def _start_broadcaster(app):
        app["broadcaster_task"] = asyncio.ensure_future(
            _metrics_broadcaster(app))

    app.on_startup.append(_start_broadcaster)
    return app


def _run_server(host, port, live_config, metrics_queue, config_file):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app = _build_app(live_config, metrics_queue, config_file)
    runner = web.AppRunner(app)
    loop.run_until_complete(runner.setup())
    site = web.TCPSite(runner, host, port)
    try:
        loop.run_until_complete(site.start())
    except OSError as e:
        print(f"[web-ui] failed to bind {host}:{port}: {e}")
        return
    print(f"[web-ui] listening on http://{host}:{port}/")
    loop.run_forever()


def start_web_ui_thread(host, port, live_config, metrics_queue, config_file):
    """Starts the aiohttp server in a daemon thread with its own event
    loop and returns immediately. No graceful-shutdown hook -- the
    process exiting kills this thread, same as every other daemon
    thread in beat_osc.py (QLCWebSocket's threads, run_invariant_loop).
    """
    thread = threading.Thread(
        target=_run_server,
        args=(host, port, live_config, metrics_queue, config_file),
        daemon=True)
    thread.start()
    return thread
