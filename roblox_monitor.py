"""
roblox_monitor.py
==================
Real, live Roblox process detection using Windows process APIs (via
psutil). This is unchanged in spirit from the original Cumbum Watch:
every PID shown anywhere in the app comes directly from here, and only
from here. Nothing here fabricates, randomizes, or hard-codes a PID.
"""

import psutil

ROBLOX_PROCESS_NAMES = [
    "RobloxPlayerBeta.exe",
    "RobloxStudioBeta.exe",
]


class RobloxMonitor:
    """Tracks exactly one live Roblox process at a time."""

    def __init__(self):
        self.pid = None
        self.proc_name = None
        self.create_time = None
        self.log_lines = []

    def log(self, text, stamp=None):
        import datetime
        stamp = stamp or datetime.datetime.now().strftime("%H:%M:%S")
        self.log_lines.append((stamp, text))
        if len(self.log_lines) > 50:
            self.log_lines.pop(0)
        print(f"[{stamp}] {text}")

    def find_roblox_candidates(self):
        candidates = []
        for proc in psutil.process_iter(["pid", "name", "create_time"]):
            try:
                name = proc.info["name"]
                if name and name in ROBLOX_PROCESS_NAMES:
                    candidates.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return candidates

    def pick_process_to_monitor(self, candidates):
        def sort_key(p):
            try:
                name_priority = ROBLOX_PROCESS_NAMES.index(p.info["name"])
                started_at = p.info["create_time"]
            except Exception:
                name_priority = len(ROBLOX_PROCESS_NAMES)
                started_at = float("inf")
            return (name_priority, started_at)

        return sorted(candidates, key=sort_key)[0]

    def currently_monitored_is_alive(self):
        if self.pid is None:
            return False
        if not psutil.pid_exists(self.pid):
            return False
        try:
            p = psutil.Process(self.pid)
            if p.name() != self.proc_name:
                return False
            if self.create_time is not None and p.create_time() != self.create_time:
                return False
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def update(self):
        if self.pid is not None:
            if self.currently_monitored_is_alive():
                return
            self.log(f"{self.proc_name} (PID {self.pid}) exited")
            self.log("DISCONNECTED")
            self.log("Waiting for Roblox...")
            self.pid = None
            self.proc_name = None
            self.create_time = None
            return

        candidates = self.find_roblox_candidates()
        if not candidates:
            return

        if len(candidates) > 1:
            names = ", ".join(f"{c.info['name']}(PID {c.info['pid']})" for c in candidates)
            self.log(f"Found {len(candidates)} Roblox processes: {names}")

        chosen = self.pick_process_to_monitor(candidates)
        try:
            self.pid = chosen.info["pid"]
            self.proc_name = chosen.info["name"]
            self.create_time = chosen.info["create_time"]
        except Exception:
            return

        self.log("Roblox detected")
        self.log(f"Connected to {self.proc_name}")
        self.log(f"PID: {self.pid}")
