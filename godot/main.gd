extends Node2D
## Pixel art explosion demo: the cleaned sprite sheet (one art pixel = one game pixel) over a 320x180
## background, with a 40% flash on the sheet's impact frame, whole-pixel screen shake, coded rocks,
## scorch and embers (blast.gd), the fullest smoke frame held and eroded, and the background blended
## toward its lit copy by the fire's brightness (shaders/light_painted.gdshader).
## Run:  godot --path <this folder> -- [options]      (or open project.godot in the editor and press F5)
## Options (after the --; paths may be res://... or absolute):
##   --sheet=PATH.png [--json=PATH.json]    the sprite sheet from clean_gif.py (default res://sprites/explosion_sheet.png,
##                                          json = the same name with .json)
##   --bg=PATH.png                          background, 320x180 (default res://backgrounds/canyon.png)
##   --lit=PATH.png                         lit copy of the background from make_lit.py (default
##                                          res://backgrounds/canyon_lit.png); none = a simple shader light instead
##                                          (shaders/light_simple.gdshader; it also lights the sky)
##   --x=196 --ground=159                   where the blast touches the ground, in game pixels
##   --flash=0.4                            full-screen flash strength on the impact frame, 0 = off (also key F)
##   --shake=1.0                            whole-pixel screen shake strength, 0 = off
##   --hold-from=12                         this frame (the fullest smoke) is held 1.8 s, rises, drifts right and
##                                          erodes from the ground up; later frames are not played
##   --layers=rocks,scorch,embers           coded layers on, comma-separated; all: spark, streak, dust, rocks,
##                                          sparks, scorch, embers; --layers= (empty) = none
##   --light-y=15                           centre of the light mask, this many px above the ground
##   --volcano=1.0                          faint warm glow on the example canyon's volcano top at (122, 62);
##                                          0 for any other background
##   --first=0.4 --interval=2.6             seconds before the first blast, then between the end of one blast's
##                                          sprite and the next (auto loop)
##   --loop-period=1.0                      seamless mode: one blast every N s, all with the same seed (default off)
## Keys: Space/Enter/click = explode now, L = auto loop on/off, F = flash 100% / 40% / off.

const BlastScript := preload("res://blast.gd")
const DEFAULT_SHEET := "res://sprites/explosion_sheet.png"
const DEFAULT_LAYERS := "rocks,scorch,embers"
const DEFAULT_BG := "res://backgrounds/canyon.png"
const DEFAULT_LIT := "res://backgrounds/canyon_lit.png"
const VOLCANO_TOP := Vector2(122, 62)
const ROLE_TARGETS := {
	"white": Color8(253, 253, 249), "yellow": Color8(252, 242, 44), "orange": Color8(251, 124, 4),
	"red": Color8(233, 42, 3), "dark_red": Color8(145, 24, 21), "smoke_light": Color8(184, 182, 181),
	"smoke_mid": Color8(108, 103, 101), "smoke_dark": Color8(71, 63, 63), "outline": Color8(38, 35, 35),
	"scorch": Color8(30, 22, 22),
}

var args := {}
var bg: Sprite2D
var light_mat: ShaderMaterial
var cam: Camera2D
var flash_rect: ColorRect
var frames: SpriteFrames
var durations: Array = []
var energy: Array = []
var pal := {}
var origin := Vector2.ZERO
var ground := Vector2i(196, 159)
var flash_setting := 1.0
var shake_setting := 1.0
var auto_loop := true
var interval := 2.6
var wait := 0.4
var loop_period := 0.0
var clock := 0.0
var next_loop := 0.0
var count := 0
var blasts: Array = []
var impact := 0
var layer_on := {}


func _ready() -> void:
	for a in OS.get_cmdline_user_args():
		var s := String(a)
		if s.begins_with("--"):
			var kv := s.substr(2).split("=", true, 1)
			args[kv[0]] = kv[1] if kv.size() > 1 else "1"
	ground = Vector2i(int(args.get("x", "196")), int(args.get("ground", "159")))
	flash_setting = float(args.get("flash", "0.4"))
	var on: PackedStringArray = String(args.get("layers", DEFAULT_LAYERS)).split(",")
	for k in ["spark", "streak", "dust", "rocks", "sparks", "scorch", "embers"]:
		layer_on[k] = on.has(k)
	shake_setting = float(args.get("shake", "1.0"))
	interval = float(args.get("interval", "2.6"))
	wait = float(args.get("first", "0.4"))
	loop_period = float(args.get("loop-period", "0"))
	next_loop = wait

	cam = Camera2D.new()
	cam.position = Vector2(160, 90)
	add_child(cam)
	cam.make_current()

	bg = Sprite2D.new()
	bg.centered = false
	var img := Image.load_from_file(_abs(args.get("bg", DEFAULT_BG)))
	bg.texture = ImageTexture.create_from_image(img)
	light_mat = ShaderMaterial.new()
	# painted light (default): blend toward a lit copy of the background (--lit=PATH.png, same size).
	# --lit=none (or a missing file) falls back to the simple shader light (a warm ellipse in hard bands).
	var lit_path: String = args.get("lit", DEFAULT_LIT)
	if lit_path != "none" and FileAccess.file_exists(_abs(lit_path)):
		light_mat.shader = load("res://shaders/light_painted.gdshader")
		light_mat.set_shader_parameter("lit_tex", ImageTexture.create_from_image(Image.load_from_file(_abs(lit_path))))
		print("light: painted light from ", lit_path)
	else:
		light_mat.shader = load("res://shaders/light_simple.gdshader")
		print("light: simple shader light (no lit background)")
	var vol := float(args.get("volcano", "1.0"))
	light_mat.set_shader_parameter("glow2_pos", VOLCANO_TOP if vol > 0.0 else Vector2(-100, -100))
	light_mat.set_shader_parameter("glow2_amount", 0.55 * vol)
	bg.material = light_mat
	add_child(bg)
	RenderingServer.set_default_clear_color(img.get_pixel(0, img.get_height() - 1))

	var layer := CanvasLayer.new()
	layer.layer = 10
	add_child(layer)
	flash_rect = ColorRect.new()
	flash_rect.color = Color(0.35, 0.28, 0.17, 0.0)
	flash_rect.size = Vector2(320, 180)
	flash_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var fm := CanvasItemMaterial.new()
	fm.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
	flash_rect.material = fm
	layer.add_child(flash_rect)

	var sheet: String = args.get("sheet", DEFAULT_SHEET)
	_load_sheet(sheet, args.get("json", sheet.get_basename() + ".json"))
	print("explosion: sheet ", sheet, "  frames ", durations.size(), "  ground ", ground, "  flash ", flash_setting,
		"  loop period ", loop_period)


func _abs(p: String) -> String:
	return ProjectSettings.globalize_path(p) if p.begins_with("res://") else p


func _load_sheet(sheet_path: String, json_path: String) -> void:
	var img := Image.load_from_file(_abs(sheet_path))
	var tex := ImageTexture.create_from_image(img)
	var data = JSON.parse_string(FileAccess.get_file_as_string(_abs(json_path)))
	var list: Array = data["frames"].values() if data["frames"] is Dictionary else data["frames"]
	var meta: Dictionary = data.get("meta", {})
	var anc = meta.get("anchor", meta.get("pivot", {"x": 0, "y": 0}))
	origin = Vector2(float(anc["x"]), float(anc["y"]))
	frames = SpriteFrames.new()
	frames.add_animation("explode")
	frames.set_animation_loop("explode", false)
	var raw_energy: Array = []
	for f in list:
		var r = f["frame"]
		var rect := Rect2i(int(r["x"]), int(r["y"]), int(r["w"]), int(r["h"]))
		var at := AtlasTexture.new()
		at.atlas = tex
		at.region = Rect2(rect)
		frames.add_frame("explode", at)
		durations.append(float(f.get("duration", 83)) / 1000.0)
		var e := 0.0  # fire light = summed brightness of warm (fire) pixels
		for y in range(rect.position.y, rect.end.y, 2):
			for x in range(rect.position.x, rect.end.x, 2):
				var c := img.get_pixel(x, y)
				if c.a > 0.5 and c.r > c.b + 0.25:
					e += c.get_luminance()
		raw_energy.append(e)
	var mx := 0.0
	for e in raw_energy:
		mx = maxf(mx, e)
	for e in raw_energy:
		energy.append(clampf(e / maxf(mx, 0.001), 0.0, 1.0))
	for tag in meta.get("frameTags", []):
		if String(tag.get("name", "")) == "impact":
			impact = int(tag["from"])
	energy[impact] = 1.5  # the impact / flash frame
	# hold: frames after --hold-from are not played; that frame is held, drifts and erodes
	var hold_from := int(args.get("hold-from", "12"))
	if hold_from >= 0 and hold_from < durations.size() - 1:
		durations.resize(hold_from + 1)
		energy.resize(hold_from + 1)
	# palette roles: nearest sheet colour to each role, so code layers share the sheet's palette
	var cols: Array = []
	for h in meta.get("palette", []):
		cols.append(Color(String(h)))
	for role in ROLE_TARGETS:
		var tgt: Color = ROLE_TARGETS[role]
		var best: Color = tgt
		var bd := INF
		for c in cols:
			var d := Vector3(c.r - tgt.r, c.g - tgt.g, c.b - tgt.b).length()
			if d < bd:
				bd = d
				best = c
		pal[role] = best
	print("palette roles: ", pal.keys().size(), " from ", cols.size(), " sheet colours; energy ", energy)


func explode() -> void:
	var b := BlastScript.new()
	var seed_v := 505 if loop_period > 0.0 else 505 + count * 17
	count += 1
	add_child(b)
	b.set_origin(origin)
	b.setup(frames, durations, energy, pal, ground, origin, seed_v, layer_on, impact)
	blasts.append(b)


func _process(delta: float) -> void:
	clock += delta
	if loop_period > 0.0:
		if clock >= next_loop - 0.0001:
			explode()
			next_loop += loop_period
	elif auto_loop:
		var newest_done: bool = blasts.is_empty() or blasts[blasts.size() - 1].t > blasts[blasts.size() - 1].ai_end
		if newest_done:
			wait -= delta
			if wait <= 0.0:
				explode()
				wait = interval
	var lit := 0.0
	var fl := 0.0
	var sh := Vector2.ZERO
	for b in blasts.duplicate():
		b.advance(delta)
		if not b.alive():
			blasts.erase(b)
			b.queue_free()
			continue
		lit = maxf(lit, b.light())
		fl = maxf(fl, b.flash_strength())
		sh += b.shake()
	light_mat.set_shader_parameter("intensity", lit)
	light_mat.set_shader_parameter("light_pos", Vector2(ground.x, ground.y - int(args.get("light-y", "15"))))
	flash_rect.color.a = fl * flash_setting
	sh *= shake_setting
	cam.offset = Vector2(clampf(round(sh.x), -5, 5), clampf(round(sh.y), -5, 5))


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_accept") or (event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT):
		explode()
	elif event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_L:
			auto_loop = not auto_loop
		elif event.keycode == KEY_F:
			flash_setting = 0.4 if flash_setting > 0.5 else (0.0 if flash_setting > 0.0 else 1.0)
			print("flash ", flash_setting)
