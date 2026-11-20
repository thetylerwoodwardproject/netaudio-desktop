"""Audio metering: parse the daemon's `meter_values` event stream, plus a simulator for demo mode.

Daemon format (API 1): the first SSE event (`snapshot`) carries `metering_scale.detailed`, a list
indexed by the raw value (0 = clipping, 1 = 0 dBFS, then -0.5 dB per step, 254 = muted,
255 = framing marker). `meter_values` events carry, per device (`server_name`), maps of
channel-number -> raw value in `tx` / `rx`, and booleans in `tx_signal_presence` / `rx_signal_presence`.
"""
import json
import math
import random
import threading
import time
import urllib.request

STALE_SECONDS = 3.0
FLOOR_DB = -60.0          # bottom of the displayed range


def level01(dbfs, state):
    """Map a reading to a 0..1 bar fill."""
    if state == "clipping":
        return 1.0
    if dbfs is None:
        return 0.0
    return max(0.0, min(1.0, (dbfs - FLOOR_DB) / -FLOOR_DB))


def css_class(dbfs, state):
    if state == "clipping" or (dbfs is not None and dbfs > -3):
        return "m-clip"
    if dbfs is not None and dbfs > -12:
        return "m-hot"
    return "m-ok"


def describe(dbfs, state, present):
    if state == "clipping":
        txt = "clipping"
    elif dbfs is None:
        txt = {"muted": "muted"}.get(state, "no level")
    else:
        txt = f"{dbfs:.1f} dBFS"
    return f"{txt} · {'signal present' if present else 'no signal'}"


class MeterFeed:
    """Background reader of GET /events. read() returns the latest non-stale readings per device:
    {server_name: {"tx": {n: (dbfs, state)}, "rx": {...}, "tx_present": {n: bool}, "rx_present": {...}}}"""

    def __init__(self, base):
        self.base = base
        self._lock = threading.Lock()
        self._latest = {}
        self._scale = None
        self._stop = threading.Event()
        self._thread = None
        self.connected = False

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()
        with self._lock:
            self._latest = {}

    def read(self):
        now = time.time()
        with self._lock:
            return {k: v for k, v in self._latest.items() if now - v["t"] <= STALE_SECONDS}

    # --- internals ---
    def _run(self):
        while not self._stop.is_set():
            try:
                self._consume()
            except Exception:  # noqa: BLE001 - reconnect on any stream failure
                pass
            self.connected = False
            self._stop.wait(2.0)

    def _consume(self):
        req = urllib.request.Request(
            self.base + "/events?meters=1&telemetry=none&patches=0",
            headers={"Accept": "text/event-stream", "NetAudio-API-Version": "1"})
        with urllib.request.urlopen(req, timeout=60) as r:
            self.connected = True
            for line in r:
                if self._stop.is_set():
                    return
                if line.startswith(b"data:"):
                    self.handle_event(json.loads(line[5:]))

    def handle_event(self, ev):
        kind = ev.get("event")
        if kind == "snapshot":
            det = (ev.get("metering_scale") or {}).get("detailed")
            if det:
                self._scale = [(e.get("dbfs"), e.get("state")) for e in det]
        elif kind == "meter_values" and ev.get("server_name"):
            self._ingest(ev)

    def _conv(self, raw):
        sc = self._scale
        if sc is not None and isinstance(raw, (int, float)) and 0 <= int(raw) < len(sc):
            return sc[int(raw)]
        return (None, "unknown")

    def _ingest(self, ev):
        def vals(key):
            return {int(k): self._conv(v) for k, v in (ev.get(key) or {}).items() if str(k).isdigit()}

        def pres(key):
            return {int(k): bool(v) for k, v in (ev.get(key) or {}).items() if str(k).isdigit()}
        entry = {"tx": vals("tx"), "rx": vals("rx"), "tx_present": pres("tx_signal_presence"),
                 "rx_present": pres("rx_signal_presence"), "t": time.time()}
        with self._lock:
            old = self._latest.get(ev["server_name"])
            if old:  # updates may carry only part of a device; keep the rest fresh
                for k in ("tx", "rx", "tx_present", "rx_present"):
                    merged = dict(old[k])
                    merged.update(entry[k])
                    entry[k] = merged
            self._latest[ev["server_name"]] = entry


class DemoFeed:
    """Plausible fake levels derived from the demo client's devices and routes."""

    def __init__(self, client):
        self.client = client
        self._rng = random.Random(3)

    def start(self):
        pass

    def close(self):
        pass

    def _tx_db(self, dev, n, t):
        name = dev["name"]
        if name == "Laptop-Dante":
            return None                                    # silent source
        if name == "Stagebox-A" and n == 6:
            return None                                    # unplugged mic
        base = {"Stagebox-A": -22.0, "FOH-Console": -12.0}.get(name, -30.0)
        if name == "FOH-Console" and n in (3, 4, 5, 6):
            base = -50.0                                   # aux/monitors quiet
        v = base + 7 * math.sin(t * (0.9 + 0.23 * n) + n * 1.7) + self._rng.uniform(-2.5, 2.5)
        if name == "Stagebox-A" and n == 3 and int(t * 2) % 17 == 0:
            return "clip"
        return min(v, -0.5)

    def read(self):
        t = time.time()
        out, tx_levels = {}, {}
        for dev in self.client.d.values():
            tx = {}
            for n in range(1, len(dev["channels"]["transmitters"]) + 1):
                tx[n] = self._tx_db(dev, n, t)
            tx_levels[dev["name"]] = tx
        for dev in self.client.d.values():
            tx, rx, txp, rxp = {}, {}, {}, {}
            for n, v in tx_levels[dev["name"]].items():
                tx[n], txp[n] = self._fmt(v)
            for s in dev["subscriptions"]:
                src = tx_levels.get(s["tx_device"], {})
                num = next((int(k) for k, c in self.client._find(s["tx_device"])["channels"]["transmitters"].items()
                            if s["tx_channel"] in (c["name"], c["friendly_name"])), None)
                rx[s["rx_channel_number"]], rxp[s["rx_channel_number"]] = self._fmt(src.get(num))
            out[dev["server_name"]] = {"tx": tx, "rx": rx, "tx_present": txp, "rx_present": rxp, "t": t}
        return out

    @staticmethod
    def _fmt(v):
        if v == "clip":
            return (None, "clipping"), True
        if v is None or v < -60:
            return (None, "below_threshold"), False
        return (round(v * 2) / 2, "signal_present"), True
