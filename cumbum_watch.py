"""
Cumbum Watch
============
A read-only console monitor for Roblox processes on Windows.

What this does:
  - Uses psutil (which wraps the real Windows process APIs) to enumerate
    running processes and find Roblox.
  - Displays the ACTUAL process ID (PID) that Windows assigned to that
    process. Nothing here is hard-coded, randomized, or simulated.
  - Continuously re-verifies that the monitored PID still belongs to a
    live process before reporting it as connected.
  - Detects the exact moment the monitored process exits, logs it, and
    goes back to waiting for Roblox to launch again (picking up whatever
    new PID Windows assigns).

What this does NOT do:
  - It never injects into, writes to, or otherwise interferes with the
    Roblox process. It only reads process metadata (pid, name, create
    time) via psutil / the Windows process APIs. It is observation-only.

Requirements:
  - Windows (this relies on Windows process enumeration; psutil provides
    a cross-platform wrapper around it).
  - Python 3.8+
  - pip install psutil colorama

Run:
  python cumbum_watch.py
"""

import os
import sys
import time
from datetime import datetime

try:
    import psutil
except ImportError:
    sys.exit(
        "Missing dependency 'psutil'.\n"
        "Install it with:  pip install psutil colorama"
    )

try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init()
    C_GREEN = Fore.GREEN + Style.BRIGHT
    C_RED = Fore.RED + Style.BRIGHT
    C_YELLOW = Fore.YELLOW
    C_CYAN = Fore.CYAN + Style.BRIGHT
    C_DIM = Style.DIM
    C_RESET = Style.RESET_ALL
except ImportError:
    # Fall back to no color if colorama isn't installed.
    C_GREEN = C_RED = C_YELLOW = C_CYAN = C_DIM = C_RESET = ""

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

# Real Windows executable names we treat as "Roblox". Order = preference
# when more than one kind is running at once (player takes priority).
ROBLOX_PROCESS_NAMES = [
    "RobloxPlayerBeta.exe",
    "RobloxStudioBeta.exe",
]

POLL_INTERVAL_SECONDS = 1.0
MAX_LOG_LINES = 14
APP_TITLE = "CUMBUM WATCH"


def now_stamp():
    """Real wall-clock timestamp, formatted like [13:45:17]."""
    return datetime.now().strftime("%H:%M:%S")


class RobloxMonitor:
    """
    Tracks exactly one live Roblox process at a time, using only data
    that Windows itself reports through psutil.
    """

    def __init__(self):
        self.pid = None          # the real PID currently being monitored, or None
        self.proc_name = None    # the exe name of that PID, or None
        self.create_time = None  # that process's real start time, used to
                                  # detect PID re-use if the OS recycles a PID
        self.log_lines = []      # rolling event log (timestamp, text)

    # ---- logging -------------------------------------------------------

    def log(self, text):
        self.log_lines.append((now_stamp(), text))
        if len(self.log_lines) > MAX_LOG_LINES:
            self.log_lines.pop(0)

    # ---- core detection logic -------------------------------------------

    def find_roblox_candidates(self):
        """
        Scan live Windows processes for anything matching our target
        Roblox executable names. Returns a list of psutil.Process objects,
        each backed by a real PID Windows has assigned.
        """
        candidates = []
        for proc in psutil.process_iter(["pid", "name", "create_time"]):
            try:
                name = proc.info["name"]
                if name and name in ROBLOX_PROCESS_NAMES:
                    candidates.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                # Process vanished mid-scan, or we can't read it — skip it.
                continue
        return candidates

    def pick_process_to_monitor(self, candidates):
        """
        If multiple Roblox-related processes are running, deterministically
        choose ONE to monitor: prefer RobloxPlayerBeta.exe over
        RobloxStudioBeta.exe, and among ties, the one that started earliest
        (lowest create_time). This is documented so it's always clear which
        process's PID is being shown.
        """
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
        """
        Verify — right now, against live Windows process state — that the
        PID we're monitoring still exists AND is still the same process
        (not a different process that got the same PID reassigned to it
        after the original exited).
        """
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
        """
        One monitoring tick. Either:
          - confirm the current PID is still valid, or detect its exit, or
          - look for a new Roblox process to start monitoring.
        """
        if self.pid is not None:
            if self.currently_monitored_is_alive():
                return  # still connected, nothing changed
            # The exact process we were watching is gone.
            self.log(f"{self.proc_name} (PID {self.pid}) exited")
            self.log("DISCONNECTED")
            self.log("Waiting for Roblox...")
            self.pid = None
            self.proc_name = None
            self.create_time = None
            return

        # Not currently monitoring anything — look for Roblox.
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
        if len(candidates) > 1:
            self.log(f"(monitoring this process only; {len(candidates) - 1} other "
                      f"Roblox process(es) ignored)")

    # ---- rendering -------------------------------------------------------

    def render(self):
        clear_screen()
        print(f"{C_CYAN}{APP_TITLE}{C_RESET}")
        print(f"{C_DIM}{'-' * len(APP_TITLE)}{C_RESET}\n")

        if self.pid is not None and self.currently_monitored_is_alive():
            print(f"{C_GREEN}\u25cf CONNECTED{C_RESET}")
            print(f"{self.proc_name}")
            print(f"PID: {self.pid}")
        else:
            print(f"{C_RED}\u25cf DISCONNECTED{C_RESET}")
            print("Waiting for Roblox...")

        print()
        print(f"{C_YELLOW}Event Log{C_RESET}")
        print(f"{C_DIM}{'-' * 9}{C_RESET}")
        if not self.log_lines:
            print(f"{C_DIM}(no events yet){C_RESET}")
        else:
            for stamp, text in self.log_lines:
                print(f"[{stamp}] {text}")

        print(f"\n{C_DIM}Read-only monitor. Press Ctrl+C to exit.{C_RESET}")


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def main():
    monitor = RobloxMonitor()
    try:
        while True:
            monitor.update()
            monitor.render()
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nExiting Cumbum Watch.")


if __name__ == "__main__":
    main()
