// Erodes the held smoke frame in whole texels: blocky value noise, so the smoke breaks up in clean
// clumps, the bottom (the smoke stem) first and the top (the cap) last. No alpha blending.
// blast.gd sets `region` to the current frame's rect in the sheet and raises `amount` over the hold.
shader_type canvas_item;

uniform float amount = 0.0;              // 0 = solid; about 1.7 = gone
uniform vec4 region = vec4(0.0, 0.0, 1.0, 1.0);  // current frame in atlas texels: x, y, w, h

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float vnoise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}

void fragment() {
	vec4 c = texture(TEXTURE, UV);
	vec2 px = floor(UV * vec2(textureSize(TEXTURE, 0)));
	float ly = clamp((px.y - region.y) / max(1.0, region.w), 0.0, 1.0);  // 0 top, 1 bottom
	float e = vnoise(px * 0.08);  // clumps of about 12 texels
	if (c.a < 0.5 || (amount > 0.0 && e < amount * (0.55 + 0.9 * ly) - 0.05)) {
		discard;
	}
	COLOR = c;
}
