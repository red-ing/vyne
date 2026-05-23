# -*- coding: utf-8 -*-
# ============================================================
# VYNE+ display_main.py — nov dizajn
# ============================================================

import os
os.environ['SDL_AUDIODRIVER'] = 'alsa'
os.environ['AUDIODEV']        = 'hw:0,0'

import time
import glob
import shutil
import subprocess
import threading
import pygame.mixer
import RPi.GPIO as GPIO
from PIL import Image, ImageDraw, ImageFont
from luma.lcd.device import ili9341
from luma.core.interface.serial import spi
from mutagen.id3 import ID3
from state import load_state, new_process, stop_process, log_interruption, \
                  time_remaining, load_config, update_last_seen
from visualizer import precompute, get_bars, get_progress

# ============================================================
# SETTINGS
# ============================================================

WIDTH     = 320
HEIGHT    = 240
MUSIC_DIR = "/home/pi/vyne/music/"
USB_ROOT  = "/media/pi/"
HOLD_TIME = 10.0
LOG_FILE  = "/home/pi/vyne/logs/events.log"

# Barve
BG      = (244, 237, 224)   # kremasto ozadje
VYNE_C  = (31,  53,  34)    # temno zelena za VYNE
PLUS_C  = (184, 146, 77)    # zlata za +
GOLD    = (184, 146, 77)    # zlata za accente
WINE    = (123, 45,  45)    # vinska za selected
LABEL_C = (176, 168, 120)   # svetlejša zlata za labele
LINE_C  = (184, 146, 77)    # zlata za linije
DIV_C   = (212, 196, 160)   # svetla za dividerje
SQ_OFF  = (212, 196, 160)   # kvadratki off
SQ_ON   = (184, 146, 77)    # kvadratki on
GREEN   = (50,  180, 80)    # wifi on
RED     = (180, 40,  40)    # wifi off / stop

# Fonti
FONTS_DIR    = '/home/pi/vyne/fonts/'
FONT_LIGHT   = FONTS_DIR + 'Montserrat-ExtraLight.ttf'
FONT_REG     = FONTS_DIR + 'Montserrat-Regular.ttf'
FONT_BOLD    = FONTS_DIR + 'Montserrat-Bold.ttf'
FONT_ITALIC  = FONTS_DIR + 'Cormorant-LightItalic.ttf'
FONT_CORP    = FONTS_DIR + 'Cormorant-Italic.ttf'

# Process types
PROCESS_TYPES = [
    {"name": "Classic",   "hours": 72,   "label": "72h"},
    {"name": "Extended",  "hours": 672,  "label": "672h"},
    {"name": "Premium",   "hours": 2016, "label": "2016h"},
    {"name": "Custom",    "hours": 0,    "label": "up to 5000h"},
]

# Kvadratki za spektrogram
sqSize    = 6
sqGap     = 3
nCols     = 280 // (sqSize + sqGap)
nRows_play = 3
rowH      = sqSize + 2
sqStartX  = 20
playBottomY = 214
playStartY  = playBottomY - (nRows_play - 1) * rowH

# ============================================================
# GPIO
# ============================================================

BTN_UP    = 17
BTN_DOWN  = 27
BTN_ENTER = 22
BTN_BACK  = 5
BL_PIN    = 12

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(BTN_UP,    GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BTN_DOWN,  GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BTN_ENTER, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BTN_BACK,  GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BL_PIN,    GPIO.OUT)
GPIO.output(BL_PIN,   GPIO.LOW)

def get_key():
    while True:
        if GPIO.input(BTN_UP)    == GPIO.LOW: time.sleep(0.2); return 'UP'
        if GPIO.input(BTN_DOWN)  == GPIO.LOW: time.sleep(0.2); return 'DOWN'
        if GPIO.input(BTN_ENTER) == GPIO.LOW: time.sleep(0.2); return 'ENTER'
        if GPIO.input(BTN_BACK)  == GPIO.LOW: time.sleep(0.2); return 'ESC'
        time.sleep(0.05)

def wait_release(pin):
    while GPIO.input(pin) == GPIO.LOW: time.sleep(0.05)
    time.sleep(0.3)

# ============================================================
# WIFI
# ============================================================

wifi_status = False

def _wifi_check_thread():
    global wifi_status
    while True:
        try:
            result = subprocess.run(['iwgetid','-r'], capture_output=True, text=True, timeout=2)
            wifi_status = result.stdout.strip() != ""
        except Exception:
            wifi_status = False
        time.sleep(10)

threading.Thread(target=_wifi_check_thread, daemon=True).start()

def check_wifi(): return wifi_status

# ============================================================
# LAST SEEN
# ============================================================

def _last_seen_thread():
    while True:
        time.sleep(30)
        try: update_last_seen()
        except Exception: pass

threading.Thread(target=_last_seen_thread, daemon=True).start()

# ============================================================
# AUDIO + DISPLAY INIT
# ============================================================

pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=4096)

serial = spi(port=0, device=0, gpio_DC=24, gpio_RST=25)
device = ili9341(serial, width=320, height=240)

blank = Image.new("RGB", (WIDTH, HEIGHT), BG)
device.display(blank)
GPIO.output(BL_PIN, GPIO.HIGH)

from intro import play_intro, play_countdown

state = load_state()
if not state or not state.get("active"):
    play_intro(device)

# ============================================================
# FONTS
# ============================================================

def font(path, size): return ImageFont.truetype(path, size)

f_brand    = font(FONT_LIGHT,  26)
f_copy     = font(FONT_LIGHT,   8)
f_section  = font(FONT_BOLD,   10)
f_menu_lg  = font(FONT_CORP,   26)
f_menu_sm  = font(FONT_CORP,   18)
f_label    = font(FONT_REG,     9)
f_artist   = font(FONT_CORP,   22)
f_track    = font(FONT_LIGHT,   9)
f_time     = font(FONT_LIGHT,  28)
f_hours    = font(FONT_BOLD,    9)
f_small    = font(FONT_LIGHT,   9)
f_process  = font(FONT_ITALIC, 20)
f_classic  = font(FONT_ITALIC, 22)
f_log      = font(FONT_REG,     9)

COPYRIGHT = "\u00a9 2026 VYNE+ \u00b7 v1.0.0 \u00b7 All rights reserved"

# ============================================================
# ID3 + LOG HELPERS
# ============================================================

def read_tags(filepath):
    try:
        tags   = ID3(filepath)
        artist = str(tags.get('TPE1', 'Unknown Artist'))
        title  = str(tags.get('TIT2', 'Unknown Title'))
    except Exception:
        name  = os.path.basename(filepath).replace(".mp3","")
        parts = name.split(" - ", 1)
        artist = parts[0] if len(parts)>1 else "Unknown"
        title  = parts[1] if len(parts)>1 else name
    return artist, title

def format_log_line(line):
    try:
        line    = line.strip()
        ts_part = line[1:20]
        rest    = line[22:]
        dt_short = ts_part[2:14]
        if "PROCESS STARTED" in rest: return f"{dt_short} START: {rest.replace('PROCESS STARTED: ','')}"
        elif "PROCESS STOPPED" in rest: return f"{dt_short} STOP"
        elif "POWER LOST" in rest: return f"{dt_short} PWR LOST"
        elif "POWER RESTORED" in rest: return f"{dt_short} PWR RESTORED"
        else: return f"{dt_short} {rest}"
    except Exception: return line[:62]

def load_log_lines():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE,"r") as f:
            lines = f.readlines()
            return list(reversed([format_log_line(l) for l in lines[-50:]]))
    return []

def get_mp3_list(directory):
    files = glob.glob(directory + "*.mp3")
    return sorted([os.path.basename(f) for f in files])

def get_usb_mp3_list():
    result = []
    seen   = set()
    for base in ("/media", "/run/media"):
        if not os.path.exists(base):
            continue
        for user in os.listdir(base):
            user_path = os.path.join(base, user)
            if not os.path.isdir(user_path):
                continue
            for drive in os.listdir(user_path):
                drive_path = os.path.join(user_path, drive)
                if not os.path.isdir(drive_path):
                    continue
                files = set(
                    glob.glob(os.path.join(drive_path, "*.mp3")) +
                    glob.glob(os.path.join(drive_path, "**", "*.mp3"), recursive=True)
                )
                for f in sorted(files):
                    if f not in seen:
                        seen.add(f)
                        result.append((os.path.basename(f), f))
    return result

# ============================================================
# DRAW HELPERS
# ============================================================

def new_canvas():
    img  = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    return img, draw

def show(img): device.display(img)

def centered_x(draw, text, font):
    bbox = draw.textbbox((0,0), text, font=font)
    return WIDTH//2 - (bbox[2]-bbox[0])//2

def draw_centered(draw, fnt, text, color, y):
    x = centered_x(draw, text, fnt)
    draw.text((x, y), text, font=fnt, fill=color)

def draw_divider(draw, y, x1=80, x2=240):
    draw.line([(x1,y),(x2,y)], fill=DIV_C, width=1)

def draw_wifi(draw):
    color = GREEN if check_wifi() else RED
    draw.ellipse([(WIDTH-17,7),(WIDTH-7,17)], fill=color)

def draw_header(draw):
    """Header z VYNE+ logotipom in zlatno ločevalno linijo."""
    letters = ['V','Y','N','E']
    spacing = 10; charW = 16
    logoW   = len(letters)*charW + (len(letters)-1)*spacing + 22
    x       = WIDTH//2 - logoW//2
    for l in letters:
        draw.text((x, 6), l, font=f_brand, fill=VYNE_C)
        x += charW + spacing
    draw.text((x, 6), '+', font=f_brand, fill=PLUS_C)
    draw_wifi(draw)
    draw.line([(20,40),(300,40)], fill=LINE_C, width=1)

def draw_footer(draw):
    """Copyright footer."""
    bbox = draw.textbbox((0,0), COPYRIGHT, font=f_copy)
    w    = bbox[2]-bbox[0]
    draw.text((WIDTH//2-w//2, 228), COPYRIGHT, font=f_copy, fill=LABEL_C)

def draw_squares(draw, y=210, bars=None):
    """Kvadratki kot ločevalnik ali spektrogram."""
    n = 16
    sqS = 6; sqG = 4
    totalW = n*sqS + (n-1)*sqG
    sx = WIDTH//2 - totalW//2
    for i in range(n):
        if bars is not None:
            active = bars[i] > 0.45
            draw.rectangle([(sx,y),(sx+sqS,y+sqS)], fill=SQ_ON if active else SQ_OFF)
        else:
            draw.rectangle([(sx,y),(sx+sqS,y+sqS)], fill=SQ_OFF)
        sx += sqS + sqG

def draw_playing_spectrum(draw, bars=None):
    """Spektrogram 3×31 za playing screen."""
    for col in range(nCols):
        if bars is not None:
            amp = bars[min(col, len(bars)-1)] if bars else 0
            active = round(amp * nRows_play)
        else:
            active = 0
        for row in range(nRows_play):
            sx = sqStartX + col*(sqSize+sqGap)
            sy = playBottomY - row*rowH
            draw.rectangle([(sx,sy),(sx+sqSize-1,sy+sqSize-1)],
                           fill=SQ_ON if row<active else SQ_OFF)

def draw_section_title(draw, title):
    """Bold zeleni naslov sekcije."""
    draw_centered(draw, f_section, title, VYNE_C, 48)

# ============================================================
# SCREENS
# ============================================================

def screen_menu(selected):
    img, draw = new_canvas()
    draw_header(draw)
    draw_section_title(draw, "")  # brez naslova na menuju
    items = ["Start Aging", "Library", "Events"]
    # enakomerna porazdelitev med linijo (y=40) in kvadratki (y=210): 170px / 4 = 42.5
    for i, item in enumerate(items):
        y_c = 40 + (i + 1) * 170 // 4
        if i == selected:
            draw_centered(draw, f_menu_lg, item, WINE, y_c - 13)
        else:
            draw_centered(draw, f_menu_sm, item, GOLD, y_c - 9)
    draw_squares(draw, y=210)
    draw_footer(draw)
    show(img)

def screen_select_process(selected):
    img, draw = new_canvas()
    draw_header(draw)
    draw_section_title(draw, "SELECT PROCESS")
    rowH2  = 42
    # 4 elementi centrično med y=48 in y=210: startY = 48 + (162 - 3*42) / 2 ≈ 62
    startY = 62
    for i, pt in enumerate(PROCESS_TYPES):
        y     = startY + i*rowH2
        isSel = i == selected
        fnt   = f_menu_lg if isSel else f_menu_sm
        col   = WINE if isSel else GOLD
        draw_centered(draw, fnt, pt["name"], col, y)
        # label pod imenom: 26px (sel) ali 18px (unsel) + 2px razmak
        draw_centered(draw, f_label, pt["label"], WINE if isSel else LABEL_C, y + (28 if isSel else 18))
        if i < len(PROCESS_TYPES)-1:
            draw_divider(draw, y+38, 60, 260)
    draw_squares(draw, y=210)
    draw_footer(draw)
    show(img)

def screen_select_mp3(mp3_list, selected, title="SELECT MUSIC"):
    img, draw = new_canvas()
    draw_header(draw)
    draw_section_title(draw, title)
    startY = 72
    rowH2  = 36
    visible = 4
    total   = len(mp3_list)
    start   = max(0, min(selected-1, total-visible))
    end     = min(start+visible, total)
    for i, idx in enumerate(range(start, end)):
        mp3   = mp3_list[idx]
        name  = mp3[0] if isinstance(mp3, tuple) else mp3
        isSel = idx == selected
        art, trk = read_tags(MUSIC_DIR + (mp3[1] if isinstance(mp3,tuple) else mp3)) if not isinstance(mp3, tuple) else (name, "")
        y = startY + i*rowH2
        fnt = f_menu_lg if isSel else f_menu_sm
        col = WINE if isSel else GOLD
        draw_centered(draw, fnt, art, col, y)
        draw_centered(draw, f_track, trk[:36], LABEL_C if not isSel else WINE, y+16)
        if i < end-start-1:
            draw_divider(draw, y+30, 40, 280)
    draw_squares(draw, y=210)
    draw_footer(draw)
    show(img)

def screen_library(mp3_list, selected):
    img, draw = new_canvas()
    draw_header(draw)
    draw_section_title(draw, "LIBRARY")
    all_items = mp3_list + ["+ Load from USB"]
    total     = len(all_items)
    visible   = 4
    start     = max(0, min(selected-1, total-visible))
    end       = min(start+visible, total)
    startY    = 72; rowH2 = 36
    for i, idx in enumerate(range(start, end)):
        item  = all_items[idx]
        isSel = idx == selected
        fnt   = f_menu_lg if isSel else f_menu_sm
        col   = WINE if isSel else GOLD
        name  = item[:28] if len(item)>28 else item
        draw_centered(draw, fnt, name, col, startY+i*rowH2)
        if i < end-start-1:
            draw_divider(draw, startY+i*rowH2+30, 40, 280)
    draw_squares(draw, y=210)
    draw_footer(draw)
    show(img)

def screen_usb_mp3(mp3_list, selected):
    img, draw = new_canvas()
    draw_header(draw)
    draw_section_title(draw, "SELECT FROM USB")
    if not mp3_list:
        draw_centered(draw, f_menu_sm, "No MP3 on USB", LABEL_C, 120)
    else:
        total   = len(mp3_list)
        visible = 4
        start   = max(0, min(selected-1, total-visible))
        end     = min(start+visible, total)
        startY  = 72; rowH2 = 36
        for i, idx in enumerate(range(start, end)):
            item  = mp3_list[idx]
            name  = item[0] if isinstance(item, tuple) else item
            isSel = idx == selected
            fnt   = f_menu_lg if isSel else f_menu_sm
            col   = WINE if isSel else GOLD
            draw_centered(draw, fnt, name[:28], col, startY+i*rowH2)
            if i < end-start-1:
                draw_divider(draw, startY+i*rowH2+30, 40, 280)
    draw_squares(draw, y=210)
    draw_footer(draw)
    show(img)

def screen_library_options(filename, selected):
    img, draw = new_canvas()
    draw_header(draw)
    draw_section_title(draw, "FILE OPTIONS")
    name = filename[:26] if len(filename)>26 else filename
    draw_centered(draw, f_menu_sm, name, GOLD, 72)
    draw_divider(draw, 100, 40, 280)
    draw_centered(draw, f_menu_lg if selected==0 else f_menu_sm, "Delete", WINE if selected==0 else GOLD, 118)
    draw_centered(draw, f_menu_lg if selected==1 else f_menu_sm, "Cancel", WINE if selected==1 else GOLD, 158)
    draw_squares(draw, y=210)
    draw_footer(draw)
    show(img)

def screen_copy_confirm(filename, selected):
    img, draw = new_canvas()
    draw_header(draw)
    draw_section_title(draw, "COPY TO DEVICE?")
    name = os.path.basename(filename)
    name = name[:26] if len(name)>26 else name
    draw_centered(draw, f_menu_sm, name, GOLD, 72)
    draw_divider(draw, 100, 40, 280)
    draw_centered(draw, f_menu_lg if selected==0 else f_menu_sm, "Yes", WINE if selected==0 else GOLD, 118)
    draw_centered(draw, f_menu_lg if selected==1 else f_menu_sm, "No",  WINE if selected==1 else GOLD, 158)
    draw_squares(draw, y=210)
    draw_footer(draw)
    show(img)

def screen_analyzing(progress=0.0):
    img, draw = new_canvas()
    draw_header(draw)
    draw_section_title(draw, "ANALYSING MUSIC")
    draw_centered(draw, f_classic, "Preparing your bottle's", GOLD, 80)
    draw_centered(draw, f_artist,  "Sonic Journey",           GOLD, 108)
    # progress bar
    draw.rectangle([(20,148),(300,154)], fill=SQ_OFF)
    filled = int(280*min(progress,1.0))
    if filled > 0:
        draw.rectangle([(20,148),(20+filled,154)], fill=GOLD)
    pct = int(progress*100)
    draw_centered(draw, f_section, f"{pct}%", VYNE_C, 162)
    draw_squares(draw, y=210)
    draw_footer(draw)
    show(img)

def screen_confirm(artist, title, days):
    # lookup process name
    process_name = "Classic"
    process_label = "72h"
    for pt in PROCESS_TYPES:
        if pt["hours"] == days or (days > 2000 and pt["name"]=="Premium"):
            process_name  = pt["name"]
            process_label = pt["label"]
            break
    img, draw = new_canvas()
    draw_header(draw)
    draw_section_title(draw, "CONFIRM AGING")
    # 3 področja
    draw_centered(draw, f_label,  "MUSIC",              LABEL_C, 60)
    draw_centered(draw, f_artist, artist,                GOLD,    76)
    draw_centered(draw, f_track,  title,                 GOLD,    100)
    draw_divider(draw, 114, 80, 240)
    draw_centered(draw, f_label,  "PROCESS",            LABEL_C, 120)
    draw_centered(draw, f_classic, f"{process_name} · {process_label}", GOLD, 136)
    draw_divider(draw, 158, 80, 240)
    draw_centered(draw, f_menu_sm, "Press ENTER to begin", WINE, 168)
    draw_centered(draw, f_small,   "BACK to change",       LABEL_C, 186)
    draw_squares(draw, y=210)
    draw_footer(draw)
    show(img)

def screen_stop_confirm(hold_pct=0):
    img, draw = new_canvas()
    draw_header(draw)
    draw_section_title(draw, "STOP AGING")
    draw_centered(draw, f_classic, "Are you sure you want to", GOLD, 76)
    draw_centered(draw, f_artist,  "end this journey?",        WINE, 102)
    draw_centered(draw, f_small,   "This cannot be undone",    LABEL_C, 126)
    draw_divider(draw, 140, 80, 240)
    draw_centered(draw, f_section, "HOLD BACK TO CONFIRM",     VYNE_C, 152)
    draw.rectangle([(20,162),(300,168)], fill=SQ_OFF)
    if hold_pct > 0:
        draw.rectangle([(20,162),(20+int(280*hold_pct),168)], fill=WINE)
    secs = max(0, int((1-hold_pct)*HOLD_TIME)+1)
    draw_centered(draw, f_section, f"{secs}s", WINE, 174)
    draw_squares(draw, y=210)
    draw_footer(draw)
    show(img)

def screen_playing():
    state = load_state()
    t     = time_remaining(state)
    if not t: return
    img, draw = new_canvas()
    draw_header(draw)

    # Lookup process
    process_hours = state.get("hours", state.get("days", 7)*24)
    process_name  = "Classic"
    for pt in PROCESS_TYPES:
        if pt["hours"] == process_hours:
            process_name = pt["name"]
            break

    # Spektrogram pozicija — 3 vrstice nad footerjem
    spec_top = playBottomY - (nRows_play-1)*rowH

    # Razpoložljiv prostor med linijo (40) in spektrogramom (spec_top)
    areaTop    = 40
    areaBottom = spec_top - 4
    areaH      = areaBottom - areaTop
    zoneH      = areaH // 3

    zone1mid = areaTop + int(zoneH*0.5)
    zone2mid = areaTop + int(zoneH*1.5)
    zone3mid = areaTop + int(zoneH*2.5)
    div1Y    = areaTop + zoneH
    div2Y    = areaTop + zoneH*2

    draw_divider(draw, div1Y, 80, 240)
    draw_divider(draw, div2Y, 80, 240)

    # 1. Process
    draw_centered(draw, f_classic, f"{process_name} · {process_hours}h", GOLD, zone1mid-8)

    # 2. Artist + track
    draw_centered(draw, f_artist, state["artist"],     WINE, zone2mid-10)
    draw_centered(draw, f_track,  state["track"],      GOLD, zone2mid+8)

    # 3. Hours remaining + countdown
    total_hours = t['hours']
    time_str    = f"{total_hours}:{t['minutes']:02d}:{t['seconds']:02d}"
    draw_centered(draw, f_hours, "HOURS REMAINING", VYNE_C, zone3mid-22)
    draw_centered(draw, f_time,  time_str,           VYNE_C, zone3mid+2)

    mp3_path = MUSIC_DIR + state.get("mp3","")
    elapsed  = (time.time()-playing_start_time) if playing_start_time else 0
    bars     = get_bars(mp3_path, elapsed) if os.path.exists(mp3_path) else None
    draw_playing_spectrum(draw, bars)

    draw_footer(draw)
    show(img)

def screen_events(log_lines, scroll):
    img, draw = new_canvas()
    draw_header(draw)
    draw_section_title(draw, "EVENTS")
    visible     = 9
    start       = scroll
    end         = min(scroll+visible, len(log_lines))
    visible_log = log_lines[start:end]
    if not log_lines:
        draw_centered(draw, f_menu_sm, "No events yet", LABEL_C, 120)
    else:
        for i, line in enumerate(visible_log):
            text  = line[:62] if len(line)>62 else line
            color = GOLD if i%2==0 else LABEL_C
            draw.text((4, 62+i*16), text, font=f_log, fill=color)
    draw_footer(draw)
    show(img)

def screen_no_mp3():
    img, draw = new_canvas()
    draw_header(draw)
    draw_centered(draw, f_artist,  "No Music Found", GOLD,    100)
    draw_centered(draw, f_menu_sm, "Add via Library", LABEL_C, 140)
    draw_squares(draw, y=210)
    draw_footer(draw)
    show(img)

def screen_message(line1, line2="", color=WINE):
    img, draw = new_canvas()
    draw_header(draw)
    draw_centered(draw, f_artist,  line1, color,    100)
    if line2:
        draw_centered(draw, f_menu_sm, line2, LABEL_C, 140)
    draw_centered(draw, f_small, "ENTER to continue", LABEL_C, 186)
    draw_squares(draw, y=210)
    draw_footer(draw)
    show(img)

def fade_in_playing():
    state = load_state()
    t     = time_remaining(state)
    if not t: return
    total_hours = t['hours']
    time_str    = f"{total_hours}:{t['minutes']:02d}:{t['seconds']:02d}"

    process_hours = state.get("hours", state.get("days",7)*24)
    process_name  = "Classic"
    for pt in PROCESS_TYPES:
        if pt["hours"] == process_hours:
            process_name = pt["name"]
            break

    spec_top   = playBottomY - (nRows_play-1)*rowH
    areaTop    = 40
    areaBottom = spec_top - 4
    areaH      = areaBottom - areaTop
    zoneH      = areaH // 3
    zone1mid   = areaTop + int(zoneH*0.5)
    zone2mid   = areaTop + int(zoneH*1.5)
    zone3mid   = areaTop + int(zoneH*2.5)
    div1Y      = areaTop + zoneH
    div2Y      = areaTop + zoneH*2

    def b(c, a): return tuple(int(BG[i]+(c[i]-BG[i])*a) for i in range(3))

    for step in range(0, 256, 18):
        a = step/255.0
        img, draw = new_canvas()

        # header
        letters = ['V','Y','N','E']
        spacing = 10; charW = 16
        lw = len(letters)*charW+(len(letters)-1)*spacing+22
        x  = WIDTH//2-lw//2
        for l in letters:
            draw.text((x,6),l,font=f_brand,fill=b(VYNE_C,a)); x+=charW+spacing
        draw.text((x,6),'+',font=f_brand,fill=b(PLUS_C,a))
        draw.line([(20,40),(300,40)],fill=b(LINE_C,a),width=1)

        draw_divider(draw, div1Y, 80, 240)
        draw_divider(draw, div2Y, 80, 240)

        draw_centered(draw, f_classic, f"{process_name} · {process_hours}h", b(GOLD,a), zone1mid-8)
        draw_centered(draw, f_artist,  state["artist"], b(WINE,a), zone2mid-10)
        draw_centered(draw, f_track,   state["track"],  b(GOLD,a), zone2mid+8)
        draw_centered(draw, f_hours,   "HOURS REMAINING", b(VYNE_C,a), zone3mid-22)
        draw_centered(draw, f_time,    time_str, b(VYNE_C,a), zone3mid+2)

        draw_footer(draw)
        show(img)
        time.sleep(0.02)

# ============================================================
# APP STATES
# ============================================================

STATE_MENU            = "menu"
STATE_SELECT_PROCESS  = "select_process"
STATE_SELECT_MP3      = "select_mp3"
STATE_CONFIRM         = "confirm"
STATE_PLAYING         = "playing"
STATE_STOP_CONFIRM    = "stop_confirm"
STATE_LIBRARY         = "library"
STATE_LIBRARY_OPTIONS = "library_options"
STATE_USB_MP3         = "usb_mp3"
STATE_COPY_CONFIRM    = "copy_confirm"
STATE_MESSAGE         = "message"
STATE_EVENTS          = "events"

playing_start_time = None

# ============================================================
# INIT
# ============================================================

log_interruption()

if state and state.get("active"):
    try:
        pygame.mixer.music.load(MUSIC_DIR + state["mp3"])
        pygame.mixer.music.play(-1)
        playing_start_time = time.time()
        threading.Thread(target=precompute, args=(MUSIC_DIR+state["mp3"],), daemon=True).start()
        app_state = STATE_PLAYING
    except Exception as e:
        print(f"[init] failed to load music: {e}")
        stop_process()
        app_state = STATE_MENU
else:
    app_state = STATE_MENU

selected         = 0
days             = 72
mp3_list         = []
selected_mp3     = ""
artist           = ""
track            = ""
usb_mp3_list     = []
copy_file        = ""
message          = ("","")
log_lines        = []
log_scroll       = 0
library_list     = []
library_selected = 0
lib_opt_selected = 0
copy_selected    = 0
msg_return_state = STATE_MENU

# ============================================================
# MAIN LOOP
# ============================================================

try:
    while True:

        if app_state == STATE_PLAYING:
            if GPIO.input(BTN_BACK) == GPIO.LOW:
                wait_release(BTN_BACK)
                app_state = STATE_STOP_CONFIRM
            else:
                screen_playing()
                time.sleep(0.15)
            continue

        if app_state == STATE_STOP_CONFIRM:
            if GPIO.input(BTN_BACK) == GPIO.LOW:
                press_start = time.time()
                confirmed   = False
                while GPIO.input(BTN_BACK) == GPIO.LOW:
                    elapsed  = time.time() - press_start
                    hold_pct = min(elapsed / HOLD_TIME, 1.0)
                    screen_stop_confirm(hold_pct=hold_pct)
                    if elapsed >= HOLD_TIME:
                        confirmed = True
                        break
                    time.sleep(0.05)
                if confirmed:
                    wait_release(BTN_BACK)
                    pygame.mixer.music.stop()
                    stop_process()
                    app_state = STATE_MENU
                    selected = 0
                else:
                    wait_release(BTN_BACK)
                    screen_stop_confirm()
            elif GPIO.input(BTN_ENTER) == GPIO.LOW:
                wait_release(BTN_ENTER)
                app_state = STATE_PLAYING
            else:
                screen_stop_confirm()
                time.sleep(0.15)
            continue

        if app_state == STATE_MENU:            screen_menu(selected)
        elif app_state == STATE_SELECT_PROCESS: screen_select_process(selected)
        elif app_state == STATE_SELECT_MP3:     screen_select_mp3(mp3_list, selected)
        elif app_state == STATE_CONFIRM:        screen_confirm(artist, track, days)
        elif app_state == STATE_LIBRARY:        screen_library(library_list, library_selected)
        elif app_state == STATE_LIBRARY_OPTIONS: screen_library_options(library_list[library_selected], lib_opt_selected)
        elif app_state == STATE_USB_MP3:        screen_usb_mp3(usb_mp3_list, library_selected)
        elif app_state == STATE_COPY_CONFIRM:   screen_copy_confirm(copy_file, copy_selected)
        elif app_state == STATE_MESSAGE:        screen_message(message[0], message[1])
        elif app_state == STATE_EVENTS:         screen_events(log_lines, log_scroll)

        key = get_key()

        if app_state == STATE_MENU:
            if key == 'UP':    selected = (selected-1)%3
            elif key == 'DOWN': selected = (selected+1)%3
            elif key == 'ENTER':
                if selected == 0:   app_state = STATE_SELECT_PROCESS; selected = 0
                elif selected == 1:
                    library_list=get_mp3_list(MUSIC_DIR); library_selected=0; app_state=STATE_LIBRARY
                elif selected == 2:
                    log_lines=load_log_lines(); log_scroll=0; app_state=STATE_EVENTS

        elif app_state == STATE_SELECT_PROCESS:
            if key == 'UP':    selected = (selected-1)%len(PROCESS_TYPES)
            elif key == 'DOWN': selected = (selected+1)%len(PROCESS_TYPES)
            elif key == 'ENTER':
                days     = PROCESS_TYPES[selected]["hours"]
                mp3_list = get_mp3_list(MUSIC_DIR)
                if not mp3_list:
                    screen_no_mp3(); time.sleep(2); app_state=STATE_MENU
                else:
                    selected=0; app_state=STATE_SELECT_MP3
            elif key == 'ESC': app_state=STATE_MENU; selected=0

        elif app_state == STATE_SELECT_MP3:
            if key == 'UP':    selected = (selected-1)%max(len(mp3_list),1)
            elif key == 'DOWN': selected = (selected+1)%max(len(mp3_list),1)
            elif key == 'ENTER':
                selected_mp3  = mp3_list[selected]
                artist, track = read_tags(MUSIC_DIR+selected_mp3)
                app_state     = STATE_CONFIRM
            elif key == 'ESC': app_state=STATE_SELECT_PROCESS; selected=0

        elif app_state == STATE_LIBRARY:
            all_items = library_list+["+ Load from USB"]
            total     = len(all_items)
            if key == 'UP':    library_selected=(library_selected-1)%total
            elif key == 'DOWN': library_selected=(library_selected+1)%total
            elif key == 'ENTER':
                if library_selected==total-1:
                    usb_mp3_list=get_usb_mp3_list(); library_selected=0
                    if not usb_mp3_list:
                        message=("NO USB FOUND","Insert USB and try again"); msg_return_state=STATE_LIBRARY; app_state=STATE_MESSAGE
                    else: app_state=STATE_USB_MP3
                else:
                    lib_opt_selected=0; app_state=STATE_LIBRARY_OPTIONS
            elif key == 'ESC': app_state=STATE_MENU; selected=0

        elif app_state == STATE_LIBRARY_OPTIONS:
            if key == 'UP':    lib_opt_selected=(lib_opt_selected-1)%2
            elif key == 'DOWN': lib_opt_selected=(lib_opt_selected+1)%2
            elif key == 'ENTER':
                if lib_opt_selected==0:
                    filepath=os.path.join(MUSIC_DIR,library_list[library_selected])
                    try: os.remove(filepath); message=("FILE DELETED",library_list[library_selected][:24])
                    except: message=("DELETE FAILED","Try again")
                    library_list=get_mp3_list(MUSIC_DIR); library_selected=0
                    msg_return_state=STATE_LIBRARY; app_state=STATE_MESSAGE
                else: app_state=STATE_LIBRARY
            elif key == 'ESC': app_state=STATE_LIBRARY

        elif app_state == STATE_USB_MP3:
            total=len(usb_mp3_list)
            if key == 'UP':    library_selected=(library_selected-1)%max(total,1)
            elif key == 'DOWN': library_selected=(library_selected+1)%max(total,1)
            elif key == 'ENTER' and usb_mp3_list:
                copy_file=usb_mp3_list[library_selected][1]; copy_selected=0; app_state=STATE_COPY_CONFIRM
            elif key == 'ESC': app_state=STATE_LIBRARY; library_selected=0

        elif app_state == STATE_COPY_CONFIRM:
            if key == 'UP':    copy_selected=(copy_selected-1)%2
            elif key == 'DOWN': copy_selected=(copy_selected+1)%2
            elif key == 'ENTER':
                if copy_selected==0:
                    try:
                        dest=os.path.join(MUSIC_DIR,os.path.basename(copy_file))
                        shutil.copy2(copy_file, dest)
                        library_list=get_mp3_list(MUSIC_DIR)
                        t=threading.Thread(target=precompute,args=(dest,),daemon=True)
                        t.start()
                        while t.is_alive():
                            screen_analyzing(get_progress(dest)); time.sleep(0.15)
                        screen_analyzing(1.0); time.sleep(0.5)
                        message=("FILE READY","MP3 analysed & ready")
                    except: message=("COPY FAILED","Try again")
                    msg_return_state=STATE_LIBRARY; app_state=STATE_MESSAGE
                else: app_state=STATE_USB_MP3
            elif key == 'ESC': app_state=STATE_USB_MP3

        elif app_state == STATE_CONFIRM:
            if key == 'ENTER':
                new_process(selected_mp3, artist, track, days)
                pygame.mixer.music.load(MUSIC_DIR+selected_mp3)
                play_countdown(device)
                pygame.mixer.music.play(-1)
                playing_start_time=time.time()
                fade_in_playing()
                app_state=STATE_PLAYING
            elif key == 'ESC': app_state=STATE_SELECT_MP3

        elif app_state == STATE_EVENTS:
            if key == 'UP':    log_scroll=max(0,log_scroll-1)
            elif key == 'DOWN': log_scroll=min(max(0,len(log_lines)-9),log_scroll+1)
            elif key in ('ESC','ENTER'): app_state=STATE_MENU; selected=0

        elif app_state == STATE_MESSAGE:
            if key in ('ENTER','ESC'):
                app_state=msg_return_state
                if msg_return_state==STATE_MENU: selected=0

except KeyboardInterrupt:
    pass
finally:
    try: pygame.mixer.quit()
    except: pass
    try: GPIO.output(BL_PIN, GPIO.LOW)
    except: pass
    try:
        blank=Image.new("RGB",(WIDTH,HEIGHT),BG)
        device.display(blank)
    except: pass
    try: GPIO.cleanup()
    except: pass
    print("\nVYNE+ stopped.")
