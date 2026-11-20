"""Issues tab: open and recently resolved problems reported by the daemon (/issues)."""
import datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

SEV_ORDER = {"error": 0, "warning": 1, "info": 2}
SEV_ICON = {"error": "dialog-error-symbolic", "warning": "dialog-warning-symbolic",
            "info": "dialog-information-symbolic"}
SEV_CLASS = {"error": "error", "warning": "warning", "info": "accent"}
SEV_LABEL = {"error": "Error", "warning": "Warning", "info": "Notice"}


def parse_ts(ts):
    if not ts:
        return None
    try:
        t = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)
    return t


def ago(ts, now=None):
    t = parse_ts(ts)
    if t is None:
        return ""
    secs = max(0, int(((now or datetime.datetime.now(datetime.timezone.utc)) - t).total_seconds()))
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60} min ago"
    if secs < 86400:
        return f"{secs // 3600} h ago"
    return f"{secs // 86400} d ago"


def sort_issues(issues):
    """Open issues first (errors before warnings, newest first), then resolved (most recent first)."""
    def key(i):
        last = parse_ts(i.get("last_seen")) or datetime.datetime.fromtimestamp(0, datetime.timezone.utc)
        if i.get("state") == "open":
            return (0, SEV_ORDER.get(i.get("severity"), 3), -last.timestamp())
        res = parse_ts(i.get("resolved_at")) or last
        return (1, 0, -res.timestamp())
    return sorted(issues, key=key)


class IssuesView(Gtk.Stack):
    def __init__(self, win):
        super().__init__(vexpand=True)
        self.win = win
        self._sig = None
        self._live = []            # [(row, issue)] for in-place subtitle refresh
        self._groups = []
        self.add_named(Adw.StatusPage(
            icon_name="emblem-ok-symbolic", title="No problems detected",
            description="The daemon isn’t reporting any clock, routing or receive-health issues."), "empty")
        self.page = Adw.PreferencesPage()
        self.add_named(self.page, "list")

    @staticmethod
    def _subtitle(i):
        bits = [i["scope"].get("device_name") or i["scope"].get("server_name"), SEV_LABEL.get(i["severity"], ""),
                ago(i["resolved_at"] if i["state"] == "resolved" else i["last_seen"])]
        if i["state"] == "resolved":
            bits[2] = f"resolved {bits[2]}"
        if i.get("occurrence_count", 1) > 1:
            bits.append(f"seen {i['occurrence_count']}×")
        return " · ".join(b for b in bits if b)

    def _issue_row(self, i):
        row = Adw.ExpanderRow(title=i["title"], subtitle=self._subtitle(i))
        row.set_use_markup(False)
        icon = Gtk.Image(icon_name=SEV_ICON.get(i["severity"], "dialog-information-symbolic"))
        if i["state"] == "resolved":
            icon.add_css_class("dim-label")
        else:
            icon.add_css_class(SEV_CLASS.get(i["severity"], "accent"))
        row.add_prefix(icon)

        def info(title, text):
            r = Adw.ActionRow(title=title, subtitle=text or "—", subtitle_lines=0)
            r.set_use_markup(False)
            r.set_subtitle_selectable(True)
            row.add_row(r)
        info("What’s happening", i.get("summary"))
        if i.get("suggested_remediation"):
            info("Suggested fix", i["suggested_remediation"])
        sc = i.get("scope") or {}
        where = ", ".join(x for x in (f"channel {sc['channel_identity']}" if sc.get("channel_identity") else "",
                                      f"flow {sc['flow_identity']}" if sc.get("flow_identity") else "",
                                      f"interface {sc['interface_identity']}" if sc.get("interface_identity") else "")
                          if x)
        info("Details", " · ".join(x for x in (
            f"First seen {ago(i.get('first_seen'))}", f"last seen {ago(i.get('last_seen'))}",
            where, (i.get("evidence_class") or "").replace("_", " ")) if x))
        go = Adw.ActionRow(title="Open device page", activatable=True)
        go.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
        go.connect("activated", lambda *_: self.win._open_device(sc.get("server_name")))
        row.add_row(go)
        return row

    def update(self, page):
        issues = sort_issues((page or {}).get("issues") or [])
        sig = tuple((i["issue_id"], i["state"], i.get("occurrence_count"), i.get("last_seen")) for i in issues)
        if sig != self._sig:
            self._sig = sig
            for g in self._groups:
                self.page.remove(g)
            self._groups, self._live = [], []
            open_, done = [i for i in issues if i["state"] == "open"], [i for i in issues if i["state"] != "open"]
            if not issues:
                self.set_visible_child_name("empty")
                return
            for title, items, desc in (("Needs attention", open_, "Active problems the daemon is observing"),
                                       ("Recently resolved", done[:15], "Cleared — kept for reference")):
                if not items:
                    continue
                g = Adw.PreferencesGroup(title=title, description=desc)
                for i in items:
                    row = self._issue_row(i)
                    g.add(row)
                    self._live.append((row, i))
                self.page.add(g)
                self._groups.append(g)
            self.set_visible_child_name("list" if self._groups else "empty")
        else:
            for row, i in self._live:         # keep "5 min ago" fresh without collapsing expanded rows
                row.set_subtitle(self._subtitle(i))
