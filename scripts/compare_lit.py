"""Side-by-side to pick a lit background: the plain background and each lit candidate, whole at x2
(top row) and the lit area at x4 (bottom row: game x 110..320, y 70..180 of the example canyon, the
floor, the cliffs and the mist next to them, where flaws show). Labels on top.

usage: python scripts/compare_lit.py BG.png LIT1.png [LIT2.png ...] --out PICK.png
"""
import os
import sys

from PIL import Image, ImageDraw

args = [x for x in sys.argv[1:] if x != "--out"]
out = sys.argv[sys.argv.index("--out") + 1]
files = [f for f in args if f != out]
ims = [Image.open(f).convert("RGB") for f in files]
W, H = ims[0].size
crop = (110, 70, 320, 180)
cw, ch = (crop[2] - crop[0]) * 4, (crop[3] - crop[1]) * 4
colw = max(W * 2, cw)
sheet = Image.new("RGB", (len(ims) * (colw + 8) + 8, 20 + H * 2 + 8 + ch + 8), (30, 30, 36))
d = ImageDraw.Draw(sheet)
for i, (f, im) in enumerate(zip(files, ims)):
    x = 8 + i * (colw + 8)
    d.text((x, 4), ("background: " if i == 0 else "candidate: ") + os.path.basename(f), fill=(230, 230, 230))
    sheet.paste(im.resize((W * 2, H * 2), Image.Resampling.NEAREST), (x, 20))
    sheet.paste(im.crop(crop).resize((cw, ch), Image.Resampling.NEAREST), (x, 20 + H * 2 + 8))
os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
sheet.save(out)
print(out, sheet.size)
