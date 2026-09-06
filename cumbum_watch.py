"""
Cumbum Watch
============
Background Roblox session monitor with a toggleable on-screen overlay.

- Real PID detection via Windows process APIs (see roblox_monitor.py).
  Never hard-coded, randomized, or faked.
- Best-effort session info (game name / players / region) comes only
  from reading Roblox's own log file and Roblox's public API (see
  roblox_session.py). No memory reading, no injection. Unavailable
  fields show "Unknown" rather than a guess.
- Overlay (Tkinter) toggles with Right Ctrl, animates open/closed, and
  auto-hides the instant Roblox isn't running (see overlay_ui.py).

This is a READ-ONLY monitoring tool. It never modifies, injects into,
or interferes with Roblox in any way.
"""

import tkinter as tk

from roblox_monitor import RobloxMonitor
from roblox_session import SessionInfoLookup
from overlay_ui import OverlayWindow

try:
    import keyboard
except ImportError:
    keyboard = None

POLL_MS = 1000


class CumbumWatchApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()  # no main window -- just the overlay

        self.monitor = RobloxMonitor()
        self.session = SessionInfoLookup()
        self.overlay = OverlayWindow(self.root)

        self.user_wants_open = False

        if keyboard is not None:
            keyboard.add_hotkey("right ctrl", self._on_hotkey)
        else:
            print("WARNING: 'keyboard' package not installed -- "
                  "Right Ctrl toggle will not work. Run: pip install keyboard")

        self.root.after(POLL_MS, self._tick)

    def _on_hotkey(self):
        self.user_wants_open = not self.user_wants_open
        self._sync_overlay_visibility()

    def _is_connected(self):
        return self.monitor.pid is not None and self.monitor.currently_monitored_is_alive()

    def _tick(self):
        self.monitor.update()
        connected = self._is_connected()

        if connected:
            self.session.maybe_refresh()
        else:
            self.session.reset()
            self.user_wants_open = False

        self.overlay.update_content(
            connected=connected,
            proc_name=self.monitor.proc_name,
            pid=self.monitor.pid,
            game_name=self.session.game_name,
            players_current=self.session.players_current,
            players_max=self.session.players_max,
            region=self.session.region,
        )

        self._sync_overlay_visibility(connected)
        self.root.after(POLL_MS, self._tick)

    def _sync_overlay_visibility(self, connected=None):
        if connected is None:
            connected = self._is_connected()

        if not connected:
            self.overlay.force_hide_immediately()
            return

        if self.user_wants_open and not self.overlay.visible:
            self.overlay.animate_in()
        elif not self.user_wants_open and self.overlay.visible:
            self.overlay.animate_out()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    CumbumWatchApp().run()
