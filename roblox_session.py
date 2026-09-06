"""
roblox_session.py
==================
Best-effort, NON-INVASIVE extraction of session info: which game is
running, player count, and region.

Method (the same technique legitimate, widely-used tools such as
Bloxstrap's Discord Rich Presence feature use):

  1. Roblox itself writes a plaintext log file to
     %LOCALAPPDATA%\\Roblox\\logs\\*.log during normal operation. We only
     READ this file. We never write to it and never touch the Roblox
     process's memory.
  2. When the log reveals a placeId, we ask Roblox's own PUBLIC web API
     (the same one roblox.com's website itself calls) for that place's
     name and player counts.
  3. When the log reveals the IP address Roblox connected to for the
     game server, we do a public IP geolocation lookup to approximate
     the server's region.

Roblox's log format can differ across client versions. If a value
can't be found, the corresponding field is left as None ("Unknown" in
the UI) -- it is NEVER guessed, randomized, or hard-coded.
"""

import os
import re
import glob
import time

try:
    import requests
except ImportError:
    requests = None


def _log_dir():
    return os.path.expandvars(r"%LOCALAPPDATA%\Roblox\logs")


# These patterns cover common Roblox log formats. If your client's
# format differs, matching simply fails and the field shows "Unknown".
PLACE_ID_PATTERNS = [
    re.compile(r"placeId[\"'=: ]+(\d+)", re.IGNORECASE),
    re.compile(r"universeid[\"'=: ]+(\d+)", re.IGNORECASE),
]
JOIN_IP_PATTERN = re.compile(r"Connect:.*?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})")


def find_latest_log_file():
    """Return the most recently modified Roblox log file, or None."""
    log_dir = _log_dir()
    if not os.path.isdir(log_dir):
        return None
    logs = glob.glob(os.path.join(log_dir, "*.log"))
    if not logs:
        return None
    return max(logs, key=os.path.getmtime)


def read_recent_log_tail(path, max_bytes=400_000):
    """Read just the end of the log (it grows large over a session)."""
    try:
        size = os.path.getsize(path)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
            return f.read()
    except OSError:
        return ""


def extract_place_id(log_text):
    for pattern in PLACE_ID_PATTERNS:
        matches = pattern.findall(log_text)
        if matches:
            return matches[-1]  # most recent occurrence wins
    return None


def extract_join_ip(log_text):
    matches = JOIN_IP_PATTERN.findall(log_text)
    return matches[-1] if matches else None


def get_universe_id(place_id):
    if requests is None:
        return None
    try:
        r = requests.get(
            f"https://apis.roblox.com/universes/v1/places/{place_id}/universe",
            timeout=3,
        )
        if r.ok:
            return r.json().get("universeId")
    except Exception:
        pass
    return None


def get_game_info(universe_id):
    """Returns (name, playing, max_players) from Roblox's public API."""
    if requests is None or universe_id is None:
        return None, None, None
    try:
        r = requests.get(
            f"https://games.roblox.com/v1/games?universeIds={universe_id}",
            timeout=3,
        )
        if r.ok:
            data = r.json().get("data") or []
            if data:
                g = data[0]
                return g.get("name"), g.get("playing"), g.get("maxPlayers")
    except Exception:
        pass
    return None, None, None


def get_region_for_ip(ip):
    """Best-effort public geolocation lookup. Returns a display string or None."""
    if requests is None or ip is None:
        return None
    try:
        r = requests.get(
            f"http://ip-api.com/json/{ip}?fields=status,country,regionName,city",
            timeout=3,
        )
        if r.ok:
            data = r.json()
            if data.get("status") == "success":
                parts = [p for p in (data.get("city"), data.get("regionName"), data.get("country")) if p]
                return ", ".join(parts) if parts else None
    except Exception:
        pass
    return None


class SessionInfoLookup:
    """
    Periodically refreshes best-effort session info. These are network
    calls, so this deliberately does NOT run on every poll tick.
    All fields default to None ("Unknown" in the UI) until real data is
    found.
    """

    def __init__(self, refresh_interval_seconds=8):
        self.refresh_interval = refresh_interval_seconds
        self._last_refresh = 0
        self.game_name = None
        self.players_current = None
        self.players_max = None
        self.region = None

    def maybe_refresh(self, force=False):
        now = time.time()
        if not force and (now - self._last_refresh) < self.refresh_interval:
            return
        self._last_refresh = now

        log_path = find_latest_log_file()
        if not log_path:
            return
        text = read_recent_log_tail(log_path)

        place_id = extract_place_id(text)
        if place_id:
            universe_id = get_universe_id(place_id)
            name, playing, max_players = get_game_info(universe_id)
            if name:
                self.game_name = name
            if playing is not None:
                self.players_current = playing
            if max_players is not None:
                self.players_max = max_players

        ip = extract_join_ip(text)
        if ip:
            region = get_region_for_ip(ip)
            if region:
                self.region = region

    def reset(self):
        """Called when Roblox disconnects, so stale info isn't shown."""
        self.game_name = None
        self.players_current = None
        self.players_max = None
        self.region = None
