# ============================================================
# VYNE+ server.py - Remote MP3 upload & control server
# ============================================================

import os
import csv
import io
import json
import socket
import threading
from datetime import datetime
from flask import Flask, request, redirect, render_template_string, Response
from werkzeug.utils import secure_filename
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
from state import load_state, new_process, stop_process, time_remaining
from visualizer import precompute

# ============================================================
# SETTINGS
# ============================================================

MUSIC_DIR   = "/home/pi/vyne/music/"
LOG_FILE    = "/home/pi/vyne/logs/events.log"
ALLOWED_EXT = {"mp3"}
USERNAME    = "admin"
PASSWORD    = "vyne2024"
STOP_PASS   = "VYNE+STOP+2024"

app = Flask(__name__)
app.secret_key = "vyne_secret_key"

# ============================================================
# HELPERS
# ============================================================

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def check_auth(req):
    auth = req.authorization
    return auth and auth.username == USERNAME and auth.password == PASSWORD

def require_auth():
    return ("Unauthorized", 401, {"WWW-Authenticate": 'Basic realm="VYNE+ Admin"'})

def get_mp3_info(filename):
    filepath = os.path.join(MUSIC_DIR, filename)
    try:
        tags    = ID3(filepath)
        audio   = MP3(filepath)
        artist  = str(tags.get('TPE1', 'Unknown'))
        title   = str(tags.get('TIT2', 'Unknown'))
        album   = str(tags.get('TALB', '-'))
        year    = str(tags.get('TDRC', '-'))
        dur     = int(audio.info.length)
        bitrate = int(audio.info.bitrate / 1000)
        mins    = dur // 60
        secs    = dur % 60
        size    = os.path.getsize(filepath)
        size_mb = round(size / 1024 / 1024, 1)
        return {
            "name": filename, "artist": artist, "title": title,
            "album": album, "year": str(year),
            "duration": f"{mins}:{secs:02d}",
            "bitrate": f"{bitrate} kbps", "size": f"{size_mb} MB"
        }
    except Exception:
        return {
            "name": filename, "artist": "Unknown", "title": "Unknown",
            "album": "-", "year": "-", "duration": "-", "bitrate": "-", "size": "-"
        }

def format_remaining(t):
    if not t:
        return "-"
    days = t['hours'] // 24
    hrs  = t['hours'] % 24
    return f"{days}d {hrs:02d}:{t['minutes']:02d}:{t['seconds']:02d}"

def format_interruptions(state):
    interruptions = state.get("interruptions", []) if state else []
    result = []
    for ts in interruptions:
        try:
            dt = datetime.fromisoformat(ts)
            result.append(dt.strftime("%Y-%m-%d %H:%M:%S"))
        except Exception:
            result.append(ts)
    return result

def get_log_lines():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
            return [l.strip() for l in reversed(lines[-50:])]
    return []

# ============================================================
# TEMPLATE
# ============================================================

TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>VYNE+ Admin</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;1,300;1,400&family=Inter:wght@300;400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg:         #f4ede0;
            --bg-1:       #ebe2d0;
            --bg-2:       #e3d8c1;
            --paper:      #faf5e9;
            --line:       rgba(38,30,16,0.12);
            --line-strong:rgba(38,30,16,0.28);
            --gold:       #b8924d;
            --gold-soft:  #c9a661;
            --gold-deep:  #8a6f33;
            --gold-bright:#d4ad5a;
            --green:      #1f3522;
            --green-soft: #2d4d31;
            --green-mute: rgba(31,53,34,0.65);
            --red:        #b53a2a;
            --red-soft:   #cf5949;
            --red-deep:   #7a2418;
            --ink:        #261e10;
            --ink-soft:   #4a3f2a;
            --ink-mute:   #7a6f5a;
            --serif:      'Cormorant Garamond', serif;
            --sans:       'Inter', sans-serif;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        html, body {
            background: var(--bg);
            color: var(--ink);
            font-family: var(--sans);
            font-weight: 300;
            -webkit-font-smoothing: antialiased;
        }

        body {
            background:
                radial-gradient(ellipse 50% 30% at 100% 100%, rgba(184,146,77,0.10), transparent 70%),
                radial-gradient(ellipse 60% 40% at 0% 10%, rgba(31,53,34,0.06), transparent 70%),
                var(--bg);
            min-height: 100vh;
            padding: 0 0 4rem;
        }

        /* ── GRID MOTIF ── */
        .grid-divider {
            width: 100%;
            height: 12px;
            background-repeat: repeat-x;
            background-position: center;
            background-size: 240px 12px;
            background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='240' height='12'><g fill='%23b8924d'><rect x='0' y='4' width='4' height='4'/><rect x='8' y='4' width='4' height='4'/><rect x='16' y='4' width='4' height='4'/><rect x='24' y='4' width='4' height='4'/><rect x='32' y='4' width='4' height='4'/><rect x='40' y='4' width='4' height='4'/><rect x='48' y='4' width='4' height='4'/><rect x='56' y='4' width='4' height='4'/><rect x='64' y='4' width='4' height='4'/><rect x='72' y='4' width='4' height='4'/><rect x='80' y='4' width='4' height='4'/><rect x='88' y='4' width='4' height='4'/><rect x='96' y='4' width='4' height='4'/><rect x='104' y='4' width='4' height='4'/><rect x='112' y='4' width='4' height='4'/><rect x='120' y='4' width='4' height='4'/></g></svg>");
            opacity: 0.7;
            margin: 2rem 0;
        }

        /* ── HEADER ── */
        .site-header {
            border-bottom: 1px solid var(--line);
            padding: 2rem 3rem 1.6rem;
            display: flex;
            align-items: baseline;
            gap: 1.2rem;
            flex-wrap: wrap;
        }

        .logo {
            font-family: var(--sans);
            font-weight: 200;
            font-size: 2.4rem;
            letter-spacing: 0.35em;
            color: var(--green);
            line-height: 1;
        }
        .logo sup {
            font-size: 1.4rem;
            color: var(--gold);
            font-weight: 300;
            letter-spacing: 0;
            vertical-align: super;
        }

        .header-sub {
            font-family: var(--serif);
            font-style: italic;
            font-size: 1rem;
            color: var(--gold-deep);
            letter-spacing: 0.05em;
        }

        .header-right {
            margin-left: auto;
            font-size: 0.65rem;
            letter-spacing: 0.2em;
            color: var(--ink-mute);
            display: flex;
            align-items: center;
            gap: 1.5rem;
        }

        .refresh-dot {
            width: 6px; height: 6px;
            border-radius: 50%;
            background: var(--gold);
            display: inline-block;
            margin-right: 6px;
            animation: pulse 2s ease-in-out infinite;
        }

        @keyframes pulse {
            0%,100% { opacity:1; } 50% { opacity:0.3; }
        }

        /* ── LAYOUT ── */
        .page-body {
            max-width: 960px;
            margin: 0 auto;
            padding: 2.5rem 3rem 0;
        }

        /* ── MESSAGES ── */
        .msg {
            padding: 0.9rem 1.2rem;
            border-radius: 3px;
            margin-bottom: 1.6rem;
            font-size: 0.75rem;
            letter-spacing: 0.12em;
            border-left: 3px solid;
        }
        .msg.ok  { background: rgba(31,53,34,0.06); border-color: var(--green); color: var(--green); }
        .msg.err { background: rgba(181,58,42,0.06); border-color: var(--red);  color: var(--red-deep); }

        /* ── CARD ── */
        .card {
            background: var(--paper);
            border: 1px solid var(--line);
            border-radius: 4px;
            padding: 1.8rem 2rem;
            margin-bottom: 1.6rem;
        }

        .card-label {
            font-size: 0.6rem;
            letter-spacing: 0.25em;
            color: var(--ink-mute);
            text-transform: uppercase;
            margin-bottom: 1.4rem;
            display: flex;
            align-items: center;
            gap: 0.8rem;
        }
        .card-label::after {
            content: '';
            flex: 1;
            height: 1px;
            background: var(--line);
        }

        /* ── STATUS GRID ── */
        .status-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 1.2rem;
            margin-bottom: 1.4rem;
        }

        .status-item .s-label {
            font-size: 0.58rem;
            letter-spacing: 0.2em;
            color: var(--ink-mute);
            margin-bottom: 5px;
            text-transform: uppercase;
        }
        .status-item .s-value {
            font-size: 1rem;
            font-weight: 400;
            letter-spacing: 0.03em;
        }

        .status-active  { color: var(--green); }
        .status-idle    { color: var(--ink-mute); }
        .status-gold    { color: var(--gold-deep); }
        .status-red     { color: var(--red); }

        /* ── COUNTDOWN ── */
        .countdown-wrap {
            margin: 1.2rem 0;
        }
        .countdown-label {
            font-size: 0.58rem;
            letter-spacing: 0.2em;
            color: var(--ink-mute);
            text-transform: uppercase;
            margin-bottom: 6px;
        }
        #countdown {
            font-family: var(--sans);
            font-size: 2rem;
            font-weight: 200;
            letter-spacing: 0.12em;
            color: var(--green);
        }

        hr.rule {
            border: none;
            border-top: 1px solid var(--line);
            margin: 1.4rem 0;
        }

        /* ── FORMS ── */
        .form-row {
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
            align-items: flex-end;
        }
        .form-group {
            display: flex;
            flex-direction: column;
            gap: 0.4rem;
            flex: 1;
            min-width: 140px;
        }
        .form-group label {
            font-size: 0.58rem;
            letter-spacing: 0.2em;
            color: var(--ink-mute);
            text-transform: uppercase;
        }

        select, input[type=text], input[type=password] {
            background: var(--bg);
            border: 1px solid var(--line-strong);
            color: var(--ink);
            padding: 0.65rem 0.8rem;
            border-radius: 3px;
            font-size: 0.82rem;
            font-family: var(--sans);
            font-weight: 300;
            width: 100%;
            appearance: none;
            -webkit-appearance: none;
            transition: border-color 0.15s;
        }
        select { background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6'><path d='M0 0l5 6 5-6z' fill='%237a6f5a'/></svg>"); background-repeat: no-repeat; background-position: right 0.8rem center; padding-right: 2rem; }
        select:focus, input:focus { outline: none; border-color: var(--gold); }

        /* ── BUTTONS ── */
        .btn {
            border: none;
            padding: 0.7rem 1.6rem;
            border-radius: 3px;
            cursor: pointer;
            font-size: 0.62rem;
            letter-spacing: 0.2em;
            text-transform: uppercase;
            font-family: var(--sans);
            font-weight: 400;
            white-space: nowrap;
            text-decoration: none;
            display: inline-block;
            transition: background 0.15s, color 0.15s;
        }
        .btn-green  { background: var(--green); color: var(--paper); }
        .btn-green:hover { background: var(--green-soft); }
        .btn-red    { background: transparent; color: var(--red-deep); border: 1px solid rgba(181,58,42,0.35); }
        .btn-red:hover { background: rgba(181,58,42,0.07); }
        .btn-ghost  { background: transparent; color: var(--ink-soft); border: 1px solid var(--line-strong); }
        .btn-ghost:hover { border-color: var(--gold); color: var(--ink); }
        .btn-row    { display: flex; gap: 0.8rem; flex-wrap: wrap; align-items: center; }

        /* ── UPLOAD ── */
        .upload-area {
            border: 1px dashed var(--line-strong);
            border-radius: 3px;
            padding: 1.8rem;
            text-align: center;
            margin-bottom: 1rem;
            transition: border-color 0.15s;
        }
        .upload-area:hover { border-color: var(--gold); }
        .upload-area input[type=file] { display: none; }
        .upload-area label {
            cursor: pointer;
            color: var(--gold-deep);
            font-size: 0.72rem;
            letter-spacing: 0.2em;
            text-transform: uppercase;
            display: block;
        }
        #filename { color: var(--ink-mute); font-size: 0.72rem; margin-top: 0.5rem; letter-spacing: 0.05em; }

        /* ── FILE LIST ── */
        .file-list { list-style: none; }
        .file-item { border-bottom: 1px solid var(--line); padding: 1.1rem 0; }
        .file-item:last-child { border-bottom: none; }
        .file-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem; }
        .file-artist { color: var(--gold-deep); font-family: var(--serif); font-style: italic; font-size: 1rem; margin-bottom: 2px; }
        .file-title  { color: var(--ink); font-size: 0.85rem; margin-bottom: 3px; }
        .file-name   { font-size: 0.68rem; color: var(--ink-mute); letter-spacing: 0.05em; }
        .file-meta   { display: flex; gap: 0.5rem; flex-wrap: wrap; }
        .file-meta span {
            font-size: 0.65rem;
            color: var(--ink-mute);
            background: var(--bg-1);
            padding: 0.2rem 0.55rem;
            border-radius: 2px;
            letter-spacing: 0.05em;
        }

        .delete-btn {
            background: none;
            border: 1px solid var(--line-strong);
            color: var(--ink-mute);
            padding: 0.3rem 0.75rem;
            border-radius: 3px;
            cursor: pointer;
            font-size: 0.62rem;
            letter-spacing: 0.12em;
            font-family: var(--sans);
            transition: border-color 0.15s, color 0.15s;
        }
        .delete-btn:hover { border-color: var(--red); color: var(--red); }

        /* ── EMPTY / LOG ── */
        .empty {
            color: var(--ink-mute);
            font-size: 0.75rem;
            letter-spacing: 0.15em;
            text-align: center;
            padding: 2.5rem;
            font-style: italic;
            font-family: var(--serif);
        }

        .log-list { list-style: none; max-height: 260px; overflow-y: auto; }
        .log-list li {
            font-size: 0.68rem;
            color: var(--ink-mute);
            padding: 0.28rem 0;
            border-bottom: 1px solid var(--line);
            font-family: 'Courier New', monospace;
        }
        .log-list li:last-child { border-bottom: none; }
        .log-count { font-size: 0.6rem; color: var(--ink-mute); letter-spacing: 0.15em; margin-bottom: 0.8rem; }

        /* ── RESPONSIVE ── */
        @media (max-width: 600px) {
            .site-header { padding: 1.5rem 1.5rem 1.2rem; }
            .page-body   { padding: 1.5rem 1.5rem 0; }
            .card        { padding: 1.4rem 1.2rem; }
        }
    </style>
    <script>
        setTimeout(function() { location.reload(); }, 30000);
        var totalSeconds = {{ total_seconds }};
        function updateCountdown() {
            if (totalSeconds <= 0) {
                var el = document.getElementById('countdown');
                if (el) el.textContent = 'COMPLETE';
                return;
            }
            var days = Math.floor(totalSeconds / 86400);
            var hrs  = Math.floor((totalSeconds % 86400) / 3600);
            var mins = Math.floor((totalSeconds % 3600) / 60);
            var secs = totalSeconds % 60;
            var el = document.getElementById('countdown');
            if (el) el.textContent =
                days + 'd ' +
                String(hrs).padStart(2,'0') + ':' +
                String(mins).padStart(2,'0') + ':' +
                String(secs).padStart(2,'0');
            totalSeconds--;
        }
        if (totalSeconds > 0) { updateCountdown(); setInterval(updateCountdown, 1000); }
        function toggleCustomHours(val) {
            var g = document.getElementById('custom-hours-group');
            var inp = document.getElementById('custom-hours-input');
            if (val === '0') {
                g.style.display = '';
                inp.required = true;
            } else {
                g.style.display = 'none';
                inp.required = false;
                inp.value = '';
            }
        }
    </script>
</head>
<body>

    <!-- HEADER -->
    <header class="site-header">
        <div class="logo">VYNE<sup>+</sup></div>
        <div class="header-sub" style="color:var(--ink-mute);">Device Control Panel · <span style="color:var(--gold-deep);">{{ hostname }}</span></div>
        <div class="header-right">
            <span><span class="refresh-dot"></span>AUTO-REFRESH 30s</span>
        </div>
    </header>

    <div class="page-body">

        {% if message %}
        <div class="msg {{ 'ok' if success else 'err' }}">{{ message }}</div>
        {% endif %}

        <!-- STATUS & CONTROL -->
        <div class="card">
            <div class="card-label">Device Status &amp; Control</div>

            <div class="status-grid">
                <div class="status-item">
                    <div class="s-label">Status</div>
                    <div class="s-value {{ 'status-active' if state and state.get('active') else 'status-idle' }}">
                        {{ 'ACTIVE' if state and state.get('active') else 'IDLE' }}
                    </div>
                </div>
                {% if state and state.get('active') %}
                <div class="status-item">
                    <div class="s-label">Artist</div>
                    <div class="s-value status-gold">{{ state.get('artist', '—') }}</div>
                </div>
                <div class="status-item">
                    <div class="s-label">Track</div>
                    <div class="s-value">{{ state.get('track', '—') }}</div>
                </div>
                <div class="status-item">
                    <div class="s-label">Duration</div>
                    <div class="s-value status-idle">{{ state.get('weeks', '—') }} weeks</div>
                </div>
                <div class="status-item">
                    <div class="s-label">Interruptions</div>
                    <div class="s-value {{ 'status-red' if state.get('interruptions') else 'status-idle' }}">
                        {{ state.get('interruptions', []) | length }}
                    </div>
                </div>
                {% endif %}
            </div>

            {% if state and state.get('active') %}
            <div class="countdown-wrap">
                <div class="countdown-label">Remaining</div>
                <div id="countdown">{{ remaining }}</div>
            </div>
            {% endif %}

            <hr class="rule">

            {% if not state or not state.get('active') %}
            <form method="POST" action="/start">
                <div class="form-row">
                    <div class="form-group">
                        <label>Select MP3</label>
                        <select name="mp3">
                            {% for f in files %}
                            <option value="{{ f.name }}">{{ f.artist }} — {{ f.title }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Duration</label>
                        <select name="weeks" id="duration-select" onchange="toggleCustomHours(this.value)">
                            <option value="72">Classic · 72h</option>
                            <option value="672">Extended · 672h</option>
                            <option value="2016">Premium · 2016h</option>
                            <option value="0">Custom · up to 5000h</option>
                        </select>
                    </div>
                    <div class="form-group" id="custom-hours-group" style="display:none;">
                        <label>Custom hours (1–5000)</label>
                        <input type="number" name="custom_hours" id="custom-hours-input"
                               min="1" max="5000" placeholder="e.g. 360">
                    </div>
                    <button type="submit" class="btn btn-green">▶ Start aging</button>
                </div>
            </form>
            {% else %}
            <form method="POST" action="/stop">
                <div class="form-row">
                    <div class="form-group">
                        <label>Stop Password</label>
                        <input type="password" name="stop_password" placeholder="Enter stop password">
                    </div>
                    <button type="submit" class="btn btn-red">⏹ Stop</button>
                </div>
            </form>
            {% endif %}
        </div>

        <div class="grid-divider"></div>

        <!-- UPLOAD -->
        <div class="card">
            <div class="card-label">Upload MP3</div>
            <form method="POST" action="/upload" enctype="multipart/form-data">
                <div class="upload-area">
                    <input type="file" id="file" name="file" accept=".mp3"
                        onchange="document.getElementById('filename').textContent = this.files[0] ? this.files[0].name : 'No file selected'">
                    <label for="file">▲ Select MP3 file</label>
                    <div id="filename">No file selected</div>
                </div>
                <button type="submit" class="btn btn-green">Upload to device</button>
            </form>
        </div>

        <!-- FILE LIST -->
        <div class="card">
            <div class="card-label">MP3 Library &nbsp;({{ files | length }})</div>
            {% if files %}
            <ul class="file-list">
                {% for f in files %}
                <li class="file-item">
                    <div class="file-header">
                        <div>
                            <div class="file-artist">{{ f.artist }}</div>
                            <div class="file-title">{{ f.title }}</div>
                            <div class="file-name">{{ f.name }}</div>
                        </div>
                        <form method="POST" action="/delete">
                            <input type="hidden" name="filename" value="{{ f.name }}">
                            <button type="submit" class="delete-btn">Delete</button>
                        </form>
                    </div>
                    <div class="file-meta">
                        {% if f.album != '-' %}<span>{{ f.album }}</span>{% endif %}
                        {% if f.year != '-' %}<span>{{ f.year }}</span>{% endif %}
                        <span>{{ f.duration }}</span>
                        <span>{{ f.bitrate }}</span>
                        <span>{{ f.size }}</span>
                    </div>
                </li>
                {% endfor %}
            </ul>
            {% else %}
            <div class="empty">No MP3 files on device</div>
            {% endif %}
        </div>

        <div class="grid-divider"></div>

        <!-- EVENTS -->
        <div class="card">
            <div class="card-label">Event Log</div>
            <div class="btn-row" style="margin-bottom:1.4rem;">
                <a href="/export/csv" class="btn btn-ghost">↓ Process Report</a>
                <a href="/export/log" class="btn btn-ghost">↓ Event Log</a>
            </div>
            {% if log_lines %}
            <div class="log-count">Last 50 events</div>
            <ul class="log-list">
                {% for line in log_lines %}
                <li>{{ line }}</li>
                {% endfor %}
            </ul>
            {% else %}
            <div class="empty">No events recorded yet</div>
            {% endif %}
        </div>

    </div><!-- /page-body -->
</body>
</html>
"""

# ============================================================
# ROUTES
# ============================================================

@app.route("/")
def index():
    if not check_auth(request):
        return require_auth()

    state         = load_state()
    t             = time_remaining(state) if state else None
    remaining     = format_remaining(t)
    total_seconds = t['total_seconds'] if t else 0
    interruptions = format_interruptions(state)
    log_lines     = get_log_lines()
    hostname      = socket.gethostname()

    raw_files = sorted(os.listdir(MUSIC_DIR)) if os.path.exists(MUSIC_DIR) else []
    files     = [get_mp3_info(f) for f in raw_files if f.endswith(".mp3")]

    message = request.args.get("message", "")
    success = request.args.get("success", "true") == "true"

    return render_template_string(TEMPLATE,
        state=state, remaining=remaining, total_seconds=total_seconds,
        interruptions=interruptions, log_lines=log_lines,
        files=files, message=message, success=success, hostname=hostname)

@app.route("/export/csv")
def export_csv():
    if not check_auth(request):
        return require_auth()

    state  = load_state()
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["VYNE+ Process Report"])
    writer.writerow(["Generated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    writer.writerow([])
    writer.writerow(["PROCESS DETAILS"])
    writer.writerow(["Field", "Value"])

    if state:
        writer.writerow(["Status",       "Active" if state.get("active") else "Stopped"])
        writer.writerow(["Artist",        state.get("artist", "-")])
        writer.writerow(["Track",         state.get("track", "-")])
        writer.writerow(["MP3 File",      state.get("mp3", "-")])
        writer.writerow(["Duration",      f"{state.get('weeks', '-')} weeks"])
        writer.writerow(["Start",         state.get("start", "-")])
        writer.writerow(["End",           state.get("end", "-")])
        writer.writerow(["Interruptions", len(state.get("interruptions", []))])
        writer.writerow([])
        writer.writerow(["INTERRUPTION LOG"])
        writer.writerow(["Timestamp"])
        for ts in state.get("interruptions", []):
            try:
                dt = datetime.fromisoformat(ts)
                writer.writerow([dt.strftime("%Y-%m-%d %H:%M:%S")])
            except Exception:
                writer.writerow([ts])
    else:
        writer.writerow(["No active process"])

    output.seek(0)
    filename = f"vyne_process_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.route("/export/log")
def export_log():
    if not check_auth(request):
        return require_auth()

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            content = f.read()
    else:
        content = "No log file found."

    filename = f"vyne_event_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    return Response(
        content,
        mimetype="text/plain",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.route("/start", methods=["POST"])
def start():
    if not check_auth(request):
        return require_auth()

    mp3   = request.form.get("mp3", "")
    hours = int(request.form.get("weeks", 72))

    if hours == 0:
        try:
            hours = max(1, min(5000, int(request.form.get("custom_hours", 0))))
        except (ValueError, TypeError):
            hours = 0
        if hours == 0:
            return redirect("/?message=Enter a valid custom duration (1–5000h)&success=false")

    if not mp3:
        return redirect("/?message=No MP3 selected&success=false")

    filepath = os.path.join(MUSIC_DIR, mp3)
    if not os.path.exists(filepath):
        return redirect("/?message=MP3 file not found&success=false")

    try:
        tags   = ID3(filepath)
        artist = str(tags.get('TPE1', 'Unknown'))
        title  = str(tags.get('TIT2', 'Unknown'))
    except Exception:
        name   = mp3.replace(".mp3", "")
        parts  = name.split(" - ", 1)
        artist = parts[0] if len(parts) > 1 else "Unknown"
        title  = parts[1] if len(parts) > 1 else name

    new_process(mp3, artist, title, hours)
    return redirect(f"/?message=Process started: {artist} — {title}&success=true")

@app.route("/stop", methods=["POST"])
def stop():
    if not check_auth(request):
        return require_auth()

    password = request.form.get("stop_password", "")
    if password != STOP_PASS:
        return redirect("/?message=Wrong stop password&success=false")

    stop_process()
    return redirect("/?message=Process stopped&success=true")

@app.route("/upload", methods=["POST"])
def upload():
    if not check_auth(request):
        return require_auth()

    if "file" not in request.files:
        return redirect("/?message=No file selected&success=false")

    file = request.files["file"]
    if file.filename == "":
        return redirect("/?message=No file selected&success=false")

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        dest = os.path.join(MUSIC_DIR, filename)
        try:
            os.makedirs(MUSIC_DIR, exist_ok=True)
            file.save(dest)
        except Exception as e:
            return redirect(f"/?message=Upload failed: {e}&success=false")
        threading.Thread(target=precompute, args=(dest,), daemon=True).start()
        return redirect(f"/?message='{filename}' uploaded — analysing in background&success=true")

    return redirect("/?message=Invalid file type. Only MP3 allowed&success=false")

@app.route("/delete", methods=["POST"])
def delete():
    if not check_auth(request):
        return require_auth()

    filename = request.form.get("filename", "")
    filepath = os.path.join(MUSIC_DIR, secure_filename(filename))

    if os.path.exists(filepath):
        os.remove(filepath)
        return redirect(f"/?message='{filename}' deleted&success=true")

    return redirect("/?message=File not found&success=false")

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
