"""NetAudio Desktop - a native GTK4/libadwaita front end for the NetAudio daemon."""
import json
import os
import sys
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Graphene, Gtk, Pango  # noqa: E402

from . import __version__  # noqa: E402
from . import clock as clk  # noqa: E402
from . import meters as mtr  # noqa: E402
from . import presets as presets_mod  # noqa: E402
from .presets_ui import PresetsView, RestoreDialog, SaveDialog  # noqa: E402
from .util import run_async  # noqa: E402
from .api import DEFAULT_PORT, ApiError, Client, ensure_daemon  # noqa: E402

APP_ID = "app.netaudio.Desktop"
ICON_NAME = "app.netaudio.Desktop"   # data/app.netaudio.Desktop.svg
CONFIG = Path(GLib.get_user_config_dir()) / "netaudio-desktop" / "config.json"
POLL_SECONDS = 3
SAMPLE_RATES = [44100, 48000, 88200, 96000, 176400, 192000]

CSS = b"""
.cell { min-width: 22px; min-height: 22px; padding: 0; margin: 1px; border-radius: 4px; }
.cell:checked, .cell:checked:backdrop { background: #3584e4; color: #ffffff; }
.cell-pending { opacity: 0.5; }
.dev-head { font-weight: bold; padding: 2px 6px; background: alpha(@accent_bg_color, 0.15); border-radius: 4px; }
.ch-head { font-size: smaller; opacity: 0.8; }
.rx-label { font-size: smaller; padding-right: 8px; }
.dot { font-size: 14px; }
.dot-good { color: @success_color; }
.dot-warn { color: @warning_color; }
.dot-bad { color: @error_color; }
.dot-unknown { opacity: 0.35; }
.statusbar { padding: 4px 12px; font-size: smaller; }
.statusbar-sep { opacity: 0.3; }
levelbar.meter trough { background: alpha(currentColor, 0.14); border-radius: 3px; min-height: 5px; min-width: 5px; }
levelbar.meter block.filled, levelbar.meter block.filled.low, levelbar.meter block.filled.high,
levelbar.meter block.filled.full { border-radius: 3px; min-height: 4px; min-width: 4px; background: #57e389; }
levelbar.meter.m-hot block.filled, levelbar.meter.m-hot block.filled.low,
levelbar.meter.m-hot block.filled.high, levelbar.meter.m-hot block.filled.full { background: #f5c211; }
levelbar.meter.m-clip block.filled, levelbar.meter.m-clip block.filled.low,
levelbar.meter.m-clip block.filled.high, levelbar.meter.m-clip block.filled.full { background: #e01b24; }
.sig { color: #57e389; }
.ch-name { font-size: smaller; }
.statusbar button { padding: 0 6px; min-height: 0; min-width: 0; font-size: smaller; font-weight: normal; }
.cell:hover { background: alpha(@accent_bg_color, 0.35); }
.cell:checked:hover { background: #4a94ea; }
.hl { background: alpha(@accent_bg_color, 0.3); border-radius: 4px; }
.dev-link:hover { text-decoration: underline; }
.axis-title { font-weight: bold; font-size: smaller; letter-spacing: 1px; opacity: 0.75;
              padding: 0 6px 4px 0; }
.rx-dev { font-weight: bold; padding: 6px 8px 2px 0; }
"""


def load_config():
    try:
        return json.loads(CONFIG.read_text())
    except Exception:
        return {}


def save_config(cfg):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=2))


def sorted_channels(chmap):
    out = []
    for k, v in (chmap or {}).items():
        try:
            out.append((int(k), v))
        except ValueError:
            continue
    return sorted(out, key=lambda t: t[0])


def ch_label(ch, num):
    return ch.get("friendly_name") or ch.get("name") or f"Channel {num}"


def online_devices(devs):
    return sorted((d for d in devs.values() if d.get("online", True)),
                  key=lambda d: (d.get("name") or d.get("server_name") or "").lower())


LEVELS = ("good", "warn", "bad", "unknown")


def make_dot():
    d = Gtk.Label(label="●", valign=Gtk.Align.CENTER)
    d.add_css_class("dot")
    d.add_css_class("dot-unknown")
    return d


def set_dot(dot, level):
    for l in LEVELS:
        dot.remove_css_class(f"dot-{l}")
    dot.add_css_class(f"dot-{level if level in LEVELS else 'unknown'}")


def make_meter(vertical=False, visible=False):
    bar = Gtk.LevelBar(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL,
                       min_value=0, max_value=1, value=0, valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
    for off in ("low", "high", "full"):
        bar.remove_offset_value(off)
    if vertical:
        bar.set_inverted(True)      # fill from the bottom up
    bar.add_css_class("meter")
    bar.add_css_class("m-ok")
    bar.set_size_request(7, 30) if vertical else bar.set_size_request(48, 6)
    bar.set_visible(visible)
    return bar


def apply_meter(bar, dbfs, state):
    lvl = round(mtr.level01(dbfs, state), 2)
    cls = mtr.css_class(dbfs, state) if lvl > 0 else "m-ok"
    if getattr(bar, "_m", None) != (lvl, cls):
        bar._m = (lvl, cls)
        bar.set_value(lvl)
        for c in ("m-ok", "m-hot", "m-clip"):
            bar.remove_css_class(c)
        bar.add_css_class(cls)


class VerticalLabel(Gtk.Widget):
    """Text rotated to read bottom-to-top, for transmit channel names above matrix columns.
    GTK4 labels cannot rotate, so this draws a Pango layout through the snapshot API."""
    __gtype_name__ = "NetAudioVerticalLabel"

    def __init__(self, text, length=96):
        super().__init__()
        self._text, self._length = text, length

    def _layout(self, width_px=None):
        lay = self.create_pango_layout(self._text)
        if width_px:
            lay.set_ellipsize(Pango.EllipsizeMode.END)
            lay.set_width(int(width_px) * Pango.SCALE)
        return lay

    def natural_text_px(self):
        return self._layout().get_pixel_size()[0]

    def set_length(self, px):
        if px != self._length:
            self._length = px
            self.queue_resize()

    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.HORIZONTAL:
            n = self._layout().get_pixel_size()[1] + 2          # rotated: text height is our width
        else:
            n = self._length
        return (n, n, -1, -1)

    def do_snapshot(self, snapshot):
        w, h = self.get_width(), self.get_height()
        if self.has_css_class("hl"):                             # hover crosshair
            snapshot.append_color(Gdk.RGBA(red=0.21, green=0.52, blue=0.89, alpha=0.3),
                                  Graphene.Rect().init(0, 0, w, h))
        lay = self._layout(self._length)
        th = lay.get_pixel_size()[1]
        snapshot.save()
        snapshot.translate(Graphene.Point().init((w - th) / 2, h))   # bottom edge, centred
        snapshot.rotate(-90)                                          # text runs upward
        snapshot.append_layout(lay, self.get_color())
        snapshot.restore()


class RoutingView(Gtk.ScrolledWindow):
    """Dante-Controller-style matrix: receivers as rows, transmitters as columns."""

    def __init__(self, on_toggle, on_rename=None, on_open=None):
        super().__init__(hexpand=True, vexpand=True)
        self.on_toggle = on_toggle
        self.on_rename = on_rename
        self.on_open = on_open
        self.grid = Gtk.Grid(margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        self.set_child(self.grid)
        self.signature = None
        self.meters_on = False
        self.meters = {}         # (kind, server_name, num) -> [bar, label, base_tooltip]
        self.cells = {}          # (rx_server, rx_num, tx_name, tx_label) -> ToggleButton
        self._updating = False
        self.empty = Adw.StatusPage(icon_name="network-wired-symbolic", title="No Dante devices found",
                                    description="Make sure this computer is on the same network as your "
                                                "devices, then press Refresh.")
        demo_btn = Gtk.Button(label="Try Demo Mode", halign=Gtk.Align.CENTER, action_name="app.demo")
        demo_btn.add_css_class("pill")
        demo_btn.add_css_class("suggested-action")
        self.empty.set_child(demo_btn)

    def update(self, devs):
        devices = online_devices(devs)
        tx_cols = []   # (device, num, channel)
        for d in devices:
            for n, ch in sorted_channels(d["channels"]["transmitters"]):
                tx_cols.append((d, n, ch))
        rx_rows = []
        for d in devices:
            for n, ch in sorted_channels(d["channels"]["receivers"]):
                rx_rows.append((d, n, ch))
        sig = (tuple((d["server_name"], n, ch_label(ch, n)) for d, n, ch in tx_cols),
               tuple((d["server_name"], n, ch_label(ch, n)) for d, n, ch in rx_rows))
        if sig != self.signature:
            self.signature = sig
            self._rebuild(devices, tx_cols, rx_rows)
        self._sync_state(devices)

    def _rebuild(self, devices, tx_cols, rx_rows):
        while (c := self.grid.get_first_child()) is not None:
            self.grid.remove(c)
        self.cells.clear()
        self.meters.clear()
        if not tx_cols or not rx_rows:
            self.set_child(self.empty)
            return
        self.set_child(self.grid)
        # Column headers: device name spanning its channels, then channel numbers.
        i = 0
        while i < len(tx_cols):
            dev = tx_cols[i][0]
            j = i
            while j < len(tx_cols) and tx_cols[j][0] is dev:
                j += 1
            head = Gtk.Label(label=dev.get("name") or dev["server_name"], xalign=0, ellipsize=3,
                             width_chars=1, max_width_chars=1)
            head.add_css_class("dev-head")
            self._linkable(head, dev)
            self.grid.attach(head, i + 1, 1, j - i, 1)
            i = j
        tx_lbls, name_widgets = [], []
        for ci, (d, n, ch) in enumerate(tx_cols):
            lbl = Gtk.Label(label=str(n))
            tx_lbls.append(lbl)
            name = VerticalLabel(ch_label(ch, n))
            name.add_css_class("ch-name")
            name_widgets.append(name)
            lbl._peer = name
            lbl.add_css_class("ch-head")
            lbl.set_tooltip_text(f"{d.get('name') or d['server_name']} — {ch_label(ch, n)}\nClick to rename")
            self._renamable(lbl, "tx", d, n, ch)
            bar = make_meter(vertical=True, visible=self.meters_on)
            colbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, halign=Gtk.Align.CENTER)
            self._renamable(name, "tx", d, n, ch)
            name.set_tooltip_text(lbl.get_tooltip_text())
            colbox.append(name)
            colbox.append(bar)
            colbox.append(lbl)
            self.meters[("tx", d["server_name"], n)] = [bar, lbl, lbl.get_tooltip_text()]
            self.grid.attach(colbox, ci + 1, 2, 1, 1)
        # Size every name to the longest one (capped) so the columns line up.
        if name_widgets:
            L = max(36, min(112, max(w.natural_text_px() for w in name_widgets) + 4))
            for w in name_widgets:
                w.set_length(L)
        # Axis titles: columns are transmitters (sources), rows are receivers (destinations).
        tx_title = Gtk.Label(label="TRANSMIT  →", xalign=0, hexpand=False)
        tx_title.add_css_class("axis-title")
        tx_title.set_tooltip_text("Columns: transmitters. Audio comes from these channels.")
        self.grid.attach(tx_title, 1, 0, len(tx_cols), 1)
        rx_title = Gtk.Label(label="RECEIVE  ↓", xalign=0, valign=Gtk.Align.END)
        rx_title.add_css_class("axis-title")
        rx_title.set_tooltip_text("Rows: receivers. Audio goes to these channels; click a cell to patch a source.")
        self.grid.attach(rx_title, 0, 1, 1, 2)
        # Rows
        row = 3
        last_dev = None
        for d, n, rch in rx_rows:
            if d is not last_dev:
                last_dev = d
                h = Gtk.Label(label=d.get("name") or d["server_name"], xalign=0)
                h.add_css_class("rx-dev")
                self._linkable(h, d)
                self.grid.attach(h, 0, row, 1, 1)
                row += 1
            rl = Gtk.Label(label=f"{n}  {ch_label(rch, n)}", xalign=0)
            rl.add_css_class("rx-label")
            rl.set_tooltip_text("Click to rename")
            self._renamable(rl, "rx", d, n, rch)
            rl.set_width_chars(18)          # fixed width so the bars line up in a column
            rl.set_max_width_chars(18)
            rl.set_ellipsize(3)
            rbar = make_meter(vertical=False, visible=self.meters_on)
            rowbox = Gtk.Box(spacing=6)
            rowbox.append(rl)
            rowbox.append(rbar)
            self.meters[("rx", d["server_name"], n)] = [rbar, rl, rl.get_tooltip_text()]
            self.grid.attach(rowbox, 0, row, 1, 1)
            for ci, (td, tn, tch) in enumerate(tx_cols):
                b = Gtk.ToggleButton()
                b.add_css_class("cell")
                b.set_tooltip_text(f"{ch_label(rch, n)} ← {td.get('name') or td['server_name']}: {ch_label(tch, tn)}")
                b.connect("toggled", self._toggled, d, n, td, tch, tn)
                mc = Gtk.EventControllerMotion()
                mc.connect("enter", lambda _c, _x, _y, a=rl, c=tx_lbls[ci]: self._hover(a, c, True))
                mc.connect("leave", lambda _c, a=rl, c=tx_lbls[ci]: self._hover(a, c, False))
                b.add_controller(mc)
                self.grid.attach(b, ci + 1, row, 1, 1)
                self.cells[(d["server_name"], n, td["server_name"], tn)] = b
            row += 1

    @staticmethod
    def _hover(row_label, col_label, on):
        """Crosshair: highlight the receive row label and transmit column number under the pointer."""
        for w in (row_label, col_label, getattr(col_label, "_peer", None)):
            if w is not None:
                (w.add_css_class if on else w.remove_css_class)("hl")
                if isinstance(w, VerticalLabel):
                    w.queue_draw()

    def _linkable(self, widget, dev):
        """Click a device name to open its page on the Devices tab."""
        if not self.on_open:
            return
        widget.add_css_class("dev-link")
        widget.set_cursor_from_name("pointer")
        widget.set_tooltip_text(f"Open {dev.get('name') or dev['server_name']}")
        g = Gtk.GestureClick(button=1)
        g.connect("released", lambda *_: self.on_open(dev["server_name"]))
        widget.add_controller(g)

    def _renamable(self, widget, kind, dev, num, ch):
        if not self.on_rename or ch.get("can_rename") is False:
            return
        widget.set_cursor_from_name("pointer")
        g = Gtk.GestureClick(button=1)
        g.connect("released", lambda gest, n_press, x, y: self._rename_popover(widget, kind, dev, num, ch))
        widget.add_controller(g)

    def _rename_popover(self, widget, kind, dev, num, ch):
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=10, margin_bottom=10,
                      margin_start=10, margin_end=10)
        what = "transmit" if kind == "tx" else "receive"
        box.append(Gtk.Label(label=f"Rename {what} channel {num} on {dev.get('name') or dev['server_name']}",
                             xalign=0, css_classes=["heading"]))
        entry = Gtk.Entry(text=ch_label(ch, num), width_chars=28, activates_default=False)
        box.append(entry)
        btn = Gtk.Button(label="Rename", halign=Gtk.Align.END, css_classes=["suggested-action"])
        box.append(btn)

        def apply(*_):
            new = entry.get_text().strip()
            pop.popdown()
            if new and new != ch_label(ch, num):
                self.on_rename(kind, dev, num, new)
        btn.connect("clicked", apply)
        entry.connect("activate", apply)
        pop.set_child(box)
        pop.set_parent(widget)
        pop.connect("closed", lambda p: GLib.idle_add(p.unparent))
        pop.popup()
        entry.grab_focus()
        entry.select_region(0, -1)

    def set_meters_visible(self, on):
        self.meters_on = on
        if not on:
            self.update_meters({})
        for bar, _l, _t in self.meters.values():
            bar.set_visible(on)

    def update_meters(self, data):
        for (kind, sn, n), ent in self.meters.items():
            bar, lbl, base = ent
            d = data.get(sn)
            if d:
                dbfs, state = d[kind].get(n, (None, "unknown"))
                present = d[kind + "_present"].get(n, False)
            else:
                dbfs, state, present = None, "unknown", False
            apply_meter(bar, dbfs, state)
            if getattr(lbl, "_sig", False) != present:
                lbl._sig = present
                for w in (lbl, getattr(lbl, "_peer", None)):
                    if w is not None:
                        (w.add_css_class if present else w.remove_css_class)("sig")
                        if isinstance(w, VerticalLabel):
                            w.queue_draw()
            tip = f"{base}\n{mtr.describe(dbfs, state, present)}" if d and self.meters_on else base
            if getattr(bar, "_tip", None) != tip:
                bar._tip = tip
                lbl.set_tooltip_text(tip)
                if getattr(lbl, "_peer", None) is not None:
                    lbl._peer.set_tooltip_text(tip)

    def _sync_state(self, devices):
        by_name = {}
        for d in devices:
            by_name[d.get("name")] = d
            by_name[d["server_name"]] = d
        active = set()
        for d in devices:
            for s in d.get("subscriptions") or []:
                if not s.get("tx_device") or not s.get("tx_channel"):
                    continue
                td = by_name.get(s["tx_device"])
                if not td:
                    continue
                for n, ch in sorted_channels(td["channels"]["transmitters"]):
                    if s["tx_channel"] in (ch.get("friendly_name"), ch.get("name")):
                        active.add((d["server_name"], s["rx_channel_number"], td["server_name"], n))
                        break
        self._updating = True
        try:
            for key, btn in self.cells.items():
                want = key in active
                if btn.get_active() != want:
                    btn.set_active(want)
                btn.remove_css_class("cell-pending")
        finally:
            self._updating = False

    def _toggled(self, btn, rx_dev, rx_num, tx_dev, tx_ch, tx_num):
        if self._updating:
            return
        btn.add_css_class("cell-pending")
        # Radio behaviour: a receiver channel has at most one source.
        if btn.get_active():
            for (rs, rn, ts, tn), other in self.cells.items():
                if rs == rx_dev["server_name"] and rn == rx_num and other is not btn and other.get_active():
                    self._updating = True
                    other.set_active(False)
                    self._updating = False
        self.on_toggle(btn.get_active(), rx_dev, rx_num, tx_dev, tx_ch, tx_num)


class DeviceDetail(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.device = None

    def show_device(self, d):
        self.device = d
        # clear groups
        for g in getattr(self, "_groups", []):
            self.remove(g)
        self._groups = []
        self._clock_rows = {}
        self._meter_bars = {}
        if d is None:
            return
        name = d.get("name") or d["server_name"]

        info = Adw.PreferencesGroup(title=name, description=d["server_name"])
        back = Gtk.Button(label="Show in Routing", valign=Gtk.Align.CENTER)
        back.connect("clicked", lambda _b: self.win.stack.set_visible_child_name("routing"))
        info.set_header_suffix(back)
        for title, val in [
            ("Status", "Online" if d.get("online") else "Offline"),
            ("IPv4", d.get("ipv4")), ("MAC address", d.get("mac_address")),
            ("Model kind", d.get("kind")),
            ("Audio", " · ".join(x for x in (
                f"{d['sample_rate_hz']} Hz" if d.get("sample_rate_hz") else None,
                f"{d['encoding']}-bit" if d.get("encoding") else None,
                f"{d['latency_ms']} ms latency" if d.get("latency_ms") is not None else None) if x)),
            ("Channels", f"{d.get('tx_count', 0)} transmit / {d.get('rx_count', 0)} receive"),
        ]:
            r = Adw.ActionRow(title=title, subtitle=str(val) if val not in (None, "") else "—")
            r.set_subtitle_selectable(True)
            info.add(r)
        self._add(info)
        self._build_clock(d)

        actions = Adw.PreferencesGroup(title="Device")
        rn = Adw.EntryRow(title="Device name", text=name, show_apply_button=True)
        rn.connect("apply", lambda row: self.win.do(
            lambda c: c.rename_device(d["server_name"], row.get_text()), f"Renamed to “{row.get_text()}”"))
        actions.add(rn)
        sr = Adw.ComboRow(title="Sample rate", model=Gtk.StringList.new([f"{r} Hz" for r in SAMPLE_RATES]))
        cur = d.get("sample_rate_hz")
        if cur in SAMPLE_RATES:
            sr.set_selected(SAMPLE_RATES.index(cur))
        sr.connect("notify::selected", self._rate_changed, d, cur)
        actions.add(sr)
        idr = Adw.ActionRow(title="Identify", subtitle="Flash the device’s indicator light")
        b = Gtk.Button(label="Identify", valign=Gtk.Align.CENTER)
        b.connect("clicked", lambda _b: self.win.do(lambda c: c.identify(d["server_name"]), "Identify sent"))
        idr.add_suffix(b)
        actions.add(idr)
        self._add(actions)

        for kind, key, title in (("tx", "transmitters", "Transmit channels"), ("rx", "receivers", "Receive channels")):
            chans = sorted_channels(d["channels"][key])
            if not chans:
                continue
            g = Adw.PreferencesGroup(title=title)
            for n, ch in chans:
                row = Adw.EntryRow(title=f"Channel {n}", text=ch_label(ch, n), show_apply_button=True)
                row.set_sensitive(ch.get("can_rename") is not False)
                mbar = make_meter(vertical=False, visible=self.win.meters_on)
                mbar.set_size_request(70, 6)
                row.add_suffix(mbar)
                self._meter_bars[(kind, n)] = mbar
                row.connect("apply", lambda rw, kind=kind, n=n: self.win.do(
                    lambda c: c.rename_channel(d["server_name"], kind, n, rw.get_text()),
                    f"Channel {n} renamed"))
                g.add(row)
            self._add(g)

    CLOCK_ROWS = (("role", "Clock role"), ("sync", "Sync status"), ("servo", "Servo / clock state"),
                  ("offset", "Frequency offset"), ("drift", "Max drift"), ("gm", "Grandmaster (domain leader)"),
                  ("master", "Syncing to"), ("mute", "Audio mute"), ("ident", "PTP identity"),
                  ("ptp", "PTP settings"))

    def _build_clock(self, d):
        g = Adw.PreferencesGroup(title="Clock &amp; sync",
                                 description="PTP clock status reported by the device")
        rows = {}
        for key, title in self.CLOCK_ROWS:
            r = Adw.ActionRow(title=title, subtitle="—")
            r.set_subtitle_selectable(True)
            if key == "sync":
                dot = make_dot()
                r.add_suffix(dot)
                rows["dot"] = dot
            g.add(r)
            rows[key] = r
        pl = Adw.SwitchRow(title="Preferred leader",
                           subtitle="Prefer this device as the network’s clock leader")
        self._pl_updating = False
        pl.connect("notify::active", self._pl_toggled, d["server_name"])
        g.add(pl)
        rows["pl"] = pl
        ports = (d.get("clock_status") or {}).get("clock_port_records") or []
        if ports:
            ex = Adw.ExpanderRow(title="Clock ports", subtitle=f"{len(ports)} port record(s)")
            for p in ports:
                bits = [str(p.get("role") or "").strip(), str(p.get("state") or "").strip(),
                        p.get("transport_path"), f"PTPv{p['ptp_version']}" if p.get("ptp_version") else None,
                        "LINK DOWN" if p.get("link_down") else None]
                ex.add_row(Adw.ActionRow(title=f"Port {p.get('record_number', '?')}",
                                         subtitle=" · ".join(str(b) for b in bits if b)))
            g.add(ex)
        self._add(g)
        self._clock_rows = rows
        self.update_live(d, self.win.clock_summary)

    def update_live(self, d, summ):
        """Refresh clock values in place (no rebuild, so scroll/focus are preserved)."""
        rows = getattr(self, "_clock_rows", None)
        if not rows or d is None:
            return
        cs = d.get("clock_status") or {}
        info = (summ or {}).get("per", {}).get(d["server_name"], {})
        dash = "—"

        def put(k, v):
            rows[k].set_subtitle(str(v) if v not in (None, "") else dash)
        if not cs or cs.get("status_supported") is False:
            for k, _t in self.CLOCK_ROWS:
                put(k, None)
            put("sync", "Not reported by this device")
            set_dot(rows["dot"], "unknown")
            rows["pl"].set_sensitive(False)
            return
        role = cs.get("clock_role")
        put("role", f"{role}{' · grandmaster' if info.get('is_grandmaster') else ''}" if role else None)
        put("sync", cs.get("synchronization"))
        set_dot(rows["dot"], info.get("health", "unknown"))
        put("servo", " / ".join(str(x) for x in (cs.get("servo_state"), cs.get("clock_state")) if x))
        off = cs.get("clock_frequency_offset_parts_per_billion")
        put("offset", f"{off:+d} ppb" if isinstance(off, int) else None)
        dr = cs.get("maximum_drift_parts_per_billion")
        put("drift", f"{dr} ppb" if dr is not None else None)
        gm, gid = info.get("grandmaster"), clk.pretty(clk.grandmaster_id(cs))
        put("gm", gm if gm == gid or not gid else f"{gm} ({gid})")
        put("master", info.get("master"))
        reasons = ", ".join(cs.get("mute_reasons") or [])
        put("mute", " · ".join(x for x in (cs.get("mute_state"), reasons) if x))
        put("ident", clk.pretty(cs.get("ptpv2_device_identity") or cs.get("ptpv1_device_uuid")))
        ptp = []
        if cs.get("ptpv2_domain") is not None:
            ptp.append(f"domain {cs['ptpv2_domain']}")
        if cs.get("ptpv2_priority1") is not None:
            ptp.append(f"priority {cs['ptpv2_priority1']}/{cs.get('ptpv2_priority2')}")
        if cs.get("ptpv2_clock_class") is not None:
            ptp.append(f"class {cs['ptpv2_clock_class']}")
        if cs.get("follower_only"):
            ptp.append("follower only")
        put("ptp", " · ".join(ptp))
        pl = rows["pl"]
        self._pl_updating = True
        pl.set_active(bool(cs.get("preferred_leader")))
        self._pl_updating = False
        avail = (d.get("clock_control_availability") or {}).get("preferred_leader", False)
        pl.set_sensitive(bool(avail) and not cs.get("preferred_leader_locked"))

    def set_meters_visible(self, on):
        for bar in getattr(self, "_meter_bars", {}).values():
            bar.set_visible(on)
            if not on:
                apply_meter(bar, None, "unknown")

    def update_meters(self, d, data):
        ent = data.get(d["server_name"]) if d else None
        for (kind, n), bar in getattr(self, "_meter_bars", {}).items():
            if ent:
                dbfs, state = ent[kind].get(n, (None, "unknown"))
            else:
                dbfs, state = None, "unknown"
            apply_meter(bar, dbfs, state)
            bar.set_tooltip_text(mtr.describe(dbfs, state, ent["%s_present" % kind].get(n, False)) if ent else None)

    def _pl_toggled(self, row, _p, server_name):
        if self._pl_updating:
            return
        on = row.get_active()
        self.win.do(lambda c: c.set_preferred_leader(server_name, on),
                    "Set as preferred leader" if on else "Preferred leader cleared")

    def _rate_changed(self, combo, _p, d, cur):
        rate = SAMPLE_RATES[combo.get_selected()]
        if rate != cur:
            self.win.do(lambda c: c.set_sample_rate(d["server_name"], rate), f"Sample rate set to {rate} Hz")

    def _add(self, g):
        self._groups.append(g)
        self.add(g)


class Window(Adw.ApplicationWindow):
    def __init__(self, app, client, cfg):
        super().__init__(application=app, title="NetAudio", default_width=1200, default_height=760)
        self.client, self.cfg = client, cfg
        self._gen = 0
        self.iface = None                   # last /settings reply
        self._iface_checked = False
        self.meters_on = False
        self.feed = None
        self._metered = set()
        self.clock_summary = {"per": {}, "grandmaster": None, "synced": 0, "total": 0}
        self.devs = {}
        self.busy = False
        self.selected = None

        self.toasts = Adw.ToastOverlay()
        tv = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Rescan devices (F5)")
        refresh.connect("clicked", lambda _b: self.refresh(rescan=True))
        header.pack_start(refresh)
        self.meter_btn = Gtk.ToggleButton(icon_name="audio-volume-high-symbolic",
                                          tooltip_text="Show live audio meters and signal presence")
        header.pack_start(self.meter_btn)
        self.spinner = Gtk.Spinner()
        header.pack_start(self.spinner)
        menu = Gio.Menu()
        menu.append("Network interface…", "app.interface")
        menu.append("Demo mode", "app.demo")
        menu.append("Preferences", "app.preferences")
        menu.append("About NetAudio Desktop", "app.about")
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, primary=True))
        tv.add_top_bar(header)

        self.routing = RoutingView(self._route_toggled, self._rename_channel, self._open_device)
        self.stack.add_titled_with_icon(self.routing, "routing", "Routing", "network-transmit-receive-symbolic")

        split = self.split = Adw.NavigationSplitView()
        self.dev_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.dev_list.add_css_class("navigation-sidebar")
        self.dev_list.connect("row-selected", self._dev_selected)
        self.dev_list.set_filter_func(self._dev_filter)
        self.dev_search = Gtk.SearchEntry(placeholder_text="Search devices", margin_top=8, margin_bottom=4,
                                          margin_start=8, margin_end=8)
        self.dev_search.connect("search-changed", lambda *_: self.dev_list.invalidate_filter())
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        side.append(self.dev_search)
        side.append(Gtk.ScrolledWindow(child=self.dev_list, vexpand=True))
        side_page = Adw.NavigationPage(title="Devices", child=side)
        self.detail = DeviceDetail(self)
        self.detail_stack = Gtk.Stack()
        self.detail_stack.add_named(Adw.StatusPage(icon_name="computer-symbolic", title="Select a device",
                                                   description="Pick a device on the left to see its clock, "
                                                               "channels and settings. You can also click a "
                                                               "device name on the Routing tab."), "empty")
        self.detail_stack.add_named(self.detail, "detail")
        self.detail_page = Adw.NavigationPage(title="Device", child=self.detail_stack)
        split.set_sidebar(side_page)
        split.set_content(self.detail_page)
        self.stack.add_titled_with_icon(split, "devices", "Devices", "computer-symbolic")

        self._real_store = presets_mod.PresetStore(Path(GLib.get_user_data_dir()) / "netaudio-desktop" / "presets")
        self.preset_store = self._real_store
        self.presets = PresetsView(self)
        self.stack.add_titled_with_icon(self.presets, "presets", "Presets", "document-save-symbolic")

        self.demo_banner = Adw.Banner(title="Demo mode — simulated devices, nothing is sent to your network",
                                      button_label="Exit Demo", action_name="app.demo")
        self.status = Adw.Banner(revealed=False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(self.demo_banner)
        box.append(self.status)
        box.append(self.stack)
        self.stack.set_vexpand(True)
        tv.set_content(box)
        tv.add_bottom_bar(self._build_statusbar())
        self.toasts.set_child(tv)
        self.set_content(self.toasts)

        key = Gtk.ShortcutController()

        def shortcut(trigger, fn):
            key.add_shortcut(Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string(trigger),
                                              Gtk.CallbackAction.new(lambda *_: (fn(), True)[1])))
        shortcut("F5", lambda: self.refresh(rescan=True))
        shortcut("<Primary>1", lambda: self.stack.set_visible_child_name("routing"))
        shortcut("<Primary>2", lambda: self.stack.set_visible_child_name("devices"))
        shortcut("<Primary>3", lambda: self.stack.set_visible_child_name("presets"))
        shortcut("<Primary>m", lambda: self.meter_btn.set_active(not self.meter_btn.get_active()))
        shortcut("<Primary>f", self._focus_search)
        self.add_controller(key)

        GLib.timeout_add_seconds(POLL_SECONDS, self._tick)
        GLib.timeout_add(100, self._meter_tick)
        self.connect("close-request", self._on_close)
        self._apply_mode()
        self.meter_btn.connect("toggled", lambda b: self.set_meters(b.get_active()))
        if cfg.get("meters"):
            self.meter_btn.set_active(True)
        self.connect_daemon()

    # --- presets ---
    def _seed_demo_presets(self):
        names = [d["server_name"] for d in self.client.d.values()]
        cap = self.client.capture_preset(names, "Default routing", ["routing", "audio"])
        self.preset_store.save("Default routing", cap["xml"], {
            "devices": [d["name"] for d in self.client.d.values()], "sections": ["routing", "audio"],
            "device_count": cap["device_count"], "omitted": [], "saved_at": cap["saved_at"][:19]})

    def presets_save(self):
        if not any(d.get("online", True) for d in self.devs.values()):
            self.toast("No devices found yet — connect to a Dante network or try Demo mode")
            return
        SaveDialog(self)

    def presets_restore(self, meta):
        if not self.devs:
            self.toast("No devices found yet")
            return
        RestoreDialog(self, meta)

    # --- network interface ---
    @staticmethod
    def _usable_ifaces(settings):
        return [i for i in (settings or {}).get("network_interfaces", []) if i.get("addresses")]

    def _iface_text(self, settings):
        names = (settings or {}).get("dante_interfaces") or []
        return ", ".join(names) if names else "all interfaces"

    def _startup_interface_check(self):
        """On launch: if there is more than one usable interface and none has been chosen yet
        (or the user asked to be asked every time), let them pick; otherwise re-apply the saved choice."""
        if self._iface_checked:
            return
        self._iface_checked = True
        client = self.client

        def done(res, err):
            if err or client is not self.client:
                return
            self.iface = res
            self.sb_iface.set_label(f"Network: {self._iface_text(res)}")
            choice = self.cfg.get("interface_choice")          # None = never chosen
            if len(self._usable_ifaces(res)) > 1 and (choice is None or self.cfg.get("ask_every_launch")):
                if not getattr(client, "demo", False):          # demo: only via the menu / status bar
                    self._show_interface_dialog(res)
            elif choice is not None and set(choice) != set(res.get("dante_interfaces") or []) \
                    and not res.get("dante_interfaces_fixed"):
                self._apply_interfaces(choice, quiet=True)
        run_async(lambda: client.settings(), done)

    def _choose_interface(self):
        client = self.client

        def done(res, err):
            if err:
                self.toast(f"Couldn't read network interfaces: {err}")
                return
            self.iface = res
            self._show_interface_dialog(res)
        run_async(lambda: client.settings(), done)

    def _show_interface_dialog(self, settings):
        ifaces = sorted(settings.get("network_interfaces", []), key=lambda i: (not i.get("running"), i["name"]))
        current = set(settings.get("dante_interfaces") or self.cfg.get("interface_choice") or [])
        if not current:
            usable = [i for i in ifaces if i.get("addresses") and i.get("running")]
            if len(usable) == 1:
                current = {usable[0]["name"]}
        body = ("Pick the network interface your Dante devices are connected to. Choose two for a redundant "
                "(primary + secondary) network, or none to listen on every interface.")
        if settings.get("dante_interfaces_fixed"):
            body += "\n\nThe daemon was started with a fixed interface, so changes can’t be applied until it is restarted."
        dlg = Adw.AlertDialog(heading="Choose your Dante network", body=body)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        lb.add_css_class("boxed-list")
        checks = {}
        for i in ifaces:
            addrs = ", ".join(i.get("addresses") or []) or "no IPv4 address"
            sub = addrs + ("" if i.get("running") else " · link down")
            row = Adw.ActionRow(title=i["name"], subtitle=sub)
            chk = Gtk.CheckButton(valign=Gtk.Align.CENTER, active=i["name"] in current)
            row.add_prefix(chk)
            row.set_activatable_widget(chk)
            if not i.get("addresses"):
                row.add_css_class("dim-label")
            lb.append(row)
            checks[i["name"]] = chk
        box.append(lb)
        ask = Adw.SwitchRow(title="Ask every time I launch", active=bool(self.cfg.get("ask_every_launch")))
        lb2 = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        lb2.add_css_class("boxed-list")
        lb2.append(ask)
        box.append(lb2)
        dlg.set_extra_child(box)
        dlg.add_response("skip", "Not Now")
        dlg.add_response("use", "Use Selection")
        dlg.set_response_appearance("use", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("use")
        dlg.set_close_response("skip")

        def on_response(_d, resp):
            self.cfg["ask_every_launch"] = ask.get_active()
            if resp == "use":
                self._apply_interfaces([n for n, c in checks.items() if c.get_active()])
            else:
                if self.cfg.get("interface_choice") is None:     # don't nag again next launch
                    self.cfg["interface_choice"] = list(settings.get("dante_interfaces") or [])
                save_config(self.cfg)
        dlg.connect("response", on_response)
        dlg.present(self)

    def _apply_interfaces(self, names, quiet=False):
        client = self.client

        def done(res, err):
            if err:
                self.toast(f"Couldn’t change interface: {err}")
                return
            self.cfg["interface_choice"] = list(names)
            save_config(self.cfg)
            if isinstance(res, dict) and "network_interfaces" in res:
                self.iface = res
            else:
                self.iface = dict(self.iface or {}, dante_interfaces=list(names))
            self.sb_iface.set_label(f"Network: {self._iface_text(self.iface)}")
            if not quiet:
                self.toast(f"Using {', '.join(names) if names else 'all interfaces'} for Dante")
            self.refresh(rescan=True)
        run_async(lambda: client.set_interfaces(names), done)

    # --- metering ---
    def set_meters(self, on):
        if on == self.meters_on:
            return
        self.meters_on = on
        self.cfg["meters"] = on
        save_config(self.cfg)
        self.routing.set_meters_visible(on)
        self.detail.set_meters_visible(on)
        if on:
            self._start_metering()
        else:
            self._stop_metering()

    def _start_metering(self):
        self.feed = self.client.make_meter_feed()
        self.feed.start()
        self._sync_metering()

    def _sync_metering(self):
        """Ask every online device to stream meters (idempotent)."""
        if not self.meters_on:
            return
        for d in self.devs.values():
            sn = d["server_name"]
            if d.get("online", True) and sn not in self._metered:
                self._metered.add(sn)
                client = self.client
                run_async(lambda c=client, s=sn: c.start_metering(s),
                          lambda _r, err, s=sn: self._metered.discard(s) if err else None)

    def _stop_metering(self, wait=False):
        if self.feed:
            self.feed.close()
            self.feed = None
        client, targets = self.client, list(self._metered)
        self._metered.clear()
        threads = []
        for sn in targets:
            def work(s=sn):
                try:
                    client.stop_metering(s)
                except Exception:  # noqa: BLE001 - best effort
                    pass
            t = threading.Thread(target=work, daemon=True)
            t.start()
            threads.append(t)
        if wait:
            deadline = time.time() + 1.5
            for t in threads:
                t.join(max(0.0, deadline - time.time()))

    def _meter_tick(self):
        if self.meters_on and self.feed:
            data = self.feed.read()
            self.routing.update_meters(data)
            self.detail.update_meters(self.devs.get(self.selected), data)
        return True

    def _on_close(self, *_):
        if self.meters_on:
            self._stop_metering(wait=True)
        return False

    # --- status bar ---
    def _build_statusbar(self):
        bar = Gtk.Box(spacing=10)
        bar.add_css_class("statusbar")
        bar.add_css_class("toolbar")

        def sep():
            sp = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
            sp.add_css_class("statusbar-sep")
            return sp
        self.sb_conn_dot, self.sb_conn = make_dot(), Gtk.Label(label="Connecting…", xalign=0)
        self.sb_iface = Gtk.Button(label="Network: —", has_frame=False,
                                   tooltip_text="Choose which network interface Dante uses")
        self.sb_iface.connect("clicked", lambda _b: self._choose_interface())
        self.sb_devices = Gtk.Label(label="", xalign=0)
        self.sb_routes = Gtk.Label(label="", xalign=0)
        self.sb_clock_dot, self.sb_clock = make_dot(), Gtk.Label(label="Clock: —", xalign=0)
        self.sb_updated = Gtk.Label(label="", xalign=1, hexpand=True, halign=Gtk.Align.END)
        self.sb_updated.add_css_class("dim-label")
        for w in (self.sb_conn_dot, self.sb_conn, sep(), self.sb_iface, sep(), self.sb_devices, sep(), self.sb_routes, sep(),
                  self.sb_clock_dot, self.sb_clock, self.sb_updated):
            bar.append(w)
        return bar

    def _update_status(self, err=None):
        demo = getattr(self.client, "demo", False)
        if err:
            set_dot(self.sb_conn_dot, "bad")
            self.sb_conn.set_label("Disconnected")
            self.sb_conn.set_tooltip_text(err)
        elif demo:
            set_dot(self.sb_conn_dot, "warn")
            self.sb_conn.set_label("Demo mode")
            self.sb_conn.set_tooltip_text("Simulated devices")
        else:
            set_dot(self.sb_conn_dot, "good")
            self.sb_conn.set_label(f"Daemon connected · {self.client.base.split('//')[-1]}")
            self.sb_conn.set_tooltip_text(None)
        devs = list(self.devs.values())
        online = sum(1 for d in devs if d.get("online", True))
        self.sb_devices.set_label(f"{online} of {len(devs)} device{'s' if len(devs) != 1 else ''} online"
                                  if devs else "No devices")
        routes = sum(1 for d in devs for sub in d.get("subscriptions") or [] if sub.get("tx_device"))
        self.sb_routes.set_label(f"{routes} route{'s' if routes != 1 else ''}")
        sm = self.clock_summary
        if sm["total"]:
            gm = sm["grandmaster"] or "unknown"
            self.sb_clock.set_label(f"Clock: grandmaster {gm} · {sm['synced']}/{sm['total']} in sync")
            level = "good" if sm["synced"] == sm["total"] else ("bad" if sm["synced"] == 0 else "warn")
            set_dot(self.sb_clock_dot, level)
            bad = [d.get("name") or d["server_name"] for d in devs
                   if sm["per"].get(d["server_name"], {}).get("health") not in ("good", "unknown", None)]
            self.sb_clock.set_tooltip_text("Not in sync: " + ", ".join(bad) if bad else "All devices in sync")
        else:
            self.sb_clock.set_label("Clock: no data")
            set_dot(self.sb_clock_dot, "unknown")
            self.sb_clock.set_tooltip_text(None)
        if not err:
            self.sb_updated.set_label(f"Updated {time.strftime('%H:%M:%S')}")

    # --- demo mode ---
    def set_demo(self, on):
        """Switch between the real daemon and the built-in simulator, live."""
        if on == getattr(self.client, "demo", False):
            return
        self._gen += 1                      # discard results from the previous backend
        self.busy = False
        self._iface_checked, self.iface = False, None
        self.sb_iface.set_label("Network: —")
        if self.meters_on:
            self._stop_metering()
        if on:
            from .demo import DemoClient
            self.client = DemoClient()
        else:
            self.client = Client(port=self.cfg.get("port", DEFAULT_PORT))
        self.devs, self.selected = {}, None
        self.clock_summary = {"per": {}, "grandmaster": None, "synced": 0, "total": 0}
        self._update_status()
        self._dev_sig = self._detail_snap = None
        self.routing.update({})
        self._update_device_list()
        self.detail.show_device(None)
        self.detail_stack.set_visible_child_name("empty")
        self._apply_mode()
        self._set_banner(None)
        if self.meters_on:
            self._start_metering()
        self.connect_daemon()

    def _apply_mode(self):
        demo = getattr(self.client, "demo", False)
        if demo:
            self.preset_store = presets_mod.PresetStore(None)        # simulated: never touches your real presets
            self._seed_demo_presets()
        else:
            self.preset_store = self._real_store
        self.presets.reload()
        self.demo_banner.set_revealed(demo)
        self.set_title("NetAudio — Demo" if demo else "NetAudio")

    # --- daemon / polling ---
    def connect_daemon(self):
        self.spinner.start()

        def done(started, err):
            if err:
                self._set_banner(err, "Retry", self.connect_daemon)
                self._update_status(err)
                self.spinner.stop()
                if not self.devs:
                    self.routing.update({})   # show the empty page (with its Demo button)
            else:
                self._set_banner(None)
                if started:
                    self.toast("Started netaudio daemon")
                self._startup_interface_check()
                self.refresh()
        run_async(lambda: ensure_daemon(self.client, self.cfg.get("port", DEFAULT_PORT),
                                        self.cfg.get("auto_start", True)), done)

    def _set_banner(self, text, button=None, cb=None):
        if text is None:
            self.status.set_revealed(False)
            return
        self.status.set_title(text)
        self.status.set_button_label(button)
        if getattr(self, "_banner_handler", None):
            self.status.disconnect(self._banner_handler)
            self._banner_handler = None
        if cb:
            self._banner_handler = self.status.connect("button-clicked", lambda _b: cb())
        self.status.set_revealed(True)

    def _tick(self):
        self.refresh()
        return True

    def refresh(self, rescan=False):
        if self.busy:
            return
        self.busy = True
        gen = self._gen
        client = self.client
        if rescan:
            self.spinner.start()

        def fetch():
            if rescan:
                try:
                    client.refresh()
                except ApiError:
                    pass
            return client.devices()

        def done(devs, err):
            if gen != self._gen:
                return
            self.busy = False
            self.spinner.stop()
            if err:
                self._set_banner(err, "Reconnect", self.connect_daemon)
                self._update_status(err)
                if not self.devs:
                    self.routing.update({})
                return
            self._set_banner(None)
            self.devs = devs
            self.clock_summary = clk.summarize(devs)
            self.routing.update(devs)
            self._update_device_list()
            self._update_status()
            self._sync_metering()
        run_async(fetch, done)

    # --- device list ---
    def _update_device_list(self):
        devices = sorted(self.devs.values(), key=lambda d: (d.get("name") or d["server_name"]).lower())
        sig = [(d["server_name"], d.get("online")) for d in devices]
        if sig != getattr(self, "_dev_sig", None):
            self._dev_sig = sig
            while (r := self.dev_list.get_first_child()) is not None:
                self.dev_list.remove(r)
            for d in devices:
                row = Adw.ActionRow(title=d.get("name") or d["server_name"],
                                    subtitle=d.get("ipv4") or "", activatable=True)
                row.server_name = d["server_name"]
                row.dot = make_dot()
                row.add_suffix(row.dot)
                if not d.get("online"):
                    row.add_css_class("dim-label")
                    row.set_subtitle(f"{d.get('ipv4') or ''} · offline".strip(" ·"))
                self.dev_list.append(row)
                if d["server_name"] == self.selected:
                    self.dev_list.select_row(row)
        if self.selected and self.selected not in self.devs:       # selected device left the network
            self.selected = None
            self._detail_snap = None
            self.detail.show_device(None)
            self.detail_stack.set_visible_child_name("empty")
        # Clock details change every poll: update the sidebar and detail rows in place.
        row = self.dev_list.get_first_child()
        while row is not None:
            d = self.devs.get(getattr(row, "server_name", None))
            if d is not None and hasattr(row, "dot"):
                info = self.clock_summary["per"].get(d["server_name"], {})
                set_dot(row.dot, info.get("health", "unknown") if d.get("online", True) else "unknown")
                if d.get("online", True):
                    role = info.get("role")
                    tag = "grandmaster ★" if info.get("is_grandmaster") else (role or "")
                    row.set_subtitle(" · ".join(x for x in (d.get("ipv4"), tag) if x))
            row = row.get_next_sibling()
        if self.selected in self.devs:
            self.detail.update_live(self.devs[self.selected], self.clock_summary)
        # Rebuild detail only when its content changed (don't clobber edits while typing).
        if self.selected in self.devs:
            stable = {k: v for k, v in self.devs[self.selected].items() if k != "clock_status"}
            stable["_ports"] = len(((self.devs[self.selected].get("clock_status") or {}).get("clock_port_records")) or [])
            snap = json.dumps(stable, sort_keys=True, default=str)
            if snap != getattr(self, "_detail_snap", None):
                focus = self.get_focus()
                if not isinstance(focus, Gtk.Text):
                    self._detail_snap = snap
                    self.detail.show_device(self.devs[self.selected])

    def _dev_selected(self, _lb, row):
        if row is None:
            return
        self.selected = row.server_name
        self._detail_snap = None
        d = self.devs.get(self.selected)
        self.detail.show_device(d)
        self.detail_stack.set_visible_child_name("detail" if d else "empty")
        self.detail_page.set_title(d.get("name") or self.selected if d else "Device")
        self.split.set_show_content(True)

    def _open_device(self, server_name):
        """Jump to a device's page on the Devices tab (e.g. from a name in the routing matrix)."""
        self.dev_search.set_text("")
        row = self.dev_list.get_first_child()
        while row is not None:
            if getattr(row, "server_name", None) == server_name:
                self.dev_list.select_row(row)
                if self.dev_list.get_selected_row() is row:
                    self._dev_selected(self.dev_list, row)   # already selected: still refresh and reveal
                break
            row = row.get_next_sibling()
        self.stack.set_visible_child_name("devices")

    def _dev_filter(self, row):
        needle = self.dev_search.get_text().strip().lower()
        if not needle:
            return True
        return needle in f"{row.get_title()} {row.get_subtitle() or ''}".lower()

    def _focus_search(self):
        self.stack.set_visible_child_name("devices")
        self.dev_search.grab_focus()

    # --- actions ---
    def toast(self, msg):
        self.toasts.add_toast(Adw.Toast(title=msg, timeout=3))

    def do(self, fn, ok_msg):
        def done(_res, err):
            self.toast(ok_msg if not err else f"Failed: {err}")
            self.refresh(rescan=False)
        run_async(lambda: fn(self.client), done)

    def _rename_channel(self, kind, dev, num, name):
        self.do(lambda c: c.rename_channel(dev["server_name"], kind, num, name),
                f"Renamed {'transmit' if kind == 'tx' else 'receive'} channel {num} to “{name}”")

    def _route_toggled(self, on, rx_dev, rx_num, tx_dev, tx_ch, tx_num):
        rx = rx_dev["server_name"]
        tx_name = tx_dev.get("name") or tx_dev["server_name"]
        if on:
            label = tx_ch.get("friendly_name") or tx_ch.get("name") or str(tx_num)
            fn = lambda c: c.subscribe(rx, rx_num, tx_name, label)  # noqa: E731
            msg = f"Routed {tx_name} ch {tx_num} → {rx_dev.get('name') or rx} ch {rx_num}"
        else:
            fn = lambda c: c.unsubscribe(rx, rx_num)  # noqa: E731
            msg = f"Cleared {rx_dev.get('name') or rx} ch {rx_num}"
        self.do(fn, msg)


class PrefsDialog(Adw.PreferencesDialog):
    def __init__(self, cfg, on_save):
        super().__init__(title="Preferences")
        page = Adw.PreferencesPage()
        g = Adw.PreferencesGroup(title="Daemon", description="NetAudio Desktop talks to the local netaudio daemon.")
        self.port = Adw.SpinRow.new_with_range(1024, 65535, 1)
        self.port.set_title("HTTP port")
        self.port.set_value(cfg.get("port", DEFAULT_PORT))
        self.auto = Adw.SwitchRow(title="Start daemon automatically", active=cfg.get("auto_start", True))
        g.add(self.port)
        g.add(self.auto)
        page.add(g)
        net = Adw.PreferencesGroup(title="Network",
                                   description="Change the interface any time from the status bar or the ☰ menu.")
        self.ask = Adw.SwitchRow(title="Ask which network interface on launch",
                                 subtitle="Otherwise your last choice is remembered",
                                 active=bool(cfg.get("ask_every_launch")))
        net.add(self.ask)
        page.add(net)
        self.add(page)
        self.connect("closed", lambda *_: on_save({"port": int(self.port.get_value()),
                                                     "auto_start": self.auto.get_active(),
                                                     "ask_every_launch": self.ask.get_active()}))


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.win = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        from gi.repository import Gdk
        # Use our own icon even when running from a source checkout (not installed system-wide).
        theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        for d in (Path(__file__).resolve().parent.parent / "data",
                  Path(os.environ.get("SNAP", "/nonexistent")) / "usr/share/icons/hicolor/scalable/apps"):
            if d.is_dir():
                theme.add_search_path(str(d))
        Gtk.Window.set_default_icon_name(ICON_NAME)
        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        for name, cb in (("preferences", self._prefs), ("about", self._about), ("quit", lambda *_: self.quit())):
            a = Gio.SimpleAction.new(name, None)
            a.connect("activate", cb)
            self.add_action(a)
        ia = Gio.SimpleAction.new("interface", None)
        ia.connect("activate", lambda *_: self.win and self.win._choose_interface())
        self.add_action(ia)
        self.demo_action = Gio.SimpleAction.new_stateful("demo", None, GLib.Variant.new_boolean(DEMO))
        self.demo_action.connect("change-state", self._toggle_demo)
        self.add_action(self.demo_action)
        self.set_accels_for_action("app.quit", ["<Primary>q"])

    def do_activate(self):
        if not self.win:
            self.cfg = load_config()
            if DEMO:
                from .demo import DemoClient
                client = DemoClient()
            else:
                client = Client(port=self.cfg.get("port", DEFAULT_PORT))
            self.win = Window(self, client, self.cfg)
        self.win.present()

    def _toggle_demo(self, action, value):
        # GLib flips boolean actions itself and asks us to apply the requested state.
        action.set_state(value)
        if self.win:
            self.win.set_demo(value.get_boolean())

    def _prefs(self, *_):
        def save(new):
            changed = new["port"] != self.cfg.get("port", DEFAULT_PORT)
            self.cfg.update(new)
            save_config(self.cfg)
            if changed and not getattr(self.win.client, "demo", False):
                self.win.client = Client(port=self.cfg["port"])
                self.win._iface_checked = False
                self.win.connect_daemon()
        PrefsDialog(self.cfg, save).present(self.win)

    def _about(self, *_):
        Adw.AboutDialog(application_name="NetAudio Desktop", application_icon=ICON_NAME,
                        version=__version__, developer_name="Unofficial",
                        comments="A native Linux front end for the NetAudio daemon "
                                 "(chris-ritsen/network-audio-controller). Not affiliated with Audinate.",
                        website="https://netaudio.app/linux", license_type=Gtk.License.MIT_X11).present(self.win)


DEMO = False


def main():
    global DEMO
    argv = list(sys.argv)
    if "--demo" in argv or os.environ.get("NETAUDIO_DESKTOP_DEMO"):
        DEMO = True
        argv = [a for a in argv if a != "--demo"]
    return App().run(argv)
