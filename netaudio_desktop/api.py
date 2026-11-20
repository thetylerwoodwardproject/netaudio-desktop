"""Thin client for the NetAudio daemon HTTP API (stdlib only)."""
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_PORT = 4780
CLIENT_ID = f"netaudio-desktop-{os.getpid()}"


class ApiError(Exception):
    pass


class Client:
    def __init__(self, host="127.0.0.1", port=DEFAULT_PORT):
        self.base = f"http://{host}:{port}"

    def _call(self, method, path, body=None, timeout=10):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("NetAudio-API-Version", "1")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                msg = json.loads(raw).get("error") or raw.decode(errors="replace")
            except Exception:
                msg = raw.decode(errors="replace") or e.reason
            raise ApiError(str(msg)) from None
        except (urllib.error.URLError, OSError) as e:
            raise ApiError(f"Cannot reach daemon at {self.base}: {e}") from None
        return json.loads(raw) if raw else {}

    def get(self, path, **kw):
        return self._call("GET", path, **kw)

    def post(self, path, body, **kw):
        return self._call("POST", path, body, **kw)

    # --- convenience ---
    def server_info(self):
        return self.get("/server-info", timeout=2)

    def devices(self):
        return self.get("/devices")

    def refresh(self):
        return self.post("/refresh", {}, timeout=30)

    def subscribe(self, rx_device, rx_channel, tx_device, tx_channel):
        return self.post("/subscribe", {
            "rx_device": rx_device, "rx_channel": rx_channel,
            "tx_device": tx_device, "tx_channel": tx_channel,
        }, timeout=20)

    def unsubscribe(self, rx_device, rx_channel):
        return self.post("/unsubscribe", {"rx_device": rx_device, "rx_channel": rx_channel}, timeout=20)

    def rename_device(self, device, name):
        return self.post("/rename-device", {"device": device, "name": name}, timeout=20)

    def rename_channel(self, device, channel_type, number, name):
        return self.post("/rename-channel", {
            "device": device, "channel_type": channel_type,
            "channel_number": number, "name": name}, timeout=20)

    def identify(self, device):
        return self.post("/identify", {"device": device})

    # --- metering (levels arrive on the /events stream; see meters.py) ---
    def make_meter_feed(self):
        from .meters import MeterFeed
        return MeterFeed(self.base)

    def start_metering(self, device):
        return self.post("/metering/start", {"client_id": CLIENT_ID, "device": device}, timeout=10)

    def stop_metering(self, device):
        return self.post("/metering/stop", {"client_id": CLIENT_ID, "device": device}, timeout=3)

    def refresh_clock(self, device):
        return self.post("/refresh-clock", {"device": device}, timeout=20)

    def set_preferred_leader(self, device, preferred):
        return self.post("/set-preferred-leader", {"device": device, "preferred": bool(preferred)}, timeout=30)

    def set_sample_rate(self, device, rate):
        return self.post("/set-sample-rate", {"device": device, "sample_rate": rate}, timeout=60)


def find_daemon_binary():
    """Locate netaudio-daemon: PATH, next to the `netaudio` launcher, or a uv/pipx install."""
    env = os.environ.get("NETAUDIO_DAEMON_BIN")
    if env and os.access(env, os.X_OK):
        return env
    snap = os.environ.get("SNAP")
    if snap and os.access(f"{snap}/usr/lib/netaudio/netaudio-daemon", os.X_OK):
        return f"{snap}/usr/lib/netaudio/netaudio-daemon"
    p = shutil.which("netaudio-daemon")
    if p:
        return p
    roots = [Path.home() / ".local/share/uv/tools/netaudio",
             Path.home() / ".local/share/pipx/venvs/netaudio",
             Path.home() / ".local/pipx/venvs/netaudio"]
    for root in roots:
        for cand in root.glob("lib/python*/site-packages/netaudio/bin/netaudio-daemon"):
            if os.access(cand, os.X_OK):
                return str(cand)
    return None


def start_daemon(port=DEFAULT_PORT, binary=None):
    """Start the daemon detached. Returns the Popen, or raises ApiError."""
    binary = binary or find_daemon_binary()
    if not binary:
        raise ApiError("netaudio-daemon not found. Install with: uv tool install netaudio")
    return subprocess.Popen(
        [binary, "--port", str(port)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True)


def ensure_daemon(client, port, auto_start=True, wait=8.0):
    """Return True if we started a daemon, False if one was already running."""
    if getattr(client, "demo", False):
        return False
    try:
        client.server_info()
        return False
    except ApiError:
        if not auto_start:
            raise
    start_daemon(port)
    deadline = time.time() + wait
    while time.time() < deadline:
        try:
            client.server_info()
            return True
        except ApiError:
            time.sleep(0.3)
    raise ApiError("Started netaudio-daemon but it did not become ready")
