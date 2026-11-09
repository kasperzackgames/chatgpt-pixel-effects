extends Node2D
## One ground explosion, spawned by main.gd. Everything is a function of `t` (seconds since the
## trigger) and a seed, so the same seed always draws the same pixels (needed for a seamless loop).
## Each coded layer can be switched on or off (`layers`, main.gd's --layers) because the ChatGPT GIF
## already draws its own spark, dust ring, debris and embers; flash, shake, debris and scorch start
## on the sheet's impact frame (impact_time).
## Layers, back to front:
##   back:   scorch mark (stays), hot pixels in the scorch, rocks and sparks on gravity arcs
##   sheet:  the cleaned sprite sheet (AnimatedSprite2D, frame picked from t); the last played frame
##           (the smoke column, main.gd's --hold-from) is held for HOLD_TIME, drifts up and right in
##           whole pixels and erodes from the ground up (shaders/dissolve.gdshader)
##   front:  flat ground shock streak, low dust skirt, embers; the spark before the first frame
## All code layers draw whole pixels in colours taken from the sheet's palette.
## (A 3-tone coded smoke column is kept for comparison: at phone size it read as grey balls, so the
## smoke comes from the sheet; set USE_CODE_SMOKE to true to see it.)
const USE_CODE_SMOKE := false
const HOLD_TIME := 1.8

const BAYER := [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5]

var t := 0.0
var seed_value := 1
var anchor := Vector2i(160, 150)          # ground contact
var frames: SpriteFrames
var durations: Array = []                # seconds per sheet frame
var energy: Array = []                   # fire light per sheet frame (0..1)
var pal := {}                            # role -> Color
var anticipation := 2 * (1.0 / 12.0)     # code spark before the first sheet frame (0 if layer off)
var hold_time := HOLD_TIME               # last played frame: hold, rise, erode
var ai_end := 0.0
var impact_time := 0.0                   # flash, shake, debris, ring and scorch start here
var layers := {"spark": true, "streak": true, "dust": true, "rocks": true, "sparks": true, "scorch": true, "embers": true}

var rocks: Array = []
var sparks: Array = []
var embers: Array = []
var puffs: Array = []
var dust: Array = []
var scorch_hot: Array = []
var sprite: AnimatedSprite2D
var back: Node2D
var front: Node2D
var dissolve_mat: ShaderMaterial


func setup(p_frames: SpriteFrames, p_durations: Array, p_energy: Array, p_pal: Dictionary, p_anchor: Vector2i,
		p_origin: Vector2, p_seed: int, p_layers: Dictionary = {}, p_impact: int = 0) -> void:
	frames = p_frames
	durations = p_durations
	energy = p_energy
	pal = p_pal
	anchor = p_anchor
	seed_value = p_seed
	for k in p_layers:
		layers[k] = p_layers[k]
	if not layers["spark"]:
		anticipation = 0.0
	ai_end = anticipation
	for d in durations:
		ai_end += d
	impact_time = anticipation
	for i in p_impact:
		impact_time += durations[i]
	back = Node2D.new()
	back.draw.connect(_draw_back)
	add_child(back)
	sprite = AnimatedSprite2D.new()
	sprite.sprite_frames = frames
	sprite.animation = "explode"
	sprite.centered = false
	sprite.position = Vector2(anchor) - p_origin
	sprite.visible = false
	dissolve_mat = ShaderMaterial.new()
	dissolve_mat.shader = load("res://shaders/dissolve.gdshader")
	sprite.material = dissolve_mat
	add_child(sprite)
	front = Node2D.new()
	front.draw.connect(_draw_front)
	add_child(front)
	_make_particles()


func flash_time() -> float:
	return impact_time


func alive() -> bool:
	return t < ai_end + 3.6


# ------------------------------------------------------------------ set-up (seeded)
func _make_particles() -> void:
	var r := RandomNumberGenerator.new()
	r.seed = seed_value
	var G := float(anchor.y)
	var X := float(anchor.x)
	for i in 10:
		var ang := -PI / 2 + r.randf_range(-1.25, 1.25)
		var spd := r.randf_range(85.0, 155.0)
		rocks.append(_debris(r, X + r.randf_range(-10, 10), G - r.randf_range(4, 22), ang, spd, 320.0,
			r.randf_range(1.6, 2.4), 2 if r.randf() < 0.5 else 3))
	for i in 24:
		var ang := -PI / 2 + r.randf_range(-1.4, 1.4)
		var spd := r.randf_range(130.0, 235.0)
		sparks.append(_debris(r, X + r.randf_range(-12, 12), G - r.randf_range(6, 45), ang, spd, 300.0,
			r.randf_range(0.45, 1.0), 2 if r.randf() < 0.25 else 1))
	for i in 28:
		embers.append({"t0": r.randf_range(0.15, 0.95), "life": r.randf_range(1.1, 2.6),
			"x": X + r.randf_range(-38, 38), "y": G - r.randf_range(8, 85),
			"rise": r.randf_range(14, 34), "drift": r.randf_range(-6, 10), "ph": r.randf() * TAU})
	for i in 18:
		var cap := i % 3 != 2
		var t0 := 0.42 + i * 0.045 + r.randf_range(0.0, 0.04)
		puffs.append({"t0": t0, "life": r.randf_range(1.7, 2.5),
			"x": X + (r.randf_range(-32, 32) if cap else r.randf_range(-9, 9)),
			"y": G - (r.randf_range(58, 86) if cap else r.randf_range(14, 52)),
			"r": r.randf_range(9, 16) if cap else r.randf_range(7, 11),
			"vy": -r.randf_range(9, 19), "vx": r.randf_range(3, 9), "grow": r.randf_range(0.4, 0.7)})
	puffs.sort_custom(func(a, b): return a["t0"] < b["t0"])
	for i in 10:
		var side := 1.0 if i % 2 == 0 else -1.0
		dust.append({"side": side, "x0": r.randf_range(6, 16), "reach": r.randf_range(42, 92),
			"r": r.randf_range(4, 8), "life": r.randf_range(0.8, 1.3), "rise": r.randf_range(1, 5)})
	for i in 12:
		scorch_hot.append({"x": X + r.randf_range(-26, 26), "y": G + r.randi_range(-1, 2), "life": r.randf_range(0.8, 2.0),
			"ph": r.randi_range(0, 7)})


func _debris(r: RandomNumberGenerator, x0: float, y0: float, ang: float, spd: float, g: float, life: float, size: int) -> Dictionary:
	var vx := cos(ang) * spd
	var vy := sin(ang) * spd
	var G := float(anchor.y)
	var disc := vy * vy + 2.0 * g * (G - y0)
	var t_hit := (-vy + sqrt(disc)) / g if disc >= 0.0 else INF
	return {"x0": x0, "y0": y0, "vx": vx, "vy": vy, "g": g, "life": life, "size": size, "t_hit": t_hit,
		"id": r.randi_range(0, 1000)}


# ------------------------------------------------------------------ per frame
func advance(dt: float) -> void:
	t += dt
	var ta := t - anticipation
	if t >= anticipation and t < ai_end + hold_time:
		sprite.visible = true
		var f := _ai_frame(ta)
		sprite.frame = f
		var k := 0.0
		if t >= ai_end:
			k = (t - ai_end) / hold_time
		var base := Vector2(anchor) - _origin_offset()
		# hold: rise ~22 px (slowing), drift ~10 px right with the wind, whole pixels only
		sprite.position = base + Vector2(roundf(10.0 * k), -roundf(22.0 * (1.0 - (1.0 - k) * (1.0 - k))))
		var reg: Rect2 = (frames.get_frame_texture("explode", f) as AtlasTexture).region
		dissolve_mat.set_shader_parameter("region", Vector4(reg.position.x, reg.position.y, reg.size.x, reg.size.y))
		dissolve_mat.set_shader_parameter("amount", 2.4 * pow(k, 1.8))  # nothing left by about 90 % of the hold
	else:
		sprite.visible = false
	back.queue_redraw()
	front.queue_redraw()


var _origin := Vector2.ZERO


func set_origin(o: Vector2) -> void:
	_origin = o


func _origin_offset() -> Vector2:
	return _origin


func _ai_frame(ta: float) -> int:
	var acc := 0.0
	for i in durations.size():
		acc += durations[i]
		if ta < acc:
			return i
	return durations.size() - 1


## warm light this blast throws on the scene right now (0..1, >1 on the flash frame)
func light() -> float:
	if t < anticipation:
		return 0.15 + 0.2 * floor(t * 12.0)
	var ta := t - anticipation
	if t < ai_end:
		return energy[_ai_frame(ta)]
	var k := (t - ai_end) / 1.2
	return maxf(0.0, energy[energy.size() - 1] * (1.0 - k))


## whole-pixel shake offset of this blast (deterministic)
func shake() -> Vector2:
	var ts := t - impact_time
	if ts < 0.0 or ts > 0.45:
		return Vector2.ZERO
	var amp := 4.0 * (1.0 - ts / 0.45)
	var n := int(ts * 60.0)
	var hx := _hash(n * 2 + seed_value * 131) - 0.5
	var hy := _hash(n * 2 + 1 + seed_value * 131) - 0.5
	return Vector2(round(hx * 2.0 * amp), round(hy * 2.0 * amp))


func flash_strength() -> float:
	var ts := t - impact_time
	if ts < 0.0 or ts >= 0.1:
		return 0.0
	return 1.0 - ts / 0.1


func _hash(n: int) -> float:
	var h := (n * 374761393 + 668265263) & 0x7fffffff
	h = ((h ^ (h >> 13)) * 1274126177) & 0x7fffffff
	return float(h & 0xffff) / 65535.0


func _bayer(x: int, y: int) -> float:
	return (BAYER[(x & 3) + (y & 3) * 4] + 0.5) / 16.0


func _px(ci: CanvasItem, x: float, y: float, c: Color, w := 1, h := 1) -> void:
	ci.draw_rect(Rect2(round(x), round(y), w, h), c)


func _disc(ci: CanvasItem, x: float, y: float, r: float, c: Color) -> void:
	# pixel disc from row spans (crisp, no anti-aliasing at any scale)
	var cx := roundf(x)
	var cy := roundf(y)
	var rr := maxf(0.5, r)
	var ri := int(ceil(rr))
	for dy in range(-ri, ri + 1):
		var half := sqrt(maxf(0.0, rr * rr - float(dy * dy)))
		var w := int(round(half))
		if half < 0.5:
			continue
		ci.draw_rect(Rect2(cx - w, cy + dy, 2 * w + 1, 1), c)


# ------------------------------------------------------------------ back layer
func _draw_back() -> void:
	var ts := t - impact_time
	if ts >= 0.0:
		if layers["scorch"]:
			_draw_scorch(back, ts)
		if layers["rocks"]:
			_draw_rocks(back, ts)
		if layers["sparks"]:
			_draw_debris(back, ts)  # sparks behind too: in front of the fire they read as dirt specks
	if USE_CODE_SMOKE:
		_draw_smoke(back)


func _draw_scorch(ci: CanvasItem, ts: float) -> void:
	var X := float(anchor.x)
	var G := float(anchor.y)
	var grow := minf(1.0, ts / 0.12)
	var rx := 38.0 * (0.4 + 0.6 * grow)
	var ry := 3.5
	for dy in range(-3, 5):
		for dx in range(-int(rx) - 1, int(rx) + 2):
			var nx := dx / rx
			var ny := (dy - 0.5) / ry
			var d := sqrt(nx * nx + ny * ny)
			if d >= 1.0:
				continue
			var xx := int(X) + dx
			var yy := int(G) + dy
			if d > 0.6 and _bayer(xx, yy) > (1.0 - d) / 0.4:
				continue
			ci.draw_rect(Rect2(xx, yy, 1, 1), pal["scorch"] if d < 0.8 else pal["smoke_dark"])
	# hot pixels glowing in the scorch
	var step := int(ts * 12.0)
	for h in scorch_hot:
		if ts > h["life"]:
			continue
		var k: float = ts / h["life"]
		if k > 0.6 and (step + h["ph"]) % 2 == 1:
			continue
		var c: Color = pal["yellow"] if k < 0.25 else (pal["orange"] if k < 0.6 else pal["red"])
		ci.draw_rect(Rect2(h["x"], h["y"], 1, 1), c)


func _puff_state(p: Dictionary) -> Dictionary:
	var lt: float = t - impact_time - p["t0"]
	if lt < 0.0 or lt >= p["life"]:
		return {}
	var lu: float = lt / p["life"]
	var s := 1.0 - pow(1.0 - minf(1.0, lu / 0.18), 2.0)
	var r: float = p["r"] * (0.55 + 0.45 * s) * (1.0 + p["grow"] * lu)
	if lu > 0.62:
		var e := (lu - 0.62) / 0.38
		r *= 1.0 - e * e
	var x: float = p["x"] + p["vx"] * lt * (0.6 + 0.4 * lu)
	var y: float = p["y"] + p["vy"] * lt * (1.0 - 0.25 * lu)
	return {"x": x, "y": y, "r": r, "lu": lu}


func _draw_smoke(ci: CanvasItem) -> void:
	var states := []
	for p in puffs:
		var st := _puff_state(p)
		if not st.is_empty() and st["r"] >= 1.0:
			states.append(st)
	if states.is_empty():
		return
	var glow := clampf(light() * 1.4, 0.0, 1.0)
	for st in states:  # one dark outline around the whole column
		_disc(ci, st["x"], st["y"], st["r"] + 1.0, pal["outline"])
	for st in states:
		_disc(ci, st["x"], st["y"], st["r"], pal["smoke_dark"])
	if glow > 0.05:  # underside lit by the fire
		for st in states:
			var gr: float = st["r"] * 0.55 * glow
			if gr >= 1.0:
				_disc(ci, st["x"], st["y"] + st["r"] * 0.42, gr, pal["dark_red"] if glow < 0.6 else pal["red"])
	for st in states:
		var r: float = st["r"]
		_disc(ci, st["x"] - r * 0.18, st["y"] - r * 0.24, r * 0.72, pal["smoke_mid"])
	for st in states:
		var r: float = st["r"]
		if r * 0.38 >= 1.0:
			_disc(ci, st["x"] - r * 0.34, st["y"] - r * 0.42, r * 0.38, pal["smoke_light"])


# ------------------------------------------------------------------ front layer
func _draw_front() -> void:
	var ts := t - impact_time
	if ts < 0.0:
		if layers["spark"] and t < anticipation:
			_draw_anticipation(front)
		return
	if layers["streak"]:
		_draw_ring(front, ts)
	if layers["dust"]:
		_draw_dust(front, ts)
	if layers["embers"]:
		_draw_embers(front, ts)


func _draw_anticipation(ci: CanvasItem) -> void:
	var n := int(t * 12.0)
	var X := float(anchor.x)
	var Y := float(anchor.y) - 2.0
	var L := 2 + n * 3
	_px(ci, X - 1, Y - 1, pal["white"], 3, 3)
	for i in range(2, L + 1):
		var c: Color = pal["yellow"] if i < L - 1 else pal["orange"]
		_px(ci, X + i, Y, c)
		_px(ci, X - i, Y, c)
		_px(ci, X, Y - i, c)


func _draw_ring(ci: CanvasItem, ts: float) -> void:
	# ground shock: a flat, broken streak racing out along the ground both ways (not a hoop)
	var k := ts / 0.3
	if k >= 1.0:
		return
	var e := 1.0 - pow(1.0 - k, 3.0)
	var rx := 14.0 + 110.0 * e
	var dens := 1.0 - k
	var X := float(anchor.x)
	var G := float(anchor.y)
	var c: Color = pal["white"] if k < 0.25 else (pal["yellow"] if k < 0.55 else pal["orange"])
	for side in [-1.0, 1.0]:
		var L := int(6.0 + 26.0 * (1.0 - k))  # streak length behind the front
		for i in L:
			var x := roundf(X + side * (rx - i))
			var y := G - (1.0 if i < L / 3 else 0.0)
			var fall := float(i) / L
			if _hash(int(x) * 7 + seed_value) > dens + 0.35 - fall * 0.5:
				continue
			ci.draw_rect(Rect2(x, y, 1, 1), c if fall < 0.5 else pal["red"])


func _ellipse(ci: CanvasItem, x: float, y: float, rx: float, ry: float, c: Color, dens: float,
		top_c: Color = Color(0, 0, 0, 0)) -> void:
	# lumpy flat ellipse: the rim is broken up by a per-pixel hash, so it never reads as a slab;
	# top_c (if set) colours the upper rim (the side the fire lights)
	var cx := roundf(x)
	var cy := roundf(y)
	var ryi := int(ceil(ry))
	for dy in range(-ryi, ryi + 1):
		var fy := float(dy) / maxf(0.5, ry)
		if absf(fy) > 1.0:
			continue
		var half := int(round(rx * sqrt(1.0 - fy * fy)))
		for dx in range(-half, half + 1):
			var xx := int(cx) + dx
			var yy := int(cy) + dy
			var fx := float(dx) / maxf(1.0, rx)
			var d := sqrt(fx * fx + fy * fy)
			if d > 0.55 and _hash(xx * 31 + yy * 17 + seed_value) > (1.0 - d) / 0.45 + 0.15:
				continue
			if dens < 1.0 and _bayer(xx, yy) > dens:
				continue
			var cc := c
			if top_c.a > 0.0 and fy < -0.35:
				cc = top_c
			ci.draw_rect(Rect2(xx, yy, 1, 1), cc)


func _draw_dust(ci: CanvasItem, ts: float) -> void:
	# low dust skirt: flat ellipses sliding out along the ground, two tones, eroding by Bayer dither
	var X := float(anchor.x)
	var G := float(anchor.y)
	for pass_i in 2:
		for d in dust:
			var k: float = ts / (d["life"] * 1.4)
			if k >= 1.0:
				continue
			var e := 1.0 - pow(1.0 - k, 2.5)
			var r: float = d["r"] * (0.7 + 0.9 * e)
			var x: float = X + d["side"] * (d["x0"] + d["reach"] * e)
			var dens := 1.0 if k < 0.45 else 1.0 - (k - 0.45) / 0.55
			var lit := light()
			var top: Color = pal["red"] if lit > 0.55 else (pal["dark_red"] if lit > 0.2 else Color(0, 0, 0, 0))
			if pass_i == 0:
				_ellipse(ci, x, G - r * 0.3, r * 1.7, r * 0.45, pal["outline"], dens, top)
			else:
				_ellipse(ci, x - d["side"] * r * 0.3, G - r * 0.4, r * 1.0, r * 0.25, pal["smoke_dark"], dens)


func _debris_at(d: Dictionary, tt: float) -> Vector2:
	var G := float(anchor.y)
	if tt <= d["t_hit"]:
		return Vector2(d["x0"] + d["vx"] * tt, minf(G, d["y0"] + d["vy"] * tt + 0.5 * d["g"] * tt * tt))
	var xh: float = d["x0"] + d["vx"] * d["t_hit"]
	var vb: float = -absf(d["vy"] + d["g"] * d["t_hit"]) * 0.3
	var tb: float = tt - d["t_hit"]
	var t2: float = -2.0 * vb / d["g"]
	var tm := minf(tb, t2)
	return Vector2(xh + d["vx"] * 0.4 * tm, minf(G, G + vb * tm + 0.5 * d["g"] * tm * tm))


func _draw_rocks(ci: CanvasItem, ts: float) -> void:
	# drawn BEHIND the sheet sprite: rocks inside the fireball are hidden and appear as they fly out
	# (in front they read as dark holes in the fire)
	var step := int(ts * 12.0)
	for d in rocks:
		if ts >= d["life"]:
			continue
		var k: float = ts / d["life"]
		if k > 0.8 and (step + d["id"]) % 2 == 1:
			continue
		var p := _debris_at(d, ts)
		var s: int = d["size"]
		_px(ci, p.x, p.y - s + 1, pal["outline"], s, s)
		if s == 3:
			_px(ci, p.x, p.y - 1, pal["smoke_dark"], 2, 2)
		if ts < 0.6:
			_px(ci, p.x, p.y - s + 1, pal["orange"] if ts < 0.3 else pal["red"])


func _draw_debris(ci: CanvasItem, ts: float) -> void:
	var step := int(ts * 12.0)
	for d in sparks:
		if ts >= d["life"]:
			continue
		var k: float = ts / d["life"]
		if k > 0.65 and (step + d["id"]) % 2 == 1:
			continue
		var p := _debris_at(d, ts)
		var c: Color = pal["white"] if k < 0.2 else (pal["yellow"] if k < 0.45 else (pal["orange"] if k < 0.75 else pal["red"]))
		var q := _debris_at(d, maxf(0.0, ts - 0.035))
		if (p - q).length() >= 2.0:  # 1-px trail, one colour cooler
			var tc: Color = pal["yellow"] if k < 0.2 else (pal["orange"] if k < 0.45 else pal["dark_red"])
			var n := int((p - q).length())
			for i in n:
				var m := q.lerp(p, float(i) / n)
				_px(ci, m.x, m.y, tc)
		var sz: int = d["size"]
		_px(ci, p.x, p.y - sz + 1, c, sz, sz)


func _draw_embers(ci: CanvasItem, ts: float) -> void:
	var step := int(ts * 12.0)
	var i := 0
	for e in embers:
		i += 1
		var lt: float = ts - e["t0"]
		if lt < 0.0 or lt >= e["life"]:
			continue
		var k: float = lt / e["life"]
		if k > 0.65 and (step + i) % 2 == 1:
			continue
		var x: float = e["x"] + e["drift"] * lt + 5.0 * lt * lt + sin(lt * 5.0 + e["ph"]) * 1.5
		var y: float = e["y"] - e["rise"] * lt * (1.0 - 0.3 * k)
		var c: Color = pal["yellow"] if k < 0.25 else (pal["orange"] if k < 0.55 else (pal["red"] if k < 0.8 else pal["dark_red"]))
		_px(ci, x, y, c)
