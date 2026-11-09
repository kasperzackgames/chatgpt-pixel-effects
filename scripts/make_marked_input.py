"""Input picture for the relight prompt: the background enlarged x5 (nearest) with a solid orange spot
where the blast touches the ground, so the image AI knows where the fire is.

usage: python scripts/make_marked_input.py BG.png X Y OUT.png
X, Y = the spot in game pixels (for the example canyon: 196 154, 5 px above the ground point 196 159).
"""
import os
import sys

from PIL import Image, ImageDraw

bg, x, y, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
im = Image.open(bg).convert("RGB")
big = im.resize((im.width * 5, im.height * 5), Image.Resampling.NEAREST)
d = ImageDraw.Draw(big)
cx, cy = x * 5 + 2, y * 5 + 2
d.ellipse([cx - 28, cy - 28, cx + 28, cy + 28], fill=(255, 140, 0))
big.save(out)
print(out, big.size)
