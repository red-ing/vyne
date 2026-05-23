# -*- coding: utf-8 -*-
# ============================================================
# VYNE+ visualizer.py  —  brez librosa, samo numpy + ffmpeg
# ============================================================

import os
import json
import subprocess
import numpy as np

CACHE_DIR = "/home/pi/vyne/cache/"
N_BARS    = 16
HOP_SEC   = 0.5
SR        = 11025

_progress = {}   # mp3_path -> 0.0..1.0


def _cache_path(mp3_path):
    name = os.path.basename(mp3_path).replace(".mp3", "") + "_viz.json"
    return os.path.join(CACHE_DIR, name)


def get_progress(mp3_path):
    """Vrne progress precompute (0.0-1.0). 1.0 = gotovo."""
    if os.path.exists(_cache_path(mp3_path)):
        return 1.0
    return _progress.get(mp3_path, 0.0)


def precompute(mp3_path):
    cache = _cache_path(mp3_path)
    os.makedirs(CACHE_DIR, exist_ok=True)

    if os.path.exists(cache):
        _progress[mp3_path] = 1.0
        return True

    _progress[mp3_path] = 0.0

    try:
        cmd = [
            "ffmpeg", "-i", mp3_path,
            "-ac", "1", "-ar", str(SR),
            "-f", "s16le", "-"
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=120)
        if len(result.stdout) == 0:
            return False

        samples = np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32)
        samples /= 32768.0

        hop        = int(SR * HOP_SEC)
        n_fft      = 512
        freqs      = np.fft.rfftfreq(n_fft, d=1.0/SR)
        band_edges = np.logspace(np.log10(20), np.log10(8000), N_BARS + 1)
        window_fn  = np.hanning(n_fft)
        frames     = []

        total_frames = max(1, (len(samples) - n_fft) // hop)
        i = 0
        frame_idx = 0

        while i + n_fft <= len(samples):
            spectrum = np.abs(np.fft.rfft(samples[i:i + n_fft] * window_fn))
            bars = []
            for b in range(N_BARS):
                mask = (freqs >= band_edges[b]) & (freqs < band_edges[b + 1])
                bars.append(float(np.sqrt(np.mean(spectrum[mask] ** 2))) if mask.any() else 0.0)
            frames.append(bars)
            i += hop
            frame_idx += 1
            _progress[mp3_path] = min(0.99, frame_idx / total_frames)

        if not frames:
            return False

        all_vals = [v for f in frames for v in f]
        max_val  = max(all_vals) if all_vals else 1.0
        if max_val > 0:
            frames = [[v / max_val for v in f] for f in frames]

        duration = len(samples) / SR

        with open(cache, "w") as fp:
            json.dump({"hop_sec": HOP_SEC, "duration": duration, "frames": frames}, fp)

        _progress[mp3_path] = 1.0
        return True

    except Exception as e:
        print(f"[visualizer] precompute error: {e}")
        _progress[mp3_path] = 1.0
        return False


def get_bars(mp3_path, elapsed_sec):
    cache = _cache_path(mp3_path)
    if not os.path.exists(cache):
        return None
    try:
        with open(cache, "r") as fp:
            data = json.load(fp)
        frames   = data["frames"]
        hop_sec  = data["hop_sec"]
        duration = data["duration"]
        pos = elapsed_sec % duration if duration > 0 else 0
        idx = int(pos / hop_sec)
        idx = max(0, min(idx, len(frames) - 1))
        return frames[idx]
    except Exception as e:
        print(f"[visualizer] get_bars error: {e}")
        return None
