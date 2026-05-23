# -*- coding: utf-8 -*-
import os
import json
import time

STATE_FILE     = "/home/pi/vyne/state.json"
CONFIG_FILE    = "/home/pi/vyne/config.json"
LOG_FILE       = "/home/pi/vyne/logs/events.log"
HEARTBEAT_FILE = "/home/pi/vyne/logs/heartbeat"

# Koliko sekund brez heartbeata šteje za izgubo elektrike
POWER_LOST_THRESHOLD = 90


def _log(msg, ts=None):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    if ts is None:
        ts = time.strftime("[%Y-%m-%d %H:%M:%S]")
    with open(LOG_FILE, "a") as f:
        f.write(f"{ts} {msg}\n")


def _write_heartbeat():
    os.makedirs(os.path.dirname(HEARTBEAT_FILE), exist_ok=True)
    with open(HEARTBEAT_FILE, "w") as f:
        f.write(str(time.time()))


def _read_heartbeat():
    try:
        with open(HEARTBEAT_FILE, "r") as f:
            return float(f.read().strip())
    except Exception:
        return None


def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return None


def _save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def new_process(mp3, artist, track, hours):
    state = {
        "active":     True,
        "mp3":        mp3,
        "artist":     artist,
        "track":      track,
        "hours":      hours,
        "start_time": time.time(),
        "last_seen":  time.time(),
    }
    _save_state(state)
    _log(f"PROCESS STARTED: {artist} - {track} ({hours}h)")


def stop_process():
    state = load_state()
    if state:
        state["active"] = False
        _save_state(state)
        _log("PROCESS STOPPED")


def log_interruption():
    last_alive = _read_heartbeat()
    now = time.time()
    if last_alive and (now - last_alive) > POWER_LOST_THRESHOLD:
        lost_ts     = time.strftime("[%Y-%m-%d %H:%M:%S]", time.localtime(last_alive))
        restored_ts = time.strftime("[%Y-%m-%d %H:%M:%S]", time.localtime(now))
        _log("POWER LOST", ts=lost_ts)
        _log("POWER RESTORED", ts=restored_ts)
    _write_heartbeat()


def time_remaining(state):
    if not state or not state.get("active"):
        return None
    start_time    = state.get("start_time", time.time())
    total_seconds = state.get("hours", 72) * 3600
    remaining     = max(0, total_seconds - (time.time() - start_time))
    if remaining <= 0:
        return None
    h = int(remaining // 3600)
    m = int((remaining % 3600) // 60)
    s = int(remaining % 60)
    return {"hours": h, "minutes": m, "seconds": s}


def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def update_last_seen():
    _write_heartbeat()
    state = load_state()
    if state and state.get("active"):
        state["last_seen"] = time.time()
        _save_state(state)
