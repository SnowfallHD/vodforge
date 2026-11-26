"""Place a captured app window on a desktop wallpaper, like a desktop screenshot.

    compose.py WALLPAPER WINDOW OUT [--shadow] [--width 2400]

WINDOW is a PNG of just the window. macOS captures keep their own transparent
shadow; --shadow adds a soft one for captures that have none (Windows).
"""

import argparse

from PIL import Image, ImageFilter, ImageOps

p = argparse.ArgumentParser()
p.add_argument("wallpaper")
p.add_argument("window")
p.add_argument("out")
p.add_argument("--shadow", action="store_true")
p.add_argument("--width", type=int, default=2400)
p.add_argument("--margin", type=float, default=0.085)
a = p.parse_args()

win = Image.open(a.window).convert("RGBA")
w, h = win.size
mx = int(w * a.margin)
my = int(w * a.margin * 0.75)
cw, ch = w + 2 * mx, h + 2 * my
canvas = ImageOps.fit(
    Image.open(a.wallpaper).convert("RGB"), (cw, ch), Image.Resampling.LANCZOS
).convert("RGBA")
if a.shadow:
    blur = max(8, w // 90)
    shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    box = Image.new("RGBA", (w, h), (0, 0, 0, 110))
    shadow.paste(box, (mx, my + blur // 3), box)
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    canvas = Image.alpha_composite(canvas, shadow)
canvas.alpha_composite(win, (mx, my))
out = canvas.convert("RGB")
if out.width > a.width:
    out = out.resize(
        (a.width, round(out.height * a.width / out.width)), Image.Resampling.LANCZOS
    )
out.save(a.out, quality=90, optimize=True, progressive=True)
print(a.out, out.size)
