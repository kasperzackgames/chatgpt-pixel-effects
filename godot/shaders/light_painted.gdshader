// Background light, painted (main.gd's default; --lit=PATH.png). lit_tex is the same background
// relit by an image AI (warm light from the blast spot on the canyon floor and the cliff faces),
// cleaned so that every pixel the fire does not light is identical to the background
// (scripts/make_lit.py). The scene blends toward it
// by the fire's intensity under a soft radial mask, in whole pixels: 4 blend steps with a fixed
// 4x4 Bayer pattern between them. Where the two images are identical (sky, stars, volcano, far
// mist) nothing can change, so there is no band, lens or seam; the colour change comes only from
// light painted on real surfaces. Plus the faint, constant glow on the volcano top (2 hard steps).
shader_type canvas_item;

uniform sampler2D lit_tex : filter_nearest;
uniform vec2 light_pos = vec2(196.0, 144.0);   // mask centre (about 15 px above the ground)
uniform float intensity = 0.0;                 // fire light 0..1 (the flash frame's 1.5 is clamped)
uniform vec2 radii = vec2(230.0, 170.0);       // mask: full inside 35% of this ellipse, zero at its edge
uniform vec2 glow2_pos = vec2(-100.0, -100.0);
uniform float glow2_radius = 10.0;
uniform float glow2_amount = 0.0;

float bayer4(vec2 p) {
	int i = int(mod(p.x, 4.0)) + int(mod(p.y, 4.0)) * 4;
	float m[16] = float[16](0.0, 8.0, 2.0, 10.0, 12.0, 4.0, 14.0, 6.0, 3.0, 11.0, 1.0, 9.0, 15.0, 7.0, 13.0, 5.0);
	return (m[i] + 0.5) / 16.0;
}

void fragment() {
	vec4 c = texture(TEXTURE, UV);
	vec3 lit = texture(lit_tex, UV).rgb;
	vec2 px = floor(UV * vec2(textureSize(TEXTURE, 0)));
	float lum = dot(c.rgb, vec3(0.299, 0.587, 0.114));
	vec3 col = c.rgb;
	// faint constant glow (volcano top): two small hard steps
	float d2 = length((px + 0.5 - glow2_pos) / vec2(1.0, 0.75)) / glow2_radius;
	float g2 = d2 < 0.45 ? 0.45 : (d2 < 1.0 ? 0.22 : 0.0);
	col = mix(col, vec3(0.75, 0.25, 0.08) * (lum * 2.0 + 0.2), g2 * glow2_amount);
	// painted blast light
	float e = length((px + 0.5 - light_pos) / radii);
	float mask = 1.0 - smoothstep(0.35, 1.0, e);
	float w = clamp(intensity, 0.0, 1.0) * mask;
	float q = clamp(floor(w * 4.0 + bayer4(px)) / 4.0, 0.0, 1.0);
	col = mix(col, lit, q);
	COLOR = vec4(col, c.a);
}
