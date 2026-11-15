/**
 * GLSL for the Kingdom stage.
 *
 * Every layer reads the same story uniforms (see `materials.ts`), so one
 * number set by the camera rig — brightness, focus on Riyadh, the scan
 * fronts, the gold sweep — changes the whole map in step.
 *
 * The scan front is the page's one motif for "the system reads": the first
 * pass reveals the Kingdom, later passes are the monitoring sweep. It always
 * travels in the reading direction (`uDir`: +1 west → east, −1 east → west).
 */

/** Scan-front helpers, shared by every layer that sits on the land. */
const SCAN = /* glsl */ `
  uniform float uRevealX;
  uniform float uRevealOn;
  uniform float uSweepX;
  uniform float uSweep;
  uniform float uDir;

  // 0 until the reveal front has passed x, then 1.
  float revealMask(float x) {
    return smoothstep(0.0, 0.3, (uRevealX - x) * uDir);
  }

  // A front at f: a crisp leading line, and a softer light trailing it.
  float scanFront(float f, float x, float trail) {
    float d = (f - x) * uDir;
    float behind = max(d, 0.0);
    return smoothstep(-0.02, 0.0, d) * (0.5 * exp(-behind * 45.0) + 0.5 * exp(-behind * trail));
  }

  // All the scan light at x: the reveal's edge while it runs, plus the
  // monitoring sweep, which is quieter — it repeats for as long as you stay.
  float scanLight(float x) {
    return scanFront(uRevealX, x, 6.0) * uRevealOn + scanFront(uSweepX, x, 2.2) * uSweep * 0.6;
  }
`;

const FOG = /* glsl */ `
  uniform float uFogNear;
  uniform float uFogFar;
  float fogKeep(float depth) {
    return 1.0 - smoothstep(uFogNear, uFogFar, depth);
  }
`;

/* ── Constellation points ───────────────────────────────────────────── */

export const POINTS_VERT = /* glsl */ `
  ${SCAN}
  ${FOG}
  uniform float uTime;
  uniform float uSize;
  uniform float uPixelRatio;
  uniform float uSpark;
  uniform float uFocus;
  uniform vec3 uFocusPos;
  attribute float aSeed;
  varying float vAlpha;
  varying float vFlash;

  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    float depth = -mv.z;

    // Every point "publishes" once per 9s cycle, at its own phase. Only the
    // share of points under uSpark take part, so one uniform turns a
    // trickle of new tenders into a flood.
    float cycle = fract(uTime / 9.0 + aSeed * 7.31);
    float flash = smoothstep(0.0, 0.012, cycle) * (1.0 - smoothstep(0.012, 0.11, cycle));
    flash *= step(fract(aSeed * 3.17), uSpark);

    float scan = scanLight(position.x);
    float near = 1.0 - smoothstep(0.15, 1.1, distance(position.xz, uFocusPos.xz));
    float focusGain = mix(1.0, mix(0.45, 1.6, near), uFocus);

    vFlash = max(flash, scan * 0.4);
    vAlpha = focusGain * fogKeep(depth) * (revealMask(position.x) + scan * 0.7);
    gl_PointSize = min(uSize * (1.0 + flash * 2.4 + scan * 0.3) * uPixelRatio / depth, 18.0 * uPixelRatio);
    gl_Position = projectionMatrix * mv;
  }
`;

export const POINTS_FRAG = /* glsl */ `
  uniform vec3 uColor;
  uniform vec3 uFlashColor;
  uniform float uDim;
  varying float vAlpha;
  varying float vFlash;

  void main() {
    float r = length(gl_PointCoord - 0.5) * 2.0;
    float soft = 1.0 - smoothstep(0.0, 1.0, r);
    float alpha = soft * soft * vAlpha * uDim * (0.95 + vFlash * 1.2);
    if (alpha < 0.004) discard;
    gl_FragColor = vec4(mix(uColor, uFlashColor, vFlash), alpha);
    #include <colorspace_fragment>
  }
`;

/* ── Cities ─────────────────────────────────────────────────────────── */

export const CITY_VERT = /* glsl */ `
  ${SCAN}
  uniform float uTime;
  uniform float uSize;
  uniform float uPixelRatio;
  uniform float uFocus;
  attribute float aSeed;
  attribute float aMain;
  attribute float aOrder;
  varying float vPulse;
  varying float vMain;
  varying float vOrder;
  varying float vShown;

  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vPulse = fract(uTime / 1.8 + aSeed);
    vMain = aMain;
    vOrder = aOrder;
    vShown = min(1.0, revealMask(position.x) + scanLight(position.x));
    float size = uSize * (1.0 + aMain * uFocus * 1.2);
    gl_PointSize = min(size * uPixelRatio / -mv.z, 72.0 * uPixelRatio);
    gl_Position = projectionMatrix * mv;
  }
`;

export const CITY_FRAG = /* glsl */ `
  uniform vec3 uColor;
  uniform vec3 uGoldColor;
  uniform float uDim;
  uniform float uFocus;
  uniform float uGold;
  varying float vPulse;
  varying float vMain;
  varying float vOrder;
  varying float vShown;

  void main() {
    float r = length(gl_PointCoord - 0.5) * 2.0;
    float core = 1.0 - smoothstep(0.05, 0.24, r);
    float ringR = 0.28 + vPulse * 0.66;
    float ring = (1.0 - smoothstep(0.0, 0.05, abs(r - ringR))) * (1.0 - vPulse) * 0.5;
    // Riyadh keeps its light when the rest of the Kingdom dims around it.
    float lit = mix(uDim, 1.0, vMain * uFocus);
    // The finale's gold sweep reaches each city in turn, Riyadh first.
    float g = uGold * 1.1;
    float gold = 1.0 - smoothstep(g - 0.08, g, vOrder);
    float alpha = (core + ring) * lit * vShown;
    if (alpha < 0.004) discard;
    gl_FragColor = vec4(mix(uColor, uGoldColor, gold), alpha);
    #include <colorspace_fragment>
  }
`;

/* ── Lines: province borders, feeders, city routes ──────────────────── */

export const LINE_VERT = /* glsl */ `
  ${SCAN}
  ${FOG}
  uniform float uFocus;
  uniform vec3 uFocusPos;
  uniform float uFocusFloor;
  attribute float aFade;
  attribute float aOrder;
  varying float vFade;
  varying float vOrder;
  varying float vKeep;
  varying float vScan;

  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vFade = aFade;
    vOrder = aOrder;
    // Close in on Riyadh and the lines far from it step back, so the
    // journey's close-up reads as one place instead of a web.
    float near = 1.0 - smoothstep(0.35, 1.5, distance(position.xz, uFocusPos.xz));
    float focus = mix(1.0, mix(uFocusFloor, 1.0, near), uFocus);
    float scan = scanLight(position.x);
    vScan = scan;
    vKeep = fogKeep(-mv.z) * focus * (revealMask(position.x) + scan * 0.9);
    gl_Position = projectionMatrix * mv;
  }
`;

export const LINE_FRAG = /* glsl */ `
  uniform vec3 uColor;
  uniform vec3 uGoldColor;
  uniform vec3 uFlashColor;
  uniform float uOpacity;
  uniform float uDim;
  uniform float uGold;
  varying float vFade;
  varying float vOrder;
  varying float vKeep;
  varying float vScan;

  void main() {
    // The sweep: routes turn gold in order of distance from Riyadh. Lines
    // that are not routes carry aOrder = 2 and never light.
    float g = uGold * 1.1;
    float lit = 1.0 - smoothstep(g - 0.08, g, vOrder);
    float alpha = vFade * vKeep * uOpacity * mix(uDim, 1.0, lit * 0.7) * (1.0 + vScan * 0.6 + lit * 0.5);
    if (alpha < 0.004) discard;
    vec3 col = mix(mix(uColor, uFlashColor, vScan * 0.35), uGoldColor, lit);
    gl_FragColor = vec4(col, alpha);
    #include <colorspace_fragment>
  }
`;

/* ── The Kingdom plate ──────────────────────────────────────────────── */

/**
 * The land as a solid: the province polygons as a thin plate. Opaque, so the
 * survey field below is hidden where the Kingdom is and shows around it —
 * the gap between the two layers is the stage's main depth cue.
 */
export const PLATE_VERT = /* glsl */ `
  attribute float aTop;
  attribute float aSide;
  varying vec3 vPos;
  varying float vTop;
  varying float vSide;
  varying float vDepth;

  void main() {
    vPos = position;
    vTop = aTop;
    vSide = aSide;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vDepth = -mv.z;
    gl_Position = projectionMatrix * mv;
  }
`;

export const PLATE_FRAG = /* glsl */ `
  ${SCAN}
  ${FOG}
  uniform vec3 uTop;
  uniform vec3 uWall;
  uniform vec3 uWallDeep;
  uniform vec3 uLight;
  uniform vec3 uFocusPos;
  uniform float uFocus;
  uniform float uDim;
  varying vec3 vPos;
  varying float vTop;
  varying float vSide;
  varying float vDepth;

  void main() {
    float scan = scanLight(vPos.x);
    float shown = min(1.0, revealMask(vPos.x) + scan);
    if (shown < 0.01) discard;

    // A broad key light from the north-east, a pool of light where the
    // story is looking, and the scan passing over the land.
    float key = 1.0 - smoothstep(0.0, 3.6, distance(vPos.xz, vec2(1.1, -0.9)));
    float pool = (1.0 - smoothstep(0.0, 1.3, distance(vPos.xz, uFocusPos.xz))) * uFocus;
    vec3 top = uTop + uLight * (0.028 * key * uDim + 0.085 * pool + 0.075 * scan);

    // Walls: lit along the rim, falling into shadow toward the base.
    vec3 wall = mix(uWallDeep, uWall, pow(vTop, 1.6)) + uLight * pow(vTop, 10.0) * 0.18;

    // Fades out (not to navy): behind the canvas is the recorded media.
    vec3 col = mix(top, wall, vSide);
    gl_FragColor = vec4(col, shown * fogKeep(vDepth));
    #include <colorspace_fragment>
  }
`;

/* ── Survey field (graticule crosses under the plate) ───────────────── */

export const SURVEY_VERT = /* glsl */ `
  ${FOG}
  uniform float uGrid;
  attribute float aWeight;
  varying float vAlpha;

  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    float r = length(position.xz);
    // Spreads out from the centre as the stage first opens, then fades
    // toward the edge of the field so it never ends on a hard border.
    float grow = smoothstep(r - 0.9, r, uGrid * 9.0);
    float edge = 1.0 - smoothstep(2.6, 6.4, r);
    vAlpha = aWeight * grow * edge * fogKeep(-mv.z);
    gl_Position = projectionMatrix * mv;
  }
`;

export const SURVEY_FRAG = /* glsl */ `
  uniform vec3 uColor;
  uniform float uOpacity;
  uniform float uDim;
  uniform float uMedia;
  varying float vAlpha;

  void main() {
    // Over the recorded land the survey field steps back: one grid, not two.
    float alpha = vAlpha * uOpacity * mix(0.55, 1.0, uDim) * (1.0 - 0.5 * uMedia);
    if (alpha < 0.003) discard;
    gl_FragColor = vec4(uColor, alpha);
    #include <colorspace_fragment>
  }
`;

/* ── Soft light pooled under everything ─────────────────────────────── */

export const GLOW_VERT = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

export const GLOW_FRAG = /* glsl */ `
  uniform vec3 uColor;
  uniform float uDim;
  uniform float uGrid;
  uniform float uStrength;
  varying vec2 vUv;
  void main() {
    float d = length((vUv - 0.5) * 2.0);
    float alpha = pow(max(0.0, 1.0 - d), 2.4) * uStrength * uDim * uGrid;
    if (alpha < 0.003) discard;
    gl_FragColor = vec4(uColor, alpha);
    #include <colorspace_fragment>
  }
`;

/* ── Detection pings: rings on the ground where the sweep finds a tender ── */

export const PING_VERT = /* glsl */ `
  ${SCAN}
  ${FOG}
  uniform float uSweepSpeed;
  uniform float uPass;
  uniform float uHandled;
  attribute vec3 aCenter;
  attribute float aSeed;
  attribute float aOrder;
  varying vec2 vUv;
  varying float vAge;
  varying float vOn;
  varying float vGoldAge;
  varying float vGoldOn;

  const float LIFE = 1.9;

  void main() {
    // Seconds since the sweep crossed this site (negative: not yet).
    float age = (uSweepX - aCenter.x) * uDir / uSweepSpeed;
    // A different share of sites fires on every pass.
    float h = fract(sin((uPass + 1.0) * 12.9898 + aSeed * 78.233) * 43758.5453);
    vOn = step(h, 0.5) * step(0.0, age) * (1.0 - step(LIFE, age)) * uSweep;
    vAge = clamp(age / LIFE, 0.0, 1.0);

    // Finale: the gold reaches each site in order of its distance from
    // Riyadh; the site rings once, then stays lit. Scroll-driven, so it
    // plays back and forth with the reader.
    float g = uHandled * 1.15 - aOrder;
    vGoldOn = step(0.0, g) * step(0.001, uHandled);
    vGoldAge = clamp(g / 0.22, 0.0, 1.0);

    vUv = uv;
    vec3 p = aCenter + vec3(position.x, 0.0, -position.y) * 0.36;
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    float keep = fogKeep(-mv.z);
    vOn *= keep;
    vGoldOn *= keep;
    gl_Position = projectionMatrix * mv;
  }
`;

export const PING_FRAG = /* glsl */ `
  uniform vec3 uColor;
  uniform vec3 uFlashColor;
  uniform vec3 uGoldColor;
  varying vec2 vUv;
  varying float vAge;
  varying float vOn;
  varying float vGoldAge;
  varying float vGoldOn;

  void main() {
    if (vOn < 0.01 && vGoldOn < 0.01) discard;
    float r = length(vUv - 0.5) * 2.0;

    // Detection: a teal ring spreading from a bright core.
    float R = 0.12 + vAge * 0.88;
    float ring = (1.0 - smoothstep(0.0, 0.07, abs(r - R))) * pow(1.0 - vAge, 1.4);
    float core = (1.0 - smoothstep(0.0, 0.16, r)) * (1.0 - smoothstep(0.0, 0.45, vAge));
    float teal = (ring * 0.8 + core) * vOn;

    // Handled: one gold ring, then a small steady gold light.
    float GR = 0.1 + vGoldAge * 0.7;
    float gRing = (1.0 - smoothstep(0.0, 0.06, abs(r - GR))) * (1.0 - vGoldAge) * 0.9;
    float gDot = (1.0 - smoothstep(0.0, 0.13, r)) + (1.0 - smoothstep(0.0, 0.46, r)) * 0.26;
    float gold = (gRing + gDot) * vGoldOn;

    float alpha = teal + gold;
    if (alpha < 0.004) discard;
    vec3 tealCol = mix(uColor, uFlashColor, core);
    gl_FragColor = vec4((tealCol * teal + uGoldColor * gold) / alpha, min(alpha, 1.0));
    #include <colorspace_fragment>
  }
`;

/* ── Beacon: a column of light over Riyadh while its tender is the subject ── */

export const BEACON_VERT = /* glsl */ `
  uniform vec3 uBase;
  uniform float uWidth;
  uniform float uHeight;
  varying vec2 vUv;

  void main() {
    // Billboarded around the vertical axis: always faces the camera, always
    // stands straight up out of the map.
    vec3 base = (modelMatrix * vec4(uBase, 1.0)).xyz;
    vec3 toCam = cameraPosition - base;
    toCam.y = 0.0;
    vec3 right = normalize(cross(vec3(0.0, 1.0, 0.0), normalize(toCam + vec3(0.0001, 0.0, 0.0))));
    vec3 world = base + right * position.x * uWidth + vec3(0.0, (position.y + 0.5) * uHeight, 0.0);
    vUv = uv;
    gl_Position = projectionMatrix * viewMatrix * vec4(world, 1.0);
  }
`;

export const BEACON_FRAG = /* glsl */ `
  uniform vec3 uColor;
  uniform float uBeacon;
  varying vec2 vUv;

  void main() {
    float x = abs(vUv.x - 0.5) * 2.0;
    float core = pow(1.0 - x, 7.0);
    float halo = pow(1.0 - x, 2.2) * 0.28;
    float y = vUv.y;
    float fade = pow(1.0 - y, 1.7) * smoothstep(0.0, 0.03, y);
    float alpha = (core + halo) * fade * uBeacon;
    if (alpha < 0.004) discard;
    gl_FragColor = vec4(uColor, alpha);
    #include <colorspace_fragment>
  }
`;

/** A ground halo under the beacon: the light it throws onto the land. */
export const HALO_FRAG = /* glsl */ `
  uniform vec3 uColor;
  uniform float uBeacon;
  uniform float uTime;
  varying vec2 vUv;

  void main() {
    float r = length(vUv - 0.5) * 2.0;
    float pool = pow(max(0.0, 1.0 - r), 3.0) * 0.55;
    float t = fract(uTime / 2.4);
    float ring = (1.0 - smoothstep(0.0, 0.05, abs(r - (0.18 + t * 0.8)))) * (1.0 - t) * 0.6;
    float alpha = (pool + ring) * uBeacon;
    if (alpha < 0.004) discard;
    gl_FragColor = vec4(uColor, alpha);
    #include <colorspace_fragment>
  }
`;
