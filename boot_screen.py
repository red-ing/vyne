# ============================================================
# VYNE+ boot_screen.py — nov dizajn
# ============================================================
import RPi.GPIO as GPIO

BL_PIN = 12
GPIO.setmode(GPIO.BCM)
GPIO.setup(BL_PIN, GPIO.OUT)
GPIO.output(BL_PIN, GPIO.LOW)

from luma.lcd.device import ili9341
from luma.core.interface.serial import spi
from PIL import Image, ImageDraw, ImageFont
import time
import math

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

serial = spi(port=0, device=0, gpio_DC=24, gpio_RST=25)
device = ili9341(serial, width=320, height=240)

sqSize   = 6
sqGap    = 3
nCols    = 280 // (sqSize + sqGap)
nRows    = 13
rowH     = sqSize + 2
sqStartX = 20
sqStartY = HEIGHT // 2 - (nRows * rowH) // 2

f_logo   = ImageFont.truetype(FONT_LIGHT, 52)
f_slogan = ImageFont.truetype(FONT_ITALIC, 14)

blockH  = nRows * rowH
logoH   = 46
cStartY = sqStartY + (blockH - (logoH + 10 + 1 + 10 + 14)) // 2
logoY   = cStartY + logoH
lineY   = logoY + 10
sloganY = lineY + 10 + 14

letters = ['V','Y','N','E']
spacing = 14
charW   = 22
logoW   = len(letters)*charW + (len(letters)-1)*spacing + 28
logoX   = WIDTH // 2 - logoW // 2

def blend(c1, c2, a):
    return tuple(int(c1[i] + (c2[i]-c1[i])*a) for i in range(3))

def new_canvas():
    return Image.new('RGB', (WIDTH, HEIGHT), BG)

def draw_spectrum(img, t, alpha):
    draw = ImageDraw.Draw(img)
    for col in range(nCols):
        freq   = col / nCols
        bass   = (1 - freq) ** 1.5
        wave   = math.sin(t * 2.5 - col * 0.4) * 0.4
        amp    = max(0, min(1, bass * 0.6 + wave + 0.2))
        active = round(amp * nRows)
        for row in range(nRows):
            sx   = sqStartX + col * (sqSize + sqGap)
            sy   = sqStartY + (nRows - 1 - row) * rowH
            base = SQ_ON if row < active else SQ_OFF
            draw.rectangle([(sx,sy),(sx+sqSize-1,sy+sqSize-1)], fill=blend(BG, base, alpha))

def draw_logo(img, a):
    draw = ImageDraw.Draw(img)
    x = logoX
    for l in letters:
        draw.text((x, logoY-logoH), l, font=f_logo, fill=blend(BG, VYNE_C, a))
        x += charW + spacing
    draw.text((x, logoY-logoH), '+', font=f_logo, fill=blend(BG, PLUS_C, a))
    draw.line([(60,lineY),(260,lineY)], fill=blend(BG, LINE_C, a), width=1)
    bbox = draw.textbbox((0,0), 'WE BOTTLE MUSIC', font=f_slogan)
    sw   = bbox[2] - bbox[0]
    draw.text((WIDTH//2-sw//2, sloganY-14), 'WE BOTTLE MUSIC', font=f_slogan, fill=blend(BG, GOLD, a))

# Faze (skrajšane):
# 0-10:  spekter fade in
# 10-50: spekter igra
# 50-65: spekter fade out
# 65-80: logo fade in
# 80-105: logo hold
# 105-120: logo fade out

t = 0.0
for f in range(121):
    img = new_canvas()

    if f < 65:
        if f < 10:    a = f / 10.0
        elif f < 50:  a = 1.0
        else:         a = 1.0 - (f-50)/15.0
        draw_spectrum(img, t, max(0, min(1, a)))

    if 65 <= f:
        if f < 80:    a = (f-65)/15.0
        elif f < 105: a = 1.0
        else:         a = 1.0 - (f-105)/15.0
        draw_logo(img, max(0, min(1, a)))

    device.display(img)
    t += 0.24

GPIO.output(BL_PIN, GPIO.HIGH)
GPIO.cleanup()
