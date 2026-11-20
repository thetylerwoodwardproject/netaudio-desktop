"""Small shared helpers."""
import threading

from gi.repository import GLib

from .api import ApiError


def run_async(fn, done):
    """Run fn() in a thread; call done(result, error) on the GTK main loop."""
    def work():
        try:
            res, err = fn(), None
        except ApiError as e:
            res, err = None, str(e)
        except Exception as e:  # noqa: BLE001
            res, err = None, f"{type(e).__name__}: {e}"
        GLib.idle_add(lambda: done(res, err) and False)
    threading.Thread(target=work, daemon=True).start()
