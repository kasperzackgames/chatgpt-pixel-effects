// Background light, simple (main.gd with --lit=none, or when the lit file is missing; it lights the
// sky too, so the painted light looks better). The blast light is a wide, low ellipse anchored just above the
// ground at the blast, so it spreads along the canyon floor and up the nearby cliff faces. Its
// falloff is cut into 5 HARD bands (no dither at the band edges), so the edges are smooth curved
// domes made of stair-stepped pixels and never a straight or vertical seam. Lit pixels move toward
// a warm colour scaled by their own brightness (detail survives); brighter surfaces take a little
// more light than the dark sky. A faint, constant glow can sit on a second point (the volcano top).
shader_type canvas_item;

uniform vec2 light_pos = vec2(196.0, 144.0);   // ellipse centre (about 15 px above the ground)
uniform float intensity = 0.0;                 // 0..1, up to 1.5 on the flash frame
uniform vec2 radii = vec2(170.0, 85.0);        // ellipse radii at full intensity (x wide, y low)
uniform vec3 warm = vec3(1.0, 0.55, 0.22);
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
	vec2 px = floor(UV * vec2(textureSize(TEXTURE, 0)));
	float lum = dot(c.rgb, vec3(0.299, 0.587, 0.114));
	vec3 col = c.rgb;
	// faint constant glow (volcano top): two small hard steps, same style as the blast light
	// (a dithered version read as a dotted halftone blob at 1280x720)
	float d2 = length((px + 0.5 - glow2_pos) / vec2(1.0, 0.75)) / glow2_radius;  // a little flat
	float g2 = d2 < 0.45 ? 0.45 : (d2 < 1.0 ? 0.22 : 0.0);
	col = mix(col, vec3(0.75, 0.25, 0.08) * (lum * 2.0 + 0.2), g2 * glow2_amount);
	// blast light: elliptical falloff, hard bands
	float I = clamp(intensity, 0.0, 1.5);
	vec2 r = radii * (0.55 + 0.45 * min(I, 1.0));
	vec2 q = (px + 0.5 - light_pos) / r;
	float e = length(q);                        // 0 at the centre, 1 on the ellipse
	float f = pow(clamp(1.0 - e, 0.0, 1.0), 1.6) * I;
	// 5 small hard steps: each band edge is a gentle step, not a ring you notice
	float m = 0.0;
	if (f > 0.62) {
		m = 0.66;
	} else if (f > 0.42) {
		m = 0.46;
	} else if (f > 0.25) {
		m = 0.28;
	} else if (f > 0.12) {
		m = 0.15;
	} else if (f > 0.04) {
		m = 0.06;
	}
	m *= clamp((lum - 0.05) / 0.15, 0.35, 1.0);
	// mix toward warm (keeps surface detail) + a small warm lift, so dark sky glows warm, not grey
	col = mix(col, warm * (lum * 2.4 + 0.12), m) + warm * m * 0.10;
	COLOR = vec4(col, c.a);
}
