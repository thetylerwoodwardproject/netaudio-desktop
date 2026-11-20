"""Presets tab: save the current device configuration, and restore it with a reviewed plan.

Safety model (mirrors the daemon's): capture is read-only; restore always shows a fresh plan of what
would change first, and nothing is written until the user confirms the plan.
"""
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from . import presets as P  # noqa: E402
from .util import run_async  # noqa: E402


def pretty_when(ts):
    try:
        return time.strftime("%b %-d, %H:%M", time.strptime((ts or "")[:19], "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return ""


def _dialog_shell(title, width, height, cancel_label="Cancel"):
    """Adw.Dialog with a header bar holding Cancel (start) and returns (dialog, toolbar, cancel, headerbar)."""
    dlg = Adw.Dialog(title=title, content_width=width, content_height=height)
    tv = Adw.ToolbarView()
    hb = Adw.HeaderBar(show_start_title_buttons=False, show_end_title_buttons=False)
    cancel = Gtk.Button(label=cancel_label)
    cancel.connect("clicked", lambda _b: dlg.close())
    hb.pack_start(cancel)
    tv.add_top_bar(hb)
    dlg.set_child(tv)
    return dlg, tv, cancel, hb


def _badge(text, kind):
    lbl = Gtk.Label(label=text, valign=Gtk.Align.CENTER)
    lbl.add_css_class("caption-heading")
    lbl.add_css_class({"change": "accent", "unchanged": "dim-label"}.get(kind, "warning"))
    return lbl


class PresetsView(Gtk.Stack):
    def __init__(self, win):
        super().__init__(vexpand=True)
        self.win = win
        self._rows = []

        empty = Adw.StatusPage(icon_name="document-save-symbolic", title="No presets yet",
                               description="Save your current routing and device settings so you can bring them "
                                           "back later — for a show, a venue, or as a quick undo.")
        save = Gtk.Button(label="Save Current Setup…", halign=Gtk.Align.CENTER)
        save.add_css_class("pill")
        save.add_css_class("suggested-action")
        save.connect("clicked", lambda _b: win.presets_save())
        imp = Gtk.Button(label="Import a Preset File…", halign=Gtk.Align.CENTER)
        imp.add_css_class("pill")
        imp.connect("clicked", lambda _b: self.import_file())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, halign=Gtk.Align.CENTER)
        box.append(save)
        box.append(imp)
        empty.set_child(box)
        self.add_named(empty, "empty")

        self.page = Adw.PreferencesPage()
        self.group = Adw.PreferencesGroup(
            title="Saved presets",
            description="Restoring always shows what will change first. Nothing is applied until you confirm.")
        actions = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        imp2 = Gtk.Button(label="Import…", valign=Gtk.Align.CENTER)
        imp2.connect("clicked", lambda _b: self.import_file())
        save2 = Gtk.Button(label="Save Current Setup…", valign=Gtk.Align.CENTER)
        save2.add_css_class("suggested-action")
        save2.connect("clicked", lambda _b: win.presets_save())
        actions.append(imp2)
        actions.append(save2)
        self.group.set_header_suffix(actions)
        self.page.add(self.group)
        self.add_named(self.page, "list")

    def reload(self):
        for r in self._rows:
            self.group.remove(r)
        self._rows = []
        metas = self.win.preset_store.list()
        if not metas:
            self.set_visible_child_name("empty")
            return
        for m in metas:
            n = m.get("device_count")
            bits = [f"{n} device{'s' if n != 1 else ''}" if n else "Imported file",
                    ", ".join(m.get("sections") or []), pretty_when(m.get("saved_at"))]
            row = Adw.ActionRow(title=m["name"], subtitle=" · ".join(b for b in bits if b))
            row.set_use_markup(False)
            exp = Gtk.Button(icon_name="document-send-symbolic", valign=Gtk.Align.CENTER,
                             tooltip_text="Export as an XML file")
            exp.add_css_class("flat")
            exp.connect("clicked", lambda _b, m=m: self.export(m))
            dele = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, tooltip_text="Delete")
            dele.add_css_class("flat")
            dele.connect("clicked", lambda _b, m=m: self.delete(m))
            rest = Gtk.Button(label="Restore…", valign=Gtk.Align.CENTER)
            rest.add_css_class("suggested-action")
            rest.connect("clicked", lambda _b, m=m: self.win.presets_restore(m))
            for w in (exp, dele, rest):
                row.add_suffix(w)
            self.group.add(row)
            self._rows.append(row)
        self.set_visible_child_name("list")

    # --- file actions ---
    def export(self, meta):
        dlg = Gtk.FileDialog(title="Export preset", initial_name=f"{meta['slug']}.xml")

        def done(d, res):
            try:
                f = d.save_finish(res)
            except GLib.Error:
                return
            try:
                f.replace_contents(self.win.preset_store.get_xml(meta["slug"]).encode("utf-8"), None, False,
                                   Gio.FileCreateFlags.NONE, None)
                self.win.toast(f"Exported “{meta['name']}”")
            except Exception as e:  # noqa: BLE001
                self.win.toast(f"Export failed: {e}")
        dlg.save(self.win, None, done)

    def import_file(self):
        dlg = Gtk.FileDialog(title="Import preset")
        flt = Gtk.FileFilter(name="Preset files")
        flt.add_suffix("xml")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(flt)
        dlg.set_filters(filters)

        def done(d, res):
            try:
                f = d.open_finish(res)
            except GLib.Error:
                return
            try:
                self.win.preset_store.import_file(f.get_path())
                self.reload()
                self.win.toast("Preset imported")
            except Exception as e:  # noqa: BLE001
                self.win.toast(f"Import failed: {e}")
        dlg.open(self.win, None, done)

    def delete(self, meta):
        a = Adw.AlertDialog(heading=f"Delete “{meta['name']}”?",
                            body="The saved preset file will be removed. Devices are not affected.")
        a.add_response("cancel", "Cancel")
        a.add_response("delete", "Delete")
        a.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        a.set_close_response("cancel")

        def resp(_d, r):
            if r == "delete":
                self.win.preset_store.delete(meta["slug"])
                self.reload()
        a.connect("response", resp)
        a.present(self.win)


class SaveDialog:
    """Choose devices + what to include, then capture them (read-only) and store the preset."""

    def __init__(self, win):
        self.win = win
        self.dlg, tv, self.cancel, hb = _dialog_shell("Save Current Setup", 540, 680)
        self.save_btn = Gtk.Button(label="Save")
        self.save_btn.add_css_class("suggested-action")
        self.save_btn.connect("clicked", lambda _b: self._save())
        hb.pack_end(self.save_btn)

        page = Adw.PreferencesPage()
        g = Adw.PreferencesGroup(title="Name")
        self.name = Adw.EntryRow(title="Preset name", text=f"Setup {time.strftime('%b %-d')}")
        g.add(self.name)
        page.add(g)

        dg = Adw.PreferencesGroup(title="Devices", description="Capture settings from these devices.")
        self.dev_checks = {}
        for d in sorted((x for x in win.devs.values() if x.get("online", True)),
                        key=lambda x: (x.get("name") or "").lower()):
            row = Adw.ActionRow(title=d.get("name") or d["server_name"], subtitle=d.get("ipv4") or "")
            row.set_use_markup(False)
            chk = Gtk.CheckButton(active=True, valign=Gtk.Align.CENTER)
            row.add_prefix(chk)
            row.set_activatable_widget(chk)
            dg.add(row)
            self.dev_checks[d["server_name"]] = (chk, d.get("name") or d["server_name"])
        page.add(dg)

        sg = Adw.PreferencesGroup(title="Include")
        self.sec = {}
        for key, label, desc, default in P.SECTIONS:
            sw = Adw.SwitchRow(title=label, subtitle=desc, active=default)
            sg.add(sw)
            self.sec[key] = sw
        page.add(sg)
        self.status = Adw.PreferencesGroup()
        self.spin_row = Adw.ActionRow(title="Reading devices…", subtitle="This can take up to a minute.",
                                      visible=False)
        self.spinner = Gtk.Spinner(spinning=True, valign=Gtk.Align.CENTER)
        self.spin_row.add_prefix(self.spinner)
        self.status.add(self.spin_row)
        page.add(self.status)
        tv.set_content(page)
        self.dlg.present(win)
        self.name.grab_focus()

    def _busy(self, on):
        self.spin_row.set_visible(on)
        self.save_btn.set_sensitive(not on)
        self.name.set_sensitive(not on)

    def _save(self):
        name = self.name.get_text().strip()
        servers = [sn for sn, (c, _n) in self.dev_checks.items() if c.get_active()]
        sections = [k for k, sw in self.sec.items() if sw.get_active()]
        if not name:
            return self.win.toast("Give the preset a name")
        if not servers:
            return self.win.toast("Select at least one device")
        if not sections:
            return self.win.toast("Choose something to include")
        store = self.win.preset_store
        if store.exists(name):
            a = Adw.AlertDialog(heading=f"Replace “{name}”?", body="A preset with this name already exists.")
            a.add_response("cancel", "Cancel")
            a.add_response("replace", "Replace")
            a.set_response_appearance("replace", Adw.ResponseAppearance.DESTRUCTIVE)
            a.set_close_response("cancel")
            a.connect("response", lambda _d, r: r == "replace" and self._capture(name, servers, sections, True))
            a.present(self.dlg)
        else:
            self._capture(name, servers, sections, False)

    def _capture(self, name, servers, sections, overwrite):
        self._busy(True)
        client = self.win.client
        names = [self.dev_checks[s][1] for s in servers]

        def done(res, err):
            self._busy(False)
            if err:
                return self.win.toast(f"Couldn’t save preset: {err}")
            meta = {"devices": names, "sections": sections, "device_count": res.get("device_count", len(servers)),
                    "omitted": res.get("omitted") or [], "filename": res.get("filename"),
                    "saved_at": (res.get("saved_at") or "")[:19] or None}
            self.win.preset_store.save(name, res["xml"], meta, overwrite=overwrite)
            self.dlg.close()
            self.win.presets.reload()
            self.win.toast(f"Saved “{name}” ({meta['device_count']} device{'s' if meta['device_count'] != 1 else ''})")
            if meta["omitted"]:
                lines = [f"• {o.get('device')} — {o.get('setting')}: {o.get('reason')}" for o in meta["omitted"]]
                a = Adw.AlertDialog(heading="Some settings weren’t captured",
                                    body="These can’t be read from the devices, so they won’t be restored:\n\n"
                                         + "\n".join(lines))
                a.add_response("ok", "OK")
                a.present(self.win)
        run_async(lambda: client.capture_preset(servers, name, sections), done)


class RestoreDialog:
    """Map preset devices onto live ones, show the plan, confirm, apply."""

    def __init__(self, win, meta):
        self.win, self.meta = win, meta
        self.xml = win.preset_store.get_xml(meta["slug"])
        self.client = win.client
        self.rows = {}              # preset device name -> (ComboRow, targets)
        self.plan = None
        self.targets, self.excluded = {}, []
        self._gen = 0
        self._busy = False

        self.dlg, tv, self.cancel, hb = _dialog_shell(f"Restore “{meta['name']}”", 680, 760)
        self.apply_btn = Gtk.Button(label="Apply Changes", sensitive=False)
        self.apply_btn.add_css_class("destructive-action")
        self.apply_btn.connect("clicked", lambda _b: self._confirm())
        hb.pack_end(self.apply_btn)

        page = Adw.PreferencesPage()
        self.dev_group = Adw.PreferencesGroup(
            title="Devices", description="Match each device in the preset to a device on your network.")
        self.change_group = Adw.PreferencesGroup(title="Changes")
        opt = Adw.PreferencesGroup(title="Options")
        self.store_sw = Adw.SwitchRow(title="Also store configuration on the devices",
                                      subtitle="Asks each device to keep these settings across reboots")
        opt.add(self.store_sw)
        self.store_sw.connect("notify::active", lambda *_: self._replan())
        for g in (self.dev_group, self.change_group, opt):
            page.add(g)
        self._change_rows = []
        self._set_loading("Reading preset…")
        tv.set_content(page)
        self.dlg.present(win)

        online = [d["server_name"] for d in win.devs.values() if d.get("online", True)]
        run_async(lambda: self.client.preview_preset(self.xml, online), self._on_preview)

    # --- helpers ---
    def _clear_changes(self):
        for r in self._change_rows:
            self.change_group.remove(r)
        self._change_rows = []

    def _add_change(self, row):
        self.change_group.add(row)
        self._change_rows.append(row)

    def _set_loading(self, text):
        self._clear_changes()
        row = Adw.ActionRow(title=text)
        row.add_prefix(Gtk.Spinner(spinning=True, valign=Gtk.Align.CENTER))
        self._add_change(row)
        self.apply_btn.set_sensitive(False)

    def _set_error(self, text):
        self._clear_changes()
        row = Adw.ActionRow(title="Couldn’t build a plan", subtitle=text, subtitle_lines=0)
        row.set_use_markup(False)
        row.add_prefix(Gtk.Image(icon_name="dialog-warning-symbolic"))
        self._add_change(row)
        self.apply_btn.set_sensitive(False)

    # --- step 1: match devices ---
    def _on_preview(self, res, err):
        if err:
            return self._set_error(err)
        for dev in res.get("devices", []):
            targets = dev.get("targets") or []
            what = ", ".join(f"{s['label']}: {s['value']}" for s in dev.get("settings", [])) or "no settings"
            labels = [f"{t.get('name') or t['id']} · {t.get('address') or '?'}"
                      f"{'' if t.get('online', True) else ' (offline)'}" for t in targets]
            if targets:
                labels.append("Skip this device")
                combo = Adw.ComboRow(title=dev["name"], subtitle=what, subtitle_lines=0,
                                     model=Gtk.StringList.new(labels))
                first_online = next((i for i, t in enumerate(targets) if t.get("online", True)), len(targets))
                combo.set_selected(first_online)
                combo.connect("notify::selected", lambda *_: self._replan())
            else:
                combo = Adw.ComboRow(title=dev["name"], subtitle=f"Not found on the network — skipped · {what}",
                                     subtitle_lines=0, model=Gtk.StringList.new(["Not found"]), sensitive=False)
            combo.set_use_markup(False)
            self.dev_group.add(combo)
            self.rows[dev["name"]] = (combo, targets)
        self._replan()

    def _selection(self):
        targets, excluded = {}, []
        for name, (combo, ts) in self.rows.items():
            i = combo.get_selected()
            if ts and i < len(ts):
                targets[name] = ts[i]["id"]
            else:
                excluded.append(name)
        return targets, excluded

    # --- step 2: plan (read-only) ---
    def _replan(self):
        if self._busy or not self.rows:
            return
        self._gen += 1
        gen = self._gen
        self.targets, self.excluded = self._selection()
        if not self.targets:
            self._clear_changes()
            self._add_change(Adw.ActionRow(title="No devices selected",
                                           subtitle="Match at least one device above to see what would change."))
            self.apply_btn.set_sensitive(False)
            self.apply_btn.set_label("Apply Changes")
            return
        self._set_loading("Comparing with your devices…")
        targets, excluded, store = dict(self.targets), list(self.excluded), self.store_sw.get_active()
        run_async(lambda: self.client.plan_preset(self.xml, targets, excluded, store),
                  lambda res, err: gen == self._gen and self._on_plan(res, err))

    def _on_plan(self, res, err):
        if err:
            return self._set_error(err)
        self.plan = res
        sm = P.summarize_plan(res)
        self.summary = sm
        self._clear_changes()
        c = sm["counts"]
        head = Adw.ActionRow(
            title=f"{sm['changes']} setting{'s' if sm['changes'] != 1 else ''} will change"
                  if sm["changes"] else "Everything already matches",
            subtitle=" · ".join(x for x in (
                f"{c['unchanged']} already set" if c["unchanged"] else "",
                f"{sm['blocked']} can’t be applied and will be skipped" if sm["blocked"] else "") if x)
            or "Nothing to restore.")
        head.add_prefix(Gtk.Image(icon_name="emblem-ok-symbolic" if not sm["changes"] else "view-list-symbolic"))
        self._add_change(head)
        for d in sm["devices"]:
            if not d["actions"]:
                continue
            exp = Adw.ExpanderRow(title=d["device_name"],
                                  subtitle=f"{len(d['actions'])} item{'s' if len(d['actions']) != 1 else ''} to review")
            exp.set_use_markup(False)
            exp.set_expanded(sum(len(x["actions"]) for x in sm["devices"]) <= 8)
            for a in d["actions"]:
                sub = a.get("reason") or ""
                det = a.get("details")
                if isinstance(det, list) and det:
                    sub += ("\n" if sub else "") + "\n".join(P.short(x, 110) for x in det[:6])
                    if len(det) > 6:
                        sub += f"\n…and {len(det) - 6} more"
                elif a.get("requested") is not None and a.get("state") == "change":
                    sub += f"{' · ' if sub else ''}{P.short(a.get('current'))} → {P.short(a.get('requested'))}"
                row = Adw.ActionRow(title=P.KIND_LABELS.get(a.get("kind"), a.get("kind", "?")), subtitle=sub,
                                    subtitle_lines=0)
                row.set_use_markup(False)
                row.add_suffix(_badge(P.STATE_LABELS.get(a.get("state"), a.get("state", "")), a.get("state")))
                exp.add_row(row)
            self._add_change(exp)
        n = sm["changes"]
        self.apply_btn.set_label(f"Apply {n} Change{'s' if n != 1 else ''}" if n else "Apply Changes")
        self.apply_btn.set_sensitive(n > 0)

    # --- step 3: confirm + apply ---
    def _confirm(self):
        n = self.summary["changes"]
        ndev = sum(1 for d in self.summary["devices"] if any(a.get("state") == "change" for a in d["actions"]))
        a = Adw.AlertDialog(
            heading="Apply to your live devices?",
            body=f"This will change {n} setting{'s' if n != 1 else ''} on {ndev} device{'s' if ndev != 1 else ''}. "
                 "Audio may be interrupted while it runs, and routing changes take effect immediately.")
        a.add_response("cancel", "Cancel")
        a.add_response("apply", "Apply")
        a.set_response_appearance("apply", Adw.ResponseAppearance.DESTRUCTIVE)
        a.set_close_response("cancel")
        a.connect("response", lambda _d, r: r == "apply" and self._apply())
        a.present(self.dlg)

    def _apply(self):
        self._busy = True
        self._gen += 1
        self.apply_btn.set_sensitive(False)
        self.cancel.set_sensitive(False)
        self._set_loading("Applying changes… please wait")
        xml, plan, targets, excluded = self.xml, self.plan, dict(self.targets), list(self.excluded)
        store = self.store_sw.get_active()
        digest = plan.get("digest") or P.sha256(xml)

        def done(res, err):
            self._busy = False
            self.dlg.close()
            if err:
                a = Adw.AlertDialog(heading="Restore failed", body=err)
            else:
                ok = res.get("complete")
                a = Adw.AlertDialog(heading="Preset applied" if ok else "Preset applied with issues",
                                    body=P.describe_result(res))
            a.add_response("ok", "OK")
            a.present(self.win)
            self.win.refresh(rescan=True)
        run_async(lambda: self.client.load_preset(xml, digest, targets, excluded, store), done)
