import { MAP_CENTER, RIYADH, X_SPAN, Z_SPAN, type Vec3 } from "./geo";
import type { StageAnchor, StageChapter, StageState } from "../../_motion/stageState";

/**
 * Where the camera is, and how the map is lit, at every point of the story.
 *
 * A pose is a keyframe; the rig resolves it against the current viewport
 * (fit distance, DOM anchor) into a `Frame` of plain numbers, interpolates
 * between the two frames that bracket the reader's progress, and damps the
 * live camera toward the result. Nothing here is tweened by GSAP: GSAP owns
 * the progress values, this file owns what they mean.
 */

export interface Pose {
  /** Which chapter's DOM anchor places the target on screen. */
  chapter: StageChapter;
  target: Vec3;
  /** Multiplier on the distance that fits the whole map into the chapter's frame. */
  zoom: number;
  /** Radians down from straight overhead. */
  polar: number;
  /** Radians around the vertical axis; 0 keeps north at the top. */
  azim: number;
  /** Overall brightness of the constellation, 0 … 1. */
  dim: number;
  /** Light pulled toward the target and away from the rest, 0 … 1. */
  focus: number;
  /** Share of points flashing as "just published", 0 … 1. */
  spark: number;
  /** How far the gold sweep has run along the city routes, 0 … 1. */
  gold: number;
  /** City-label opacity, 0 … 1. */
  labels: number;
  /** Strength of the monitoring sweep and its detection pings, 0 … 1. */
  sweep: number;
  /** Riyadh's light column, 0 … 1. */
  beacon: number;
  /** Finale only: how far the "handled" gold has spread over the tender
   *  sites, outward from Riyadh, 0 … 1. */
  handled: number;
  /** The recorded media layer behind the map: opacity, and its push-in. */
  media: number;
  mediaZoom: number;
}

/** A pose resolved for the current viewport: numbers only, safe to lerp. */
export interface Frame {
  tx: number; ty: number; tz: number;
  dist: number; polar: number; azim: number;
  ax: number; ay: number;
  dim: number; focus: number; spark: number; gold: number; labels: number;
  sweep: number; beacon: number; handled: number; media: number; mediaZoom: number;
}

/**
 * Journey timeline marks, as fractions of the pinned scroll. The DOM
 * timeline in `Journey.tsx` places its tweens on these same numbers, so the
 * document leaving Riyadh and the camera arriving there are one event.
 */
export const JOURNEY_MARKS = {
  emerge: 0.08,
  analyze: 0.26,
  match: 0.52,
  alert: 0.76,
} as const;

/** Where each of the four steps (detect, analyze, match, alert) takes over. */
export const JOURNEY_STEPS = [0, 0.22, 0.48, 0.72] as const;

const HERO: Pose = {
  chapter: "hero", target: MAP_CENTER, zoom: 1, polar: 0.9, azim: -0.2,
  dim: 1, focus: 0, spark: 0.07, gold: 0, labels: 1, sweep: 1, beacon: 0, handled: 0,
  media: 1, mediaZoom: 1,
};

/** The camera's opening position: high above, turned, the map still dark. */
const HERO_INTRO: Pose = {
  ...HERO, zoom: 1.45, polar: 0.42, azim: -0.62, dim: 0.12, labels: 0, sweep: 0,
};

const JOURNEY: [number, Pose][] = [
  [0, {
    chapter: "journey", target: RIYADH, zoom: 0.8, polar: 0.92, azim: -0.08,
    dim: 1, focus: 0.25, spark: 1, gold: 0, labels: 0.75, sweep: 0.7, beacon: 0.35, handled: 0,
    media: 0.4, mediaZoom: 1.12,
  }],
  [JOURNEY_MARKS.emerge, {
    chapter: "journey", target: RIYADH, zoom: 0.54, polar: 0.82, azim: 0.02,
    dim: 0.82, focus: 0.85, spark: 0.45, gold: 0, labels: 0.15, sweep: 0.2, beacon: 1, handled: 0,
    media: 0, mediaZoom: 1.2,
  }],
  [JOURNEY_MARKS.analyze, {
    chapter: "journey", target: RIYADH, zoom: 0.46, polar: 0.74, azim: 0.12,
    dim: 0.7, focus: 1, spark: 0.16, gold: 0, labels: 0, sweep: 0, beacon: 0.85, handled: 0,
    media: 0, mediaZoom: 1.2,
  }],
  [JOURNEY_MARKS.match, {
    chapter: "journey", target: RIYADH, zoom: 0.44, polar: 0.7, azim: 0.24,
    dim: 0.66, focus: 1, spark: 0.16, gold: 0, labels: 0, sweep: 0, beacon: 0.85, handled: 0,
    media: 0, mediaZoom: 1.2,
  }],
  [JOURNEY_MARKS.alert, {
    chapter: "journey", target: RIYADH, zoom: 0.52, polar: 0.76, azim: 0.34,
    dim: 0.62, focus: 0.8, spark: 0.3, gold: 0.12, labels: 0, sweep: 0, beacon: 0.3, handled: 0,
    media: 0, mediaZoom: 1.2,
  }],
  [1, {
    chapter: "journey", target: RIYADH, zoom: 0.56, polar: 0.78, azim: 0.38,
    dim: 0.62, focus: 0.75, spark: 0.3, gold: 0.18, labels: 0, sweep: 0, beacon: 0.15, handled: 0,
    media: 0, mediaZoom: 1.2,
  }],
];

const FINALE_START: Pose = {
  chapter: "finale", target: MAP_CENTER, zoom: 1.3, polar: 0.78, azim: 0.34,
  dim: 0.5, focus: 0, spark: 0.2, gold: 0, labels: 0.4, sweep: 0, beacon: 0, handled: 0,
  media: 0.25, mediaZoom: 1.1,
};

const FINALE: Pose = {
  chapter: "finale", target: MAP_CENTER, zoom: 1, polar: 0.52, azim: 0,
  dim: 1, focus: 0, spark: 0.03, gold: 1, labels: 0.85, sweep: 0, beacon: 0, handled: 1,
  media: 0.7, mediaZoom: 1.02,
};

/* ── Resolving ──────────────────────────────────────────────────────── */

const TAN_HALF_FOV = Math.tan((50 * Math.PI) / 180 / 2);

/**
 * How much of the frame the whole map should fill, per chapter and layout.
 * Compact layouts let it bleed past both edges — on a portrait phone a map
 * that fits the width is a thin strip.
 */
const FILL: Record<StageChapter, { wide: [number, number]; compact: [number, number] }> = {
  hero: { wide: [0.62, 0.82], compact: [1.34, 0.5] },
  journey: { wide: [0.56, 0.8], compact: [1.34, 0.5] },
  finale: { wide: [0.6, 0.66], compact: [1.3, 0.48] },
};

export interface ResolveContext {
  w: number;
  h: number;
  compact: boolean;
  anchors: Record<StageChapter, StageAnchor | null>;
}

/** Camera distance at which the map spans the chapter's fill of the frame. */
function fitDistance(chapter: StageChapter, polar: number, ctx: ResolveContext): number {
  const [fill, fillH] = FILL[chapter][ctx.compact ? "compact" : "wide"];
  let fw = fill;
  let fh = fillH;
  // The wide hero sizes the map from its anchor box (the end columns, bled
  // to the viewport edge), not from the viewport: on a 2560px+ screen the
  // copy stops growing at the container but the viewport keeps going, and a
  // viewport-sized map slid in behind the paragraph. Slightly narrower than
  // the box, because the near (southern) half of a tilted map projects
  // wider than its middle — the whole Kingdom stays in frame.
  const anchor = ctx.anchors[chapter];
  if (chapter === "hero" && anchor && anchor.w > 0) {
    if (!ctx.compact) fw = Math.min(fw, (anchor.w * 0.9) / ctx.w);
    // Compact: the band between the actions and the facts. The map may
    // bleed past the sides, but on a tablet a width-sized map grew taller
    // than its band and ran under the facts; the band's height caps it.
    else fh = Math.min(fh, (anchor.h * 1.15) / ctx.h);
  }
  const aspect = ctx.w / Math.max(ctx.h, 1);
  // Seen from `polar` off vertical, the map's depth foreshortens by cos(polar).
  const depthOnScreen = Z_SPAN * Math.cos(polar) + 0.4;
  const byWidth = X_SPAN / (fw * 2 * TAN_HALF_FOV * aspect);
  const byHeight = depthOnScreen / (fh * 2 * TAN_HALF_FOV);
  return Math.max(byWidth, byHeight);
}

/** Fallback anchor when a chapter's anchor isn't measured yet. */
function defaultAnchor(chapter: StageChapter, ctx: ResolveContext): StageAnchor {
  if (chapter === "finale") return { x: ctx.w / 2, y: ctx.h * 0.62, w: ctx.w, h: ctx.h * 0.4 };
  return ctx.compact
    ? { x: ctx.w / 2, y: ctx.h * 0.7, w: ctx.w, h: ctx.h * 0.4 }
    : { x: ctx.w * 0.66, y: ctx.h * 0.52, w: ctx.w * 0.5, h: ctx.h * 0.6 };
}

export function resolve(p: Pose, ctx: ResolveContext): Frame {
  const a = ctx.anchors[p.chapter] ?? defaultAnchor(p.chapter, ctx);
  return {
    tx: p.target[0], ty: p.target[1], tz: p.target[2],
    dist: fitDistance(p.chapter, p.polar, ctx) * p.zoom,
    polar: p.polar, azim: p.azim,
    ax: a.x, ay: a.y,
    dim: p.dim, focus: p.focus, spark: p.spark, gold: p.gold, labels: p.labels,
    sweep: p.sweep, beacon: p.beacon, handled: p.handled,
    media: p.media, mediaZoom: p.mediaZoom,
  };
}

const KEYS = Object.keys(resolveZero()) as (keyof Frame)[];

function resolveZero(): Frame {
  return {
    tx: 0, ty: 0, tz: 0, dist: 0, polar: 0, azim: 0, ax: 0, ay: 0,
    dim: 0, focus: 0, spark: 0, gold: 0, labels: 0, sweep: 0, beacon: 0, handled: 0,
    media: 0, mediaZoom: 1,
  };
}

export function lerpFrame(a: Frame, b: Frame, t: number, out: Frame = resolveZero()): Frame {
  for (const k of KEYS) out[k] = a[k] + (b[k] - a[k]) * t;
  return out;
}

export function copyFrame(from: Frame, to: Frame = resolveZero()): Frame {
  for (const k of KEYS) to[k] = from[k];
  return to;
}

export const emptyFrame = resolveZero;

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);
const smooth = (t: number) => t * t * (3 - 2 * t);
/** Decelerating ease for the one-shot intro. */
const outCubic = (t: number) => 1 - Math.pow(1 - t, 3);

/**
 * The frame the camera should be heading for, given where the reader is.
 *
 * Chapters are checked from the end of the page back: the finale wins while
 * its window is open, then the journey once it has started, then the hero
 * (whose own frame already blends toward the journey's first pose as the
 * hero scrolls away, so the hand-over at the pin is seamless).
 */
export function targetFrame(s: StageState, ctx: ResolveContext, out: Frame): Frame {
  if (s.reduced) {
    // One still frame per chapter, carried by its section like an image.
    const onFinale = s.windows.has("finale") && !s.windows.has("hero");
    copyFrame(resolve(onFinale ? FINALE : HERO, ctx), out);
    out.ay += onFinale ? s.finaleTop : s.heroTop;
    return out;
  }

  if (s.windows.has("finale") && !s.windows.has("journey") && !s.windows.has("hero")) {
    lerpFrame(resolve(FINALE_START, ctx), resolve(FINALE, ctx), smooth(clamp01(s.finale)), out);
    out.ay += s.finaleTop;
    return out;
  }

  if (s.journey > 0) {
    const p = clamp01(s.journey);
    let i = 0;
    while (i < JOURNEY.length - 2 && p > JOURNEY[i + 1][0]) i++;
    const [p0, a] = JOURNEY[i];
    const [p1, b] = JOURNEY[i + 1];
    const t = smooth(clamp01((p - p0) / (p1 - p0)));
    return lerpFrame(resolve(a, ctx), resolve(b, ctx), t, out);
  }

  const hero = lerpFrame(resolve(HERO_INTRO, ctx), resolve(HERO, ctx), outCubic(clamp01(s.intro)));
  return lerpFrame(hero, resolve(JOURNEY[0][1], ctx), smooth(clamp01(s.approach)), out);
}
