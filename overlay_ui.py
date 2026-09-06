"""
overlay_ui.py
=============
A small, dark, magenta-accented floating panel -- styled after the
reference screenshot's aesthetic (colors, card layout, typography) --
but this is a PURELY INFORMATIONAL HUD:

  - No sliders, toggles, dropdowns, or color pickers that affect
    anything -- just four read-only info cards.
  - No interaction with the Roblox process's memory, rendering, or
    input at all. It's a separate window drawn on top of the screen.

Visual reference used: dark background, magenta/pink accent color,
rounded card sections, small caps section labels. None of the
cheat/ESP/exploit functionality from that reference is reproduced here.
"""

import tkinter as tk

BG = "#14141c"
PANEL = "#1c1c26"
ACCENT = "#ff19cf"
TEXT_MAIN = "#f2f2f7"
TEXT_DIM = "#8a8a99"
GREEN = "#35d17a"
RED = "#ff4d5e"

ANIM_STEPS = 14
ANIM_INTERVAL_MS = 12
PANEL_W, PANEL_H = 300, 260


class OverlayWindow:
    def __init__(self, root):
        self.root = root
        self.visible = False
        self._anim_job = None
        self._start_alpha = 0.0
        self._start_y = 0

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.0)
        self.win.configure(bg=BG)

        sw = self.win.winfo_screenwidth()
        self.target_x = sw - PANEL_W - 24
        self.target_y = 24
        self.closed_y = self.target_y - 20  # slides down slightly on open
        self.win.geometry(f"{PANEL_W}x{PANEL_H}+{self.target_x}+{self.closed_y}")

        self._build_widgets()
        self.win.withdraw()

    def _build_widgets(self):
        outer = tk.Frame(self.win, bg=BG, highlightbackground=ACCENT,
                          highlightthickness=1)
        outer.place(x=0, y=0, width=PANEL_W, height=PANEL_H)

        tk.Label(outer, text="CUMBUM WATCH", bg=BG, fg=ACCENT,
                  font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=14, pady=(12, 2))

        self.status_label = tk.Label(outer, text="\u25cf DISCONNECTED",
                                      bg=BG, fg=RED, font=("Segoe UI", 9, "bold"))
        self.status_label.pack(anchor="w", padx=14, pady=(0, 10))

        self.section_labels = {}
        for key, title_text in [
            ("game", "GAME"),
            ("players", "PLAYERS"),
            ("region", "REGION"),
            ("connection", "CONNECTION"),
        ]:
            card = tk.Frame(outer, bg=PANEL)
            card.pack(fill="x", padx=12, pady=4)
            tk.Label(card, text=title_text, bg=PANEL, fg=TEXT_DIM,
                      font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=10, pady=(6, 0))
            value_label = tk.Label(card, text="Unknown", bg=PANEL, fg=TEXT_MAIN,
                                     font=("Segoe UI", 10), justify="left")
            value_label.pack(anchor="w", padx=10, pady=(0, 6))
            self.section_labels[key] = value_label

    # ---- content -----------------------------------------------------

    def update_content(self, connected, proc_name, pid, game_name,
                        players_current, players_max, region):
        if connected:
            self.status_label.config(text="\u25cf CONNECTED", fg=GREEN)
        else:
            self.status_label.config(text="\u25cf DISCONNECTED", fg=RED)

        self.section_labels["game"].config(text=game_name or "Unknown")

        if players_current is not None and players_max is not None:
            self.section_labels["players"].config(text=f"{players_current} / {players_max}")
        else:
            self.section_labels["players"].config(text="Unknown")

        self.section_labels["region"].config(text=region or "Unknown")

        if connected and pid is not None:
            self.section_labels["connection"].config(text=f"{proc_name}\nPID: {pid}")
        else:
            self.section_labels["connection"].config(text="Not connected")

    # ---- show / hide with animation -----------------------------------

    def toggle(self):
        if self.visible:
            self.animate_out()
        else:
            self.animate_in()

    def animate_in(self):
        self.visible = True
        self.win.deiconify()
        self._animate(target_alpha=0.96, target_y=self.target_y)

    def animate_out(self):
        self.visible = False
        self._animate(target_alpha=0.0, target_y=self.closed_y, on_done=self.win.withdraw)

    def force_hide_immediately(self):
        """Used when Roblox disconnects -- snap closed, no animation needed."""
        if self._anim_job:
            self.win.after_cancel(self._anim_job)
            self._anim_job = None
        self.visible = False
        self.win.attributes("-alpha", 0.0)
        self.win.withdraw()

    def _animate(self, target_alpha, target_y, on_done=None, step=0):
        if step == 0:
            self._start_alpha = self.win.attributes("-alpha")
            self._start_y = self.win.winfo_y()

        progress = step / ANIM_STEPS
        eased = 1 - (1 - progress) ** 3  # ease-out cubic

        alpha = self._start_alpha + (target_alpha - self._start_alpha) * eased
        y = int(self._start_y + (target_y - self._start_y) * eased)

        self.win.attributes("-alpha", max(0.0, min(1.0, alpha)))
        x = self.win.winfo_x()
        self.win.geometry(f"+{x}+{y}")

        if step < ANIM_STEPS:
            self._anim_job = self.win.after(
                ANIM_INTERVAL_MS, self._animate, target_alpha, target_y, on_done, step + 1
            )
        else:
            self._anim_job = None
            if on_done:
                on_done()
