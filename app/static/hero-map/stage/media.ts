/**
 * The hero's recorded media: a still and a loop rendered offline from
 * `frontend/media/survey-night/` (the Kingdom's dune sea at night, drawn as
 * survey contours, read by the same scan front as the live map).
 *
 * The numbers below are shared with that renderer and with the camera rig:
 * change one side and the other must follow.
 */

const DIR = "/static/hero-map/assets";

export const MEDIA = {
  /** Loop length (s) — equal to the live map's sweep period (CameraRig). */
  loop: 10,
  /** The loop moment the landscape still shows; the video starts from it. */
  stillAt: 5.5,
  /**
   * Video time of the map sweep's phase 0: map phase = video time − offset.
   * With it, the land's scan crosses the map's side of the frame while the
   * map's own sweep crosses the map.
   */
  syncOffset: 2.55,
  landscape: {
    widths: [960, 1600, 2560],
    base: `${DIR}/hero-survey-kingdom`,
    fallback: `${DIR}/hero-survey-kingdom-1600.webp`,
  },
  portrait: {
    widths: [720, 1080],
    base: `${DIR}/hero-survey-kingdom-portrait`,
  },
  video: {
    webm: `${DIR}/hero-survey-loop.webm`,
    mp4: `${DIR}/hero-survey-loop.mp4`,
  },
} as const;

/**
 * Compact layouts in portrait get the portrait composition (horizon low,
 * under a phone's copy). Keyed to the layout breakpoint, like the stage.
 */
export const PORTRAIT_MEDIA = "(max-width: 1023.98px) and (max-aspect-ratio: 4/5)";

export function srcSet(base: string, widths: readonly number[], ext: "avif" | "webp") {
  return widths.map((w) => `${base}-${w}.${ext} ${w}w`).join(", ");
}

/**
 * The loop is a desktop nicety, never a requirement: no video under reduced
 * motion (decided by the caller), on compact layouts, with Save-Data on, on
 * slow connections, or on low-memory devices. The still covers all of those.
 */
export function mayPlayMedia(): boolean {
  const n = navigator as Navigator & {
    connection?: { saveData?: boolean; effectiveType?: string };
    deviceMemory?: number;
  };
  if (n.connection?.saveData) return false;
  if (n.connection?.effectiveType && /2g|3g/.test(n.connection.effectiveType)) return false;
  if (typeof n.deviceMemory === "number" && n.deviceMemory < 4) return false;
  return true;
}

