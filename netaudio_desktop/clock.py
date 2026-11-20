"""Interpret the daemon's per-device `clock_status` (PTP sync) into something displayable.

The exact strings the daemon reports for role/sync/servo state have not been observed
on real hardware here, so health is a tolerant keyword heuristic and the raw values are
always shown alongside it.
"""

GOOD, WARN, BAD, UNKNOWN = "good", "warn", "bad", "unknown"

_WARN = ("acquir", "locking", "syncing", "settling", "holdover", "calibrat", "initial", "listening", "pending")
_BAD = ("unlock", "not sync", "no sync", "unsync", "lost", "fault", "error", "fail", "free-run", "freerun", "disabled")
_GOOD = ("lock", "sync", "leader", "master", "ok", "stable", "locked")


def ident(v):
    """Normalise a PTP identity (string, or list of byte ints) to lowercase hex, no separators."""
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        if not v:
            return None
        try:
            return "".join(f"{int(b):02x}" for b in v)
        except (TypeError, ValueError):
            return None
    s = "".join(ch for ch in str(v).lower() if ch in "0123456789abcdef")
    return s or None


def pretty(v):
    h = ident(v)
    return ":".join(h[i:i + 2] for i in range(0, len(h), 2)) if h else None


def device_ids(cs):
    return {i for i in (ident(cs.get("ptpv2_device_identity")), ident(cs.get("ptpv1_device_uuid"))) if i}


def grandmaster_id(cs):
    return ident(cs.get("ptpv2_grandmaster_identity")) or ident(cs.get("ptpv1_grandmaster_uuid"))


def master_id(cs):
    return ident(cs.get("ptpv2_master_identity")) or ident(cs.get("ptpv1_master_uuid"))


def health(cs):
    if not cs or cs.get("status_supported") is False:
        return UNKNOWN
    text = " ".join(str(cs.get(k) or "") for k in ("synchronization", "servo_state", "clock_state")).lower()
    if not text.strip():
        return UNKNOWN
    if any(w in text for w in _WARN):
        return WARN
    if any(w in text for w in _BAD):
        return BAD
    if cs.get("mute_reasons"):
        return WARN
    if any(w in text for w in _GOOD):
        return GOOD
    return WARN


def summarize(devs):
    """Return {'grandmaster': name|id|None, 'grandmaster_id', 'synced', 'total', 'per': {server_name: info}}."""
    online = [d for d in devs.values() if d.get("online", True)]
    by_id = {}
    for d in online:
        for i in device_ids(d.get("clock_status") or {}):
            by_id[i] = d
    votes = {}
    for d in online:
        g = grandmaster_id((d.get("clock_status") or {}))
        if g:
            votes[g] = votes.get(g, 0) + 1
    gm = max(votes, key=votes.get) if votes else None
    gm_dev = by_id.get(gm) if gm else None
    per, synced, total = {}, 0, 0
    for d in online:
        cs = d.get("clock_status") or {}
        h = health(cs)
        m = master_id(cs)
        md = by_id.get(m) if m else None
        gid = grandmaster_id(cs)
        role = (cs.get("clock_role") or "").strip() or None
        per[d["server_name"]] = {
            "health": h, "role": role,
            "is_grandmaster": bool(gm and (gm in device_ids(cs))),
            "grandmaster": (by_id[gid].get("name") if gid in by_id else pretty(gid)) if gid else None,
            "master": (md.get("name") if md else pretty(m)) if m else None,
        }
        if h != UNKNOWN:
            total += 1
            synced += h == GOOD
    return {"grandmaster": (gm_dev.get("name") or gm_dev["server_name"]) if gm_dev else pretty(gm),
            "grandmaster_id": pretty(gm), "synced": synced, "total": total, "per": per}
