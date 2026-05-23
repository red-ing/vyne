# ============================================================
# VYNE+ intro.py — nov dizajn
# ============================================================
import os
import time
import math
from PIL import Image, ImageDraw, ImageFont
import pygame.mixer

WIDTH  = 320
HEIGHT = 240

BG      = (244, 237, 224)
VYNE_C  = (31,  53,  34)
PLUS_C  = (184, 146, 77)
LINE_C  = (184, 146, 77)
SQ_OFF  = (212, 196, 160)
SQ_ON   = (184, 146, 77)
GOLD    = (184, 146, 77)

FONTS_DIR   = '/home/pi/vyne/fonts/'
FONT_LIGHT  = FONTS_DIR + 'Montserrat-ExtraLight.ttf'
FONT_ITALIC = FONTS_DIR + 'Cormorant-LightItalic.ttf'
SOUNDS_DIR  = '/home/pi/vyne/sounds/'
SOUND_TICK  = SOUNDS_DIR + 'tick.mp3'
SOUND_START = SOUNDS_DIR + 'start.mp3'

_f_logo   = ImageFont.truetype(FONT_LIGHT, 52)
_f_slogan = ImageFont.truetype(FONT_ITALIC, 14)

sqSize    = 6
sqGap     = 3
nCols     = 280 // (sqSize + sqGap)
nRows     = 13
rowH      = sqSize + 2
sqStartX  = 20
sqStartY  = HEIGHT // 2 - (nRows * rowH) // 2
playStartY = 214 - 2 * rowH

DIGITS = {
    '3': [
        [1,1,1,1,1,1,1,1,1],[1,1,1,1,1,1,1,1,1],
        [0,0,0,0,0,0,0,1,1],[0,0,0,0,0,0,0,1,1],
        [0,1,1,1,1,1,1,1,1],[0,1,1,1,1,1,1,1,1],
        [0,0,0,0,0,0,0,1,1],[0,0,0,0,0,0,0,1,1],[0,0,0,0,0,0,0,1,1],
        [1,1,1,1,1,1,1,1,1],[1,1,1,1,1,1,1,1,1],
    ],
    '2': [
        [1,1,1,1,1,1,1,1,1],[1,1,1,1,1,1,1,1,1],
        [0,0,0,0,0,0,0,1,1],[0,0,0,0,0,0,0,1,1],
        [1,1,1,1,1,1,1,1,1],[1,1,1,1,1,1,1,1,1],
        [1,1,0,0,0,0,0,0,0],[1,1,0,0,0,0,0,0,0],[1,1,0,0,0,0,0,0,0],
        [1,1,1,1,1,1,1,1,1],[1,1,1,1,1,1,1,1,1],
    ],
    '1': [
        [0,0,0,0,1,1,0,0,0],[0,0,0,1,1,1,0,0,0],[0,0,1,0,1,1,0,0,0],
        [0,0,0,0,1,1,0,0,0],[0,0,0,0,1,1,0,0,0],[0,0,0,0,1,1,0,0,0],
        [0,0,0,0,1,1,0,0,0],[0,0,0,0,1,1,0,0,0],[0,0,0,0,1,1,0,0,0],
        [0,0,1,1,1,1,1,1,0],[0,0,1,1,1,1,1,1,0],
    ],
}
DIGIT_COLS = 9
DIGIT_ROWS = 11
colOffset  = (nCols - DIGIT_COLS) // 2
rowOffset  = (nRows - DIGIT_ROWS) // 2

def is_digit_on(row, col, num):
    dc = col - colOffset
    dr = (nRows - 1 - row) - rowOffset
    if dr < 0 or dr >= DIGIT_ROWS or dc < 0 or dc >= DIGIT_COLS:
        return False
    return DIGITS[num][dr][dc] == 1

def blend(c1, c2, a):
    return tuple(int(c1[i] + (c2[i]-c1[i])*a) for i in range(3))

def get_amp(col, t):
    freq = col / nCols
    bass = (1 - freq) ** 1.5
    return max(0, min(1, bass * 0.6 + math.sin(t * 2.5 - col * 0.4) * 0.4 + 0.2))

def play_sound(filepath):
    if os.path.exists(filepath):
        try:
            pygame.mixer.Sound(filepath).play()
        except Exception:
            pass

def new_canvas():
    return Image.new('RGB', (WIDTH, HEIGHT), BG)

def draw_spectrum(img, t, alpha):
    draw = ImageDraw.Draw(img)
    for col in range(nCols):
        amp    = get_amp(col, t)
        active = round(amp * nRows)
        for row in range(nRows):
            sx   = sqStartX + col * (sqSize + sqGap)
            sy   = sqStartY + (nRows - 1 - row) * rowH
            base = SQ_ON if row < active else SQ_OFF
            draw.rectangle([(sx,sy),(sx+sqSize-1,sy+sqSize-1)], fill=blend(BG, base, alpha))

def draw_logo(img, a):
    draw    = ImageDraw.Draw(img)
    blockH  = nRows * rowH
    logoH   = 46
    cStartY = sqStartY + (blockH - (logoH + 10 + 1 + 10 + 14)) // 2
    logoY   = cStartY + logoH
    lineY   = logoY + 10
    sloganY = lineY + 10 + 14
    x = logoX
    for l in letters:
        draw.text((x, logoY-logoH), l, font=_f_logo, fill=blend(BG, VYNE_C, a))
        x += charW + spacing
    draw.text((x, logoY-logoH), '+', font=_f_logo, fill=blend(BG, PLUS_C, a))
    draw.line([(60,lineY),(260,lineY)], fill=blend(BG, LINE_C, a), width=1)
    bbox = draw.textbbox((0,0), 'WE BOTTLE MUSIC', font=_f_slogan)
    sw   = bbox[2] - bbox[0]
    draw.text((WIDTH//2-sw//2, sloganY-14), 'WE BOTTLE MUSIC', font=_f_slogan, fill=blend(BG, GOLD, a))

def draw_grid(img, alpha):
    draw = ImageDraw.Draw(img)
    for row in range(nRows):
        for col in range(nCols):
            sx = sqStartX + col*(sqSize+sqGap)
            sy = sqStartY + (nRows-1-row)*rowH
            draw.rectangle([(sx,sy),(sx+sqSize-1,sy+sqSize-1)], fill=blend(BG, SQ_OFF, alpha))

def draw_countdown(img, num, alpha):
    draw = ImageDraw.Draw(img)
    for row in range(nRows):
        for col in range(nCols):
            sx   = sqStartX + col*(sqSize+sqGap)
            sy   = sqStartY + (nRows-1-row)*rowH
            isOn = is_digit_on(row, col, num)
            c    = blend(SQ_OFF, SQ_ON, alpha) if isOn else SQ_OFF
            draw.rectangle([(sx,sy),(sx+sqSize-1,sy+sqSize-1)], fill=c)

letters = ['V','Y','N','E']
spacing = 14
charW   = 22
logoW   = len(letters)*charW + (len(letters)-1)*spacing + 28
logoX   = WIDTH // 2 - logoW // 2

# Faze:
# 0-10:   spekter fade in
# 10-50:  spekter igra
# 50-65:  spekter fade out
# 65-80:  logo fade in
# 80-105: logo hold
# 105-120: logo fade out
# 120-135: grid fade in
# 135-175: "3"
# 175-215: "2"
# 215-255: "1"
# 255-285: collapse
# 285+:   konec

CD = [('3', 135, 175), ('2', 175, 215), ('1', 215, 255)]
COLLAPSE_S = 255
COLLAPSE_E = 285
TOTAL      = 285

def play_intro(device):
    """Boot-style intro: spekter → logo."""
    t = 0.0
    for f in range(121):
        img = new_canvas()
        if f < 65:
            a = f/10.0 if f<10 else 1.0 if f<50 else 1.0-(f-50)/15.0
            draw_spectrum(img, t, max(0, min(1, a)))
        if f >= 65:
            a = (f-65)/15.0 if f<80 else 1.0 if f<105 else 1.0-(f-105)/15.0
            draw_logo(img, max(0, min(1, a)))
        device.display(img)
        t += 0.24

def play_countdown(device):
    """Playing intro: spekter → logo → grid → 3,2,1 → collapse."""
    t = 0.0
    for f in range(TOTAL + 1):
        img = new_canvas()

        # spekter
        if f < 65:
            a = f/10.0 if f<10 else 1.0 if f<50 else 1.0-(f-50)/15.0
            draw_spectrum(img, t, max(0, min(1, a)))

        # logo
        if 65 <= f < 120:
            a = (f-65)/15.0 if f<80 else 1.0 if f<105 else 1.0-(f-105)/15.0
            draw_logo(img, max(0, min(1, a)))

        # grid fade in
        if 120 <= f < 135:
            draw_grid(img, (f-120)/15.0)

        # countdown
        for num, start, end in CD:
            if start <= f < end:
                dur = end - start
                nf  = f - start
                if nf < 8:        a = nf/8.0
                elif nf < dur-8:  a = 1.0
                else:             a = 1.0-(nf-(dur-8))/8.0
                draw_countdown(img, num, max(0, min(1, a)))
                if nf == 1:
                    play_sound(SOUND_TICK)

        # collapse
        if COLLAPSE_S <= f <= COLLAPSE_E:
            cp   = (f-COLLAPSE_S)/(COLLAPSE_E-COLLAPSE_S)
            draw = ImageDraw.Draw(img)
            for row in range(nRows):
                target = row if row < 3 else -1
                fromY  = sqStartY + (nRows-1-row)*rowH
                toY    = playStartY + (2-target)*rowH if target >= 0 else HEIGHT+20
                curY   = int(fromY + (toY-fromY)*cp)
                rowA   = 1.0 if target >= 0 else max(0.0, 1.0-cp*2)
                if rowA <= 0.01:
                    continue
                for col in range(nCols):
                    sx = sqStartX + col*(sqSize+sqGap)
                    c  = blend(BG, SQ_OFF, rowA)
                    draw.rectangle([(sx,curY),(sx+sqSize-1,curY+sqSize-1)], fill=c)

        device.display(img)
        t += 0.24

    play_sound(SOUND_START)
