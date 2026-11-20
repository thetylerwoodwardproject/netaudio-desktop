"""Device audio settings helpers (GTK-free). Field names follow the daemon's device record, as read by
the official CLI: *_latency_ms, standard_latency_choices_ms, supported_sample_rates_hz,
sample_rate_pullup_*, gain_device_type / gain_levels / gain_level_choices."""

DEFAULT_RATES = [44100, 48000, 88200, 96000, 176400, 192000]
DEFAULT_ENCODINGS = [16, 24, 32]
DEFAULT_LATENCIES_MS = [0.15, 0.25, 0.5, 1.0, 2.0, 5.0]
PULLUP_LABELS = {0: "None", 1: "+4.1667%", 2: "+0.1%", 3: "−0.1%", 4: "−4.0%"}


def can_write(d, *keywords, exclude=()):
    """Whether the daemon says a setting is writable. Unknown availability keys are treated as allowed
    (the daemon still refuses what it can't do)."""
    avail = d.get("operation_availability") or {}
    hits = [v for k, v in avail.items() if any(w in k.lower() for w in keywords)
            and not any(x in k.lower() for x in exclude) and isinstance(v, dict)]
    if not hits:
        return True
    return any(v.get("writable", True) and v.get("write_permitted", True) for v in hits)


def is_locked(d):
    return bool(d.get("is_locked"))


def fmt_ms(v):
    return f"{v:g} ms"


def rates(d):
    cur = d.get("sample_rate_hz")
    out = sorted(set(d.get("supported_sample_rates_hz") or DEFAULT_RATES) | ({cur} if cur else set()))
    return out


def encodings(d):
    cur = d.get("encoding")
    return sorted(set(DEFAULT_ENCODINGS) | ({cur} if cur else set()))


def latency_current(d):
    for k in ("configured_latency_ms", "latency_ms", "active_latency_ms"):
        if d.get(k) is not None:
            return d[k]
    return None


def latency_choices(d):
    """Standard choices advertised by the device (fallback: common values within its min/max)."""
    lo, hi = d.get("min_latency_ms"), d.get("max_latency_ms")
    ch = list(d.get("standard_latency_choices_ms") or [])
    if not ch:
        ch = [v for v in DEFAULT_LATENCIES_MS if (lo is None or v >= lo) and (hi is None or v <= hi)]
    cur = latency_current(d)
    if cur is not None and all(abs(cur - v) > 1e-9 for v in ch):
        ch.append(cur)
    return sorted(set(ch))


def latency_hint(d):
    lo, hi = d.get("min_latency_ms"), d.get("max_latency_ms")
    bits = []
    if lo is not None and hi is not None:
        bits.append(f"Allowed {lo:g}–{hi:g} ms")
    act, conf = d.get("active_latency_ms"), d.get("configured_latency_ms")
    if act is not None and conf is not None and abs(act - conf) > 1e-9:
        bits.append(f"active {act:g} ms — reboot may be needed")
    elif d.get("default_latency_ms") is not None:
        bits.append(f"default {d['default_latency_ms']:g} ms")
    return " · ".join(bits)


def pullup(d):
    """(choices [(raw, label)], current_raw) or None when the device can't do pull-up."""
    sup = d.get("supported_sample_rate_pullup_raw_values") or []
    if not sup or d.get("sample_rate_pullup_configuration_supported") is False:
        return None
    cur = d.get("requested_sample_rate_pullup_raw_value")
    if cur is None:
        cur = d.get("sample_rate_pullup_raw_value")
    return [(r, PULLUP_LABELS.get(r, f"raw {r}")) for r in sup], cur


def gain(d):
    """None if no reference-level controls, else {"kind": "tx"|"rx", "type": "input"|"output",
    "choices": [(value, label)], "levels": [current value per channel]}."""
    typ = d.get("gain_device_type")
    if typ not in ("input", "output"):
        return None
    choices = [(c["value"], c.get("label") or str(c["value"])) for c in d.get("gain_level_choices") or []]
    if not choices:
        return None
    return {"kind": "tx" if typ == "input" else "rx", "type": typ, "choices": choices,
            "levels": list(d.get("gain_levels") or [])}
