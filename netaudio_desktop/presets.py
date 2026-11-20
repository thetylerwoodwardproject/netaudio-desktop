"""Preset storage and plan helpers (GTK-free, unit-testable).

The daemon's /presets/save returns preset XML but does not store it; this app keeps the XML files
(plus a small JSON sidecar with display metadata) in the user's data directory.
"""
import hashlib
import json
import re
import time
from pathlib import Path

SECTIONS = (("routing", "Routing", "Subscriptions and channel names", True),
            ("audio", "Audio settings", "Sample rate, encoding, latency", True),
            ("device_controls", "Device controls", "Gain and other analog controls", True),
            ("network", "Network settings", "Interface configuration — only restore onto the same network", False))

KIND_LABELS = {
    "device_name": "Device name", "redundancy_mode": "Redundancy mode", "sample_rate": "Sample rate",
    "encoding": "Encoding", "latency": "Latency", "receive_flow_performance": "Receive flow performance",
    "transmit_flow_performance": "Transmit flow performance", "unicast_performance": "Unicast performance",
    "receive_flow_default_slots": "Receive flow slots", "sample_rate_pullup": "Sample-rate pull-up",
    "device_control": "Device control", "clock_configuration": "Clock configuration",
    "transmitter_channel_names": "Transmit channel names", "receiver_channel_names": "Receive channel names",
    "transmit_flow": "Transmit flows", "receiver_subscriptions": "Receive subscriptions",
    "external_receiver_subscriptions": "External (AES67) subscriptions", "codec_gain": "Codec gain",
    "interface": "Network interface", "preserved": "Preserved (not applied)"}
STATE_LABELS = {"change": "Will change", "unchanged": "Already set", "unsupported": "Not supported",
                "unavailable": "Unavailable", "ambiguous": "Ambiguous"}


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "preset"


def sha256(xml):
    return hashlib.sha256(xml.encode("utf-8")).hexdigest()


def short(v, n=90):
    """Compact one-line rendering of an arbitrary plan value."""
    if v is None:
        return "—"
    if isinstance(v, str):
        out = v
    else:
        try:
            out = json.dumps(v, separators=(", ", ": "), default=str)
        except Exception:  # noqa: BLE001
            out = str(v)
    return out if len(out) <= n else out[: n - 1] + "…"


def summarize_plan(plan):
    """Counts per action state, and the devices' non-unchanged actions."""
    counts = {k: 0 for k in STATE_LABELS}
    devices = []
    for d in (plan or {}).get("devices", []):
        shown = []
        for a in d.get("actions", []):
            counts[a.get("state", "unavailable")] = counts.get(a.get("state", "unavailable"), 0) + 1
            if a.get("state") != "unchanged":
                shown.append(a)
        devices.append({"device_name": d.get("device_name"), "server_name": d.get("server_name"),
                        "actions": shown, "total": len(d.get("actions", []))})
    blocked = counts["unsupported"] + counts["unavailable"] + counts["ambiguous"]
    return {"counts": counts, "changes": counts["change"], "blocked": blocked, "devices": devices}


def describe_result(res):
    """Human summary of a /presets/load result."""
    rep = (res or {}).get("report") or {}
    lines = []
    if res.get("complete"):
        lines.append("Everything was applied and verified.")
    else:
        lines.append("Not everything could be applied or verified.")
    if rep.get("failures"):
        lines.append(f"{rep['failures']} step(s) failed.")
    if rep.get("unverified"):
        lines.append(f"{rep['unverified']} step(s) could not be verified.")
    if res.get("interrupted"):
        lines.append("The run stopped early after a failure.")
    if rep.get("needs_reboot"):
        lines.append("Needs a reboot: " + ", ".join(rep["needs_reboot"]))
    bad = [o for o in rep.get("operations", []) if str(o.get("state", "")).lower() not in
           ("applied", "confirmed", "unchanged", "ok", "success", "succeeded")]
    for o in bad[:6]:
        lines.append(f"• {o.get('device_name', '?')} — {KIND_LABELS.get(o.get('kind'), o.get('kind'))}: "
                     f"{o.get('message') or o.get('state')}")
    return "\n".join(lines)


class PresetStore:
    """Presets on disk (directory) or in memory (directory=None, used by demo mode)."""

    def __init__(self, directory=None):
        self.dir = Path(directory) if directory else None
        self._mem = {}
        if self.dir:
            self.dir.mkdir(parents=True, exist_ok=True)

    def list(self):
        if self.dir is None:
            metas = [dict(m, slug=s) for s, (m, _x) in self._mem.items()]
        else:
            metas = []
            for f in self.dir.glob("*.json"):
                try:
                    m = json.loads(f.read_text())
                    if (self.dir / f"{f.stem}.xml").exists():
                        metas.append(dict(m, slug=f.stem))
                except Exception:  # noqa: BLE001 - skip unreadable sidecars
                    continue
        return sorted(metas, key=lambda m: m.get("saved_at", ""), reverse=True)

    def exists(self, name):
        return any(m["name"].strip().lower() == name.strip().lower() for m in self.list())

    def _slug_for(self, name, overwrite):
        existing = {m["slug"]: m for m in self.list()}
        base = slugify(name)
        for slug, m in existing.items():
            if m["name"].strip().lower() == name.strip().lower():
                if overwrite:
                    return slug
        slug, i = base, 2
        while slug in existing:
            slug, i = f"{base}-{i}", i + 1
        return slug

    def save(self, name, xml, meta=None, overwrite=False):
        meta = dict(meta or {}, name=name, saved_at=(meta or {}).get("saved_at") or time.strftime("%Y-%m-%dT%H:%M:%S"))
        slug = self._slug_for(name, overwrite)
        if self.dir is None:
            self._mem[slug] = (meta, xml)
        else:
            (self.dir / f"{slug}.xml").write_text(xml, encoding="utf-8")
            (self.dir / f"{slug}.json").write_text(json.dumps(meta, indent=2))
        return slug

    def get_xml(self, slug):
        if self.dir is None:
            return self._mem[slug][1]
        return (self.dir / f"{slug}.xml").read_text(encoding="utf-8")

    def delete(self, slug):
        if self.dir is None:
            self._mem.pop(slug, None)
        else:
            for ext in ("xml", "json"):
                (self.dir / f"{slug}.{ext}").unlink(missing_ok=True)

    def import_file(self, path):
        path = Path(path)
        xml = path.read_text(encoding="utf-8")
        if len(xml.encode("utf-8")) > 4 * 1024 * 1024:
            raise ValueError("Preset file is larger than 4 MiB")
        if "<" not in xml:
            raise ValueError("That doesn't look like a preset XML file")
        return self.save(path.stem, xml, {"imported": True, "devices": [], "sections": [], "device_count": None})
