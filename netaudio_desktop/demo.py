"""In-memory fake of the daemon client, for trying the UI without a Dante network."""
import copy
import hashlib
import random
import time
import xml.etree.ElementTree as ET

from .api import ApiError


def _dev(name, ip, mac, tx, rx, rate=48000, kind="demo"):
    def chans(prefix, n, labels=None):
        return {str(i): {"name": (labels[i - 1] if labels else f"{prefix}{i:02d}"),
                         "friendly_name": None, "can_rename": True, "media_type": "audio",
                         "sample_rate": rate, "encoding": 24} for i in range(1, n + 1)}
    return {"server_name": f"{name}.local.", "name": name, "ipv4": ip, "online": True, "kind": kind,
            "mac_address": mac, "sample_rate_hz": rate, "encoding": 24, "latency_ms": 1.0,
            "tx_count": len(tx), "rx_count": len(rx), "subscriptions": [],
            "channels": {"transmitters": {str(i + 1): c for i, c in enumerate(
                             {"name": l, "friendly_name": None, "can_rename": True} for l in tx)},
                         "receivers": {str(i + 1): c for i, c in enumerate(
                             {"name": l, "friendly_name": None, "can_rename": True} for l in rx)}}}


class DemoClient:
    demo = True

    def __init__(self):
        self.d = {}
        for dev in (
            _dev("Stagebox-A", "192.168.10.11", "00:1D:C1:AA:00:11",
                 [f"Mic {i}" for i in range(1, 9)], []),
            _dev("FOH-Console", "192.168.10.20", "00:1D:C1:AA:00:20",
                 ["Main L", "Main R", "Aux 1", "Aux 2", "Mon 1", "Mon 2"],
                 [f"Input {i}" for i in range(1, 9)]),
            _dev("Recorder", "192.168.10.30", "00:1D:C1:AA:00:30", [],
                 [f"Track {i}" for i in range(1, 9)], rate=96000),
            _dev("Amp-Rack", "192.168.10.40", "00:1D:C1:AA:00:40", [],
                 ["Zone 1 L", "Zone 1 R", "Zone 2 L", "Zone 2 R"]),
            _dev("Laptop-Dante", "192.168.10.50", "00:1D:C1:AA:00:50",
                 ["Play L", "Play R"], ["Rec L", "Rec R"]),
        ):
            self.d[dev["server_name"]] = dev
        self._ifaces = []
        self._init_settings()
        self.preferred = "Stagebox-A"
        self._eui = {d["name"]: "00:1d:c1:ff:fe:" + d["mac_address"].lower()[-8:] for d in self.d.values()}
        self._rng = random.Random(7)
        self._recompute_clock()
        for i in range(1, 9):
            self._sub("FOH-Console", i, "Stagebox-A", f"Mic {i}")
        self._sub("Recorder", 1, "FOH-Console", "Main L")
        self._sub("Recorder", 2, "FOH-Console", "Main R")
        self._sub("Amp-Rack", 1, "FOH-Console", "Main L")
        self._sub("Amp-Rack", 2, "FOH-Console", "Main R")

    # --- helpers ---
    def _find(self, sel):
        for d in self.d.values():
            if sel in (d["server_name"], d["name"]):
                return d
        raise ApiError(f"Device not found: {sel}")

    @staticmethod
    def _label(ch):
        return ch["friendly_name"] or ch["name"]

    def _sub(self, rx, rxch, tx, txlabel):
        r = self._find(rx)
        t = self._find(tx)
        r["subscriptions"] = [s for s in r["subscriptions"] if s["rx_channel_number"] != rxch]
        r["subscriptions"].append({
            "rx_channel_number": rxch, "rx_channel": self._label(r["channels"]["receivers"][str(rxch)]),
            "rx_device": r["name"], "tx_channel": txlabel, "tx_device": t["name"],
            "status": "dynamic", "subscription_status_code": 9, "rx_status_code": 9})

    def _recompute_clock(self):
        names = [d["name"] for d in self.d.values()]
        leader = self.preferred if self.preferred in names else names[0]
        for d in self.d.values():
            is_leader = d["name"] == leader
            d["clock_status"] = {
                "status_supported": True,
                "clock_role": "leader" if is_leader else "follower",
                "synchronization": "synchronized",
                "servo_state": "locked",
                "clock_state": "leader" if is_leader else "follower",
                "clock_frequency_offset_parts_per_billion": 0,
                "maximum_drift_parts_per_billion": 40,
                "stratum": 4, "mute_state": "unmuted", "mute_reasons": [],
                "preferred_leader": d["name"] == self.preferred, "preferred_leader_locked": False,
                "ptpv2_device_identity": self._eui[d["name"]],
                "ptpv2_grandmaster_identity": self._eui[leader],
                "ptpv2_master_identity": self._eui[leader],
                "ptpv2_domain": 0, "ptpv2_priority1": 2 if d["name"] == self.preferred else 128,
                "ptpv2_priority2": 128, "ptpv2_clock_class": 248,
                "clock_port_records": [
                    {"record_number": 1, "role": "leader" if is_leader else "follower", "state": "active",
                     "link_down": False, "ptp_version": 2, "transport_path": "primary"}]
                + ([{"record_number": 2, "role": "passive", "state": "active", "link_down": True,
                     "ptp_version": 2, "transport_path": "secondary"}] if d["name"] == "Amp-Rack" else []),
            }
            d["clock_control_availability"] = {"preferred_leader": True, "clock_source": True}

    def _tick_clock(self):
        for d in self.d.values():
            cs = d["clock_status"]
            lead = cs["clock_role"] == "leader"
            cs["clock_frequency_offset_parts_per_billion"] = 0 if lead else self._rng.randint(-35, 35)
            if d["name"] == "Laptop-Dante":   # a device that is still settling
                cs["synchronization"], cs["servo_state"] = "synchronizing", "acquiring"
                if self._rng.random() < 0.3:
                    cs["synchronization"], cs["servo_state"] = "synchronized", "locked"

    # --- audio settings, gain and issues (simulated) ---
    GAIN_CHOICES = [{"label": "+24 dBu", "value": 1}, {"label": "+18 dBu", "value": 2},
                    {"label": "+4 dBu", "value": 3}, {"label": "0 dBu", "value": 4},
                    {"label": "−10 dBV", "value": 5}]

    def _init_settings(self):
        for d in self.d.values():
            d.update({"standard_latency_choices_ms": [0.25, 0.5, 1.0, 2.0, 5.0], "min_latency_ms": 0.15,
                      "max_latency_ms": 5.0, "default_latency_ms": 1.0, "configured_latency_ms": 1.0,
                      "active_latency_ms": 1.0, "supported_sample_rates_hz": [44100, 48000, 88200, 96000],
                      "sample_rate_pullup_raw_value": 0, "requested_sample_rate_pullup_raw_value": 0,
                      "supported_sample_rate_pullup_raw_values": [0, 1, 2, 3, 4],
                      "sample_rate_pullup_configuration_supported": d["name"] != "Laptop-Dante",
                      "is_locked": False})
            if d["name"] == "Stagebox-A":
                d.update({"gain_device_type": "input", "gain_level_choices": copy.deepcopy(self.GAIN_CHOICES),
                          "gain_levels": [3] * len(d["channels"]["transmitters"])})
            if d["name"] == "Amp-Rack":
                d.update({"gain_device_type": "output", "gain_level_choices": copy.deepcopy(self.GAIN_CHOICES),
                          "gain_levels": [3] * len(d["channels"]["receivers"])})
        self._t0 = time.time()

    def set_latency(self, device, ms):
        d = self._find(device)
        if not (d["min_latency_ms"] <= ms <= d["max_latency_ms"]):
            raise ApiError(f"Latency must be between {d['min_latency_ms']:g} and {d['max_latency_ms']:g} ms")
        d["configured_latency_ms"] = d["latency_ms"] = ms
        return {"success": True}

    def set_encoding(self, device, bits):
        self._find(device)["encoding"] = bits
        return {"success": True}

    def set_pullup(self, device, raw_value):
        d = self._find(device)
        if raw_value not in d["supported_sample_rate_pullup_raw_values"]:
            raise ApiError("Unsupported pull-up value")
        d["requested_sample_rate_pullup_raw_value"] = d["sample_rate_pullup_raw_value"] = raw_value
        return {"success": True}

    def set_gain(self, device, channel_number, device_type, gain_level):
        d = self._find(device)
        if d.get("gain_device_type") != device_type:
            raise ApiError("This device has no reference-level controls of that type")
        d["gain_levels"][channel_number - 1] = gain_level
        return {"success": True}

    def issues(self, state="open", limit=200):
        now = time.time()
        iso = lambda ago: time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now - ago))  # noqa: E731

        def issue(i, kind, sev, dev, title, summary, fix, first, last, count, resolved=None, **scope):
            return {"issue_id": f"demo-{i}", "kind": kind, "severity": sev, "state": "resolved" if resolved else "open",
                    "title": title, "summary": summary, "suggested_remediation": fix,
                    "first_seen": iso(first), "last_seen": iso(last), "resolved_at": iso(resolved) if resolved else None,
                    "occurrence_count": count, "evidence_class": "direct_observation", "evidence_source": "demo",
                    "observation_state": "observed", "schema_version": 1, "raw_source_fields": {},
                    "scope": dict({"device_name": dev, "server_name": f"{dev}.local.", "device_identity": dev,
                                   "channel_identity": None, "flow_identity": None, "interface_identity": None},
                                  **scope)}
        items = []
        if "Laptop-Dante" in {d["name"] for d in self.d.values()}:
            items.append(issue(1, "clock_synchronization", "warning", "Laptop-Dante", "Clock not locked",
                               "The device is still synchronising to the grandmaster clock and has not reached lock.",
                               "Check the network path to the grandmaster and wait a minute. Persistent trouble "
                               "suggests excess jitter or a switch without PTP support.", 540, 3, 14))
        if "Recorder" in {d["name"] for d in self.d.values()}:
            items.append(issue(2, "receiver_latency_pressure", "warning", "Recorder", "Receive latency is tight",
                               "Packets are arriving close to the playout deadline at the configured latency of 1 ms.",
                               "Increase the receive latency (Devices → Audio settings) or shorten the network path.",
                               3100, 45, 9, channel_identity="Track 1"))
            items.append(issue(3, "reboot_required", "info", "Recorder", "Reboot needed to apply a setting",
                               "A configured setting will take effect after the next restart.",
                               "Restart the device when convenient.", 7200, 7100, 1))
            items.append(issue(4, "subscription_failure", "error", "Recorder", "Subscription failed",
                               "Receive channel 2 could not connect to its transmitter.",
                               "Verify the transmitting device is online and the route is still valid.",
                               86000, 85900, 2, resolved=85000, channel_identity="Track 2"))
        if state == "open":
            items = [i for i in items if i["state"] == "open"]
        active = sum(1 for i in items if i["state"] == "open")
        return {"active_count": active, "count": len(items), "history_limit": 1000, "issues": items[:limit],
                "next_cursor": None, "schema_version": 1}

    # --- presets (simulated: a small XML dialect, applied to the in-memory devices) ---
    def capture_preset(self, devices, name, sections):
        root = ET.Element("preset", {"name": name, "format": "netaudio-demo-1"})
        omitted = []
        for sn in devices:
            d = self._find(sn)
            de = ET.SubElement(root, "device", {"name": d["name"]})
            if "audio" in sections:
                ET.SubElement(de, "audio", {"sample_rate": str(d["sample_rate_hz"])})
            if "routing" in sections:
                for key, kind in (("transmitters", "tx"), ("receivers", "rx")):
                    for n, c in d["channels"][key].items():
                        ET.SubElement(de, "label", {"kind": kind, "n": n, "value": self._label(c)})
                for sub in d["subscriptions"]:
                    ET.SubElement(de, "subscription", {"rx": str(sub["rx_channel_number"]),
                                                       "tx_device": sub["tx_device"], "tx_channel": sub["tx_channel"]})
            if "network" in sections:
                ET.SubElement(de, "network", {"ipv4": d["ipv4"]})
            if "device_controls" in sections and d["name"] == "Amp-Rack":
                omitted.append({"device": d["name"], "setting": "Analog output gain",
                                "reason": "This device doesn't expose its gain controls (demo)"})
        return {"device_count": len(devices), "filename": f"{name}.xml", "name": name, "omitted": omitted,
                "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "xml": ET.tostring(root, encoding="unicode")}

    @staticmethod
    def _parse_preset(xml):
        try:
            return ET.fromstring(xml)
        except ET.ParseError as e:
            raise ApiError(f"Not a valid preset: {e}") from None

    def preview_preset(self, xml, devices):
        root = self._parse_preset(xml)
        out = []
        for de in root.findall("device"):
            subs = de.findall("subscription")
            labels = de.findall("label")
            audio = de.find("audio")
            settings = []
            if audio is not None:
                settings.append({"label": "Sample rate", "value": f"{audio.get('sample_rate')} Hz"})
            if labels:
                settings.append({"label": "Channel names", "value": f"{len(labels)} channels"})
            if subs or labels:
                settings.append({"label": "Subscriptions", "value": f"{len(subs)} routes"})
            targets = [{"id": d["server_name"], "name": d["name"], "address": d["ipv4"], "online": True,
                        "context": None} for d in self.d.values() if d["name"] == de.get("name")]
            out.append({"name": de.get("name"), "preserved": [], "settings": settings, "targets": targets})
        return {"devices": out, "digest": hashlib.sha256(xml.encode()).hexdigest(), "name": root.get("name")}

    def _preset_actions(self, de, target):
        """Compute (action dict, apply callable) pairs for one preset device against its target device."""
        acts = []
        audio = de.find("audio")
        if audio is not None:
            want = int(audio.get("sample_rate"))
            cur = target["sample_rate_hz"]
            acts.append(({"kind": "sample_rate", "state": "change" if want != cur else "unchanged",
                          "reason": f"{cur} Hz → {want} Hz" if want != cur else "Already set",
                          "current": cur, "requested": want},
                         (lambda w=want, t=target: self.set_sample_rate(t["server_name"], w))))
        for kind, key, nice in (("tx", "transmitters", "transmitter_channel_names"),
                                ("rx", "receivers", "receiver_channel_names")):
            diffs = [(le.get("n"), le.get("value")) for le in de.findall("label") if le.get("kind") == kind
                     and le.get("n") in target["channels"][key]
                     and self._label(target["channels"][key][le.get("n")]) != le.get("value")]
            if any(le.get("kind") == kind for le in de.findall("label")):
                acts.append(({"kind": nice, "state": "change" if diffs else "unchanged",
                              "reason": f"{len(diffs)} name(s) differ" if diffs else "Already set",
                              "current": None, "requested": None,
                              "details": [f"{kind.upper()} {n}: {self._label(target['channels'][key][n])} → {v}"
                                          for n, v in diffs]},
                             (lambda dd=diffs, k=kind, t=target: [
                                 self.rename_channel(t["server_name"], k, int(n), v) for n, v in dd])))
        subs = de.findall("subscription")
        if subs or any(le.get("kind") for le in de.findall("label")):
            want = {int(s.get("rx")): (s.get("tx_device"), s.get("tx_channel")) for s in subs}
            cur = {s["rx_channel_number"]: (s["tx_device"], s["tx_channel"]) for s in target["subscriptions"]}
            changes = []
            for rx in sorted(set(want) | set(cur)):
                if want.get(rx) != cur.get(rx):
                    fmt = lambda v: f"{v[0]} / {v[1]}" if v else "(none)"  # noqa: E731
                    changes.append((rx, want.get(rx), f"Rx {rx}: {fmt(cur.get(rx))} → {fmt(want.get(rx))}"))
            acts.append(({"kind": "receiver_subscriptions", "state": "change" if changes else "unchanged",
                          "reason": f"{len(changes)} route(s) differ" if changes else "Already set",
                          "current": len(cur), "requested": len(want), "details": [c[2] for c in changes]},
                         (lambda ch=changes, t=target: [
                             self.subscribe(t["server_name"], rx, w[0], w[1]) if w
                             else self.unsubscribe(t["server_name"], rx) for rx, w, _ in ch])))
        if de.find("network") is not None:
            acts.append(({"kind": "interface", "state": "unsupported",
                          "reason": "Network settings aren't restored in demo mode", "current": None,
                          "requested": None}, None))
        return acts

    def plan_preset(self, xml, targets, excluded, store=False):
        root = self._parse_preset(xml)
        devs = []
        for de in root.findall("device"):
            name = de.get("name")
            if name in excluded or name not in targets:
                continue
            target = self._find(targets[name])
            devs.append({"device_name": name, "server_name": target["server_name"],
                         "actions": [a for a, _f in self._preset_actions(de, target)]})
        return {"devices": devs, "digest": hashlib.sha256(xml.encode()).hexdigest(), "name": root.get("name")}

    def load_preset(self, xml, digest, targets, excluded, store=False):
        if digest != hashlib.sha256(xml.encode()).hexdigest():
            raise ApiError("Preset changed since it was planned; plan again before applying")
        root = self._parse_preset(xml)
        ops = []
        time.sleep(0.6)
        # Names first, then audio settings, then subscriptions (as the real daemon orders them).
        order = {"transmitter_channel_names": 0, "receiver_channel_names": 0, "sample_rate": 1,
                 "receiver_subscriptions": 2}
        for de in root.findall("device"):
            name = de.get("name")
            if name in excluded or name not in targets:
                continue
            target = self._find(targets[name])
            for act, fn in sorted(self._preset_actions(de, target), key=lambda p: order.get(p[0]["kind"], 3)):
                if act["state"] == "change" and fn:
                    fn()
                    ops.append({"device_name": name, "kind": act["kind"], "state": "applied",
                                "message": act["reason"]})
        return {"complete": True, "digest": digest, "interrupted": False, "name": root.get("name"),
                "run_id": f"demo-{int(time.time())}",
                "report": {"failures": 0, "needs_reboot": [], "operations": ops, "results": [], "unverified": 0}}

    # --- client API ---
    def server_info(self):
        return {"product": "netaudio-demo", "version": "demo"}

    def devices(self):
        self._tick_clock()
        return copy.deepcopy(self.d)

    _NICS = [{"name": "enp3s0", "addresses": ["192.168.10.5"], "running": True},
             {"name": "enp4s0", "addresses": ["192.168.20.5"], "running": True},
             {"name": "wlp2s0", "addresses": [], "running": False}]

    def settings(self):
        return {"network_interfaces": copy.deepcopy(self._NICS), "dante_interfaces": list(self._ifaces),
                "dante_interfaces_fixed": False, "monitoring_port": 8752, "active_monitoring_port": 8752}

    def set_interfaces(self, names):
        known = {n["name"] for n in self._NICS}
        bad = [n for n in names if n not in known]
        if bad:
            raise ApiError(f"Unknown interface: {', '.join(bad)}")
        self._ifaces = list(names)
        return self.settings()

    def make_meter_feed(self):
        from .meters import DemoFeed
        return DemoFeed(self)

    def start_metering(self, device):
        return {"success": True}

    def stop_metering(self, device):
        return {"success": True}

    def refresh_clock(self, device):
        self._find(device)
        return {"success": True}

    def set_preferred_leader(self, device, preferred):
        d = self._find(device)
        self.preferred = d["name"] if preferred else (None if self.preferred == d["name"] else self.preferred)
        self._recompute_clock()
        return {"success": True}

    def refresh(self):
        time.sleep(0.4)
        return {}

    def subscribe(self, rx_device, rx_channel, tx_device, tx_channel):
        r = self._find(rx_device)
        if str(rx_channel) not in r["channels"]["receivers"]:
            raise ApiError(f"{r['name']} has no receive channel {rx_channel}")
        self._sub(rx_device, rx_channel, tx_device, tx_channel)
        return {"success": True}

    def unsubscribe(self, rx_device, rx_channel):
        r = self._find(rx_device)
        r["subscriptions"] = [s for s in r["subscriptions"] if s["rx_channel_number"] != rx_channel]
        return {"success": True}

    def rename_device(self, device, name):
        d = self._find(device)
        old = d["name"]
        if not name.strip():
            raise ApiError("Name cannot be empty")
        d["name"] = name
        self._eui[name] = self._eui.pop(old)
        if self.preferred == old:
            self.preferred = name
        d["server_name"] = f"{name}.local."
        self.d = {x["server_name"]: x for x in self.d.values()}
        for x in self.d.values():
            for s in x["subscriptions"]:
                if s["tx_device"] == old:
                    s["tx_device"] = name
                if s["rx_device"] == old:
                    s["rx_device"] = name
        self._recompute_clock()
        return {"success": True}

    def rename_channel(self, device, channel_type, number, name):
        d = self._find(device)
        key = "transmitters" if channel_type == "tx" else "receivers"
        ch = d["channels"][key][str(number)]
        old = self._label(ch)
        ch["friendly_name"] = name
        for x in self.d.values():
            for s in x["subscriptions"]:
                if channel_type == "tx" and s["tx_device"] == d["name"] and s["tx_channel"] == old:
                    s["tx_channel"] = name
                if channel_type == "rx" and s["rx_device"] == d["name"] and s["rx_channel_number"] == number:
                    s["rx_channel"] = name
        return {"success": True}

    def identify(self, device):
        self._find(device)
        return {"success": True}

    def set_sample_rate(self, device, rate):
        d = self._find(device)
        d["sample_rate_hz"] = rate
        return {"success": True}
