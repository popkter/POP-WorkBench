#version 440
// PopToolProject: transparent material overlay. DWM owns the desktop pixels;
// this shader has no sampler and cannot capture or refract external windows.
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 uSize;
    float uRadius;
    vec4 uTint;
    vec2 uTouch;
    float uTouchAmount;
};
void main() {
    vec2 size = max(uSize, vec2(1.0));
    vec2 position = qt_TexCoord0 * size;
    vec2 p = position - size * 0.5;
    float radius = clamp(uRadius, 0.0, min(size.x, size.y) * 0.5);
    vec2 q = abs(p) - size * 0.5 + radius;
    float distance = length(max(q, vec2(0.0))) + min(max(q.x, q.y), 0.0) - radius;
    float coverage = 1.0 - smoothstep(-0.7, 0.7, distance);
    vec2 gradient = max(q, vec2(0.001)) * sign(p);
    if (q.x < 0.0 || q.y < 0.0)
        gradient = q.x > q.y ? vec2(sign(p.x), 0.0) : vec2(0.0, sign(p.y));
    float facing = dot(normalize(gradient), normalize(vec2(-0.4, -0.9)));
    float rim = (1.0 - smoothstep(0.3, 2.2, -distance))
        * (0.05 + 0.24 * max(facing, 0.0));
    float glow = exp(-length(position - uTouch) / 70.0) * uTouchAmount * 0.045;
    float highlight = clamp(rim + glow, 0.0, 0.4);
    float alpha = uTint.a + highlight * (1.0 - uTint.a);
    vec3 premultiplied = uTint.rgb * uTint.a * (1.0 - highlight) + vec3(highlight);
    fragColor = vec4(premultiplied, alpha) * coverage * qt_Opacity;
}
