.pragma library
// Apache-2.0. The in-app material's uniforms: a line-for-line port of the Flutter port's
// lib/src/material.dart, itself a port of ports/skia's clearMaterialUniforms (renderer.mjs) and
// inAppMaterialUniforms (material.mjs), which carry Compose's GlassStyle.inApp. Lengths are device
// pixels; the density converts the dp constants. Plain ES5 so QML's engine and Node both run it
// (test/material.test.mjs checks it against ports/flutter/test/material_fixture.json).

var LIGHT_OPACITY = [[0, .435], [31, .514], [50, .565], [62, .600], [100, .733]];
var DARK_OPACITY = [[0, .416], [29, .439], [50, .451], [62, .510], [86, .655], [100, .737]];

function interpolate(table, t) {
    var i = 0;
    while (i < table.length - 2 && table[i + 1][0] <= t) i++;
    var x = table[i][0], a = table[i][1], y = table[i + 1][0], b = table[i + 1][1];
    return a + (b - a) * (t - x) / (y - x);
}

function clamp01(v) { return Math.min(1, Math.max(0, v)); }

/**
 * Every material uniform the shader reads, {name: [numbers]}, for a surface of `width` × `height`
 * device pixels (without the padding) at `density` device pixels per logical pixel.
 * m: {radius, dark, tintAmount, light: [x, y], tint: [r, g, b, a] or null, materialize,
 *     reducedTransparency, increasedContrast}; radius is in logical pixels.
 */
function uniforms(m, width, height, density) {
    var tintAmount = m.tintAmount === undefined ? 50 : m.tintAmount;
    if (tintAmount < 0 || tintAmount > 100) throw new RangeError("tintAmount must be 0 to 100");
    var v = {};
    // clearMaterialUniforms (magnification 1).
    v.uSize = [width, height];
    v.uPad = [2];
    // The backdrop texture is sampled clamped at its edges, so the backdrop region is unbounded here.
    v.uBackdrop = [-1e5, -1e5, 1e5, 1e5];
    v.uRefractBand = [24];
    v.uRefractDepth = [12];
    v.uIor = [1.5];
    v.uBevelPower = [2];
    v.uCornerPower = [2];
    v.uFieldRange = [1];
    v.uFieldScale = [1];
    v.uBevel = [2];
    v.uSpecularPow = [4];
    v.uCounterLight = [1];
    v.uEdgeLight = [1];
    v.uTint = [1, 1, 1, 0];
    v.uFineShare = [1];
    v.uWideScale = [.25];
    v.uTouch = [width / 2, height / 2];
    v.uPoseA = [1, 0, 0, 1];
    v.uPoseAInv = [1, 0, 0, 1];
    v.uPoseD = [1, 1, 1, 0];
    v.uPoseE = [0, 3, 0, 0];

    // inAppMaterialUniforms.
    var t = tintAmount / 100;
    var limit = Math.min(width, height) / 2;
    var r = Math.min((m.radius === undefined ? 20 : m.radius) * density, limit);
    var grey = m.dark ? 0 : 241 / 255;
    var opacity = Math.round(interpolate(m.dark ? DARK_OPACITY : LIGHT_OPACITY, tintAmount) * 255) / 255;
    var light = m.light || [-0.35, -0.94];
    v.uRadii = [r, r, r, r];
    v.uRefractBand = [.6 * r];
    v.uRefractDepth = [14 * density];
    v.uProfile = [1];
    v.uFormation = [0];
    v.uHeldLens = [0];
    v.uHeldMagnification = [0];
    v.uHeldGlow = [1];
    v.uAberration = [.07];
    v.uBlur = [(.5 + 1.5 * t * t) / .6 * density];
    v.uWideKernel = [10 * density];
    v.uFineShare = [.95 * Math.pow(1 - t, 1.5)];
    v.uTint = [grey, grey, grey, opacity];
    v.uLift = [m.dark ? 35 / 255 : 0];
    v.uBevel = [1.33 * density];
    v.uBevelPeak = [.25];
    v.uSpecular = [.25];
    v.uSpecularPow = [6];
    v.uCounterLight = [1];
    v.uEdgeLight = [0];
    v.uLight = [light[0], light[1]];
    v.uLegibility = [.6];
    v.uScale = [clamp01((Math.min(width, height) / density - 56) / 264)];
    v.uMaterialize = [clamp01(m.materialize === undefined ? 1 : m.materialize)];
    v.uFrost = [clamp01(m.reducedTransparency || 0)];
    v.uContrast = [clamp01(m.increasedContrast || 0)];
    if (m.tint) {
        var q = function (c) { return Math.round(c * 255) / 255; };
        v.uTint = [q(m.tint[0]), q(m.tint[1]), q(m.tint[2]), q(m.tint[3])];
    }
    // Qt reads the wide tone from the backdrop directly (see tool/generate_shader.mjs): switch it on.
    v.uWideStrip = [1];
    return v;
}

if (typeof module !== "undefined") module.exports = { uniforms: uniforms };
