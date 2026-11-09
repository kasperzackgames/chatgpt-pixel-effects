# The relight prompt (step 3)

For an image AI that edits an attached picture. Attach `out/lit/marked_x5.png` (your background enlarged x5 with an
orange spot where the blast hits, made by `scripts/make_marked_input.py`) and send this text with it:

```text
a relit copy of the attached pixel-art game background: exactly the same picture, same composition, same framing, same size and the same pixel grid, every shape, edge, rock and star in exactly the same place. Change only the lighting: a huge explosion is burning on the canyon floor at the orange spot (do not draw the explosion or the spot; at the spot there is just brightly lit ground). Its warm orange and yellow light falls on the canyon floor around the spot and on the cliff faces and rocks that face it, strongest close to the spot and falling off quickly with distance; rock faces turned toward the fire get warm orange highlights, faces turned away keep their cold blue shading. The night sky, the stars, the distant volcano, the far mountains and the mist far from the fire stay dark and blue, unchanged. True pixel art, crisp pixels on the same grid, no blur, no glow haze over the sky, no text.
```

- Any image model that edits an attached picture works. We used OpenAI's image model (the one ChatGPT uses),
  called through the Codex CLI; it returned 1672x941 for the 1600x900 input (`example/canyon_relit.png`).
- The result must show exactly the same framing as the input (same 16:9 shape, nothing cropped, padded or
  moved). `make_lit.py` scales it back to 320x180 and reports `best_shift`, which must be `[0, 0]`.
- For your own background, describe its parts instead of "canyon floor", "cliff faces", "volcano" and "far
  mountains", and keep the rule that the sky stays unchanged.
- Make two versions if you can and pick the one whose sky and mist look exactly like the background.
