"""In-memory fake of the daemon client, for trying the UI without a Dante network."""
import copy
import random
import time

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
