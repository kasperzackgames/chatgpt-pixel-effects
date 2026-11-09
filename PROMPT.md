# The explosion prompt (step 1)

Paste this into ChatGPT as one message (you need a ChatGPT that can make animated GIFs). Save the GIF it returns.

```text
Make an animated GIF of a pixel-art explosion for a 2D side-view game, rendered as large as you can (at least 512x512). 16 frames, about 80 ms per frame. Use fine pixel art: each art pixel is only 2 to 3 image pixels wide, so the explosion has a lot of detail (about 120 art pixels tall at its peak). The camera does not move. The bottom edge of the frame is the ground line, and the explosion hits the ground at the bottom centre, at the same point in every frame. Don't draw the ground itself. Sequence: a tiny spark on the ground; one bright white flash frame; a huge orange and yellow fireball that grows until it fills about three quarters of the frame height and rises into a mushroom cloud with a fiery stem; debris chunks and sparks flying out in arcs; a thin dust ring rolling sideways along the ground; the fire breaks up into a light grey smoke column that rises and drifts; glowing embers fade out until the frame is empty. True pixel art: crisp pixels on one even grid, hard edges, no anti-aliasing, no blur, no soft gradients, a limited palette of about 20 colours (white, yellows, oranges, reds, dark reds and four neutral greys for the smoke). Background: flat solid pure magenta #FF00FF in every frame, nothing else. No text, no borders.
```

- ChatGPT ignores the size request: expect about 300x300 pixels (the example `example/explosion.gif` is 316x301, 16 frames, 80 ms each).
- Results vary from one generation to the next. Re-roll when the explosion is small, cut off at an edge, or drawn with big coarse pixels.
- Keep the magenta background: the cleanup removes it. For violet or purple effects (lightning, magic), ask for "flat solid pure green #00FF00" instead and clean with `--key green`.
