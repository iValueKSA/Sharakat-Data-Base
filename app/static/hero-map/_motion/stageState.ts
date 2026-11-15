/**
 * Shared state between the landing sections and the WebGL stage behind them.
 *
 * The sections own the choreography: their ScrollTriggers write how far the
 * reader has got into each chapter. The stage owns nothing but rendering: its
 * frame loop reads these numbers and eases the camera toward the pose they
 * describe.
 *
 * Deliberately a plain mutable module object, not React state or context.
 * Scroll progress changes every frame, and a React render per frame is the
 * one cost this page cannot afford. The only things that notify listeners are
 * the rare, discrete changes the stage has to react to structurally — whether
 * it is visible at all, and when its layout anchors move.
 *
 * There is one landing page, so one module-level instance is the right scope;
 * `resetStage()` runs when the page unmounts so a return visit starts clean.
 */

/** The sections that are windows onto the stage. Everything else is opaque. */
export type StageChapter = "hero" | "journey" | "finale";

export interface StageAnchor {
  /** Viewport-x of the anchor's centre, px. */
  x: number;
  /** Anchor centre measured from the top of its frame (the part of the
   *  section that sits at viewport-top when that chapter is on screen), px. */
  y: number;
  /** The anchor box's size, px — the hero sizes its map from it. */
  w: number;
  h: number;
}

export interface StageState {
  /** Hero entrance, 0 → 1, tweened once on load. */
  intro: number;
  /** Hero scrolling away toward the journey, 0 → 1. */
  approach: number;
  /** Progress through the pinned journey, 0 → 1. */
  journey: number;
  /** The finale window opening, 0 → 1. */
  finale: number;
  /** Where the finale's top edge is on screen right now, px. The finale's map
   *  travels with its section instead of staying pinned to the viewport. */
  finaleTop: number;
  /** Where the hero's top edge is on screen, px. Only read under reduced
   *  motion, where the map scrolls with its section like any image. */
  heroTop: number;
  /** Pointer position, −1 … 1 on both axes (fine pointers only). */
  pointerX: number;
  pointerY: number;
  /** Where each chapter wants the map to land on screen. */
  anchors: Record<StageChapter, StageAnchor | null>;
  /** Window sections currently intersecting the viewport. */
  windows: Set<StageChapter>;
  /** `prefers-reduced-motion: reduce` — one still frame per chapter. */
  reduced: boolean;
}

function initial(): StageState {
  return {
    intro: 0,
    approach: 0,
    journey: 0,
    finale: 0,
    finaleTop: 0,
    heroTop: 0,
    pointerX: 0,
    pointerY: 0,
    anchors: { hero: null, journey: null, finale: null },
    // The page always opens on the hero, so the stage starts visible; the
    // triggers correct this immediately if the page was restored mid-scroll.
    windows: new Set<StageChapter>(["hero"]),
    reduced: false,
  };
}

export const stage: StageState = initial();

type Listener = () => void;
const listeners = new Set<Listener>();

/** Subscribe to structural changes (visibility, anchors, reduced motion). */
export function onStageChange(fn: Listener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

function emit() {
  listeners.forEach((fn) => fn());
}

export function setStageWindow(chapter: StageChapter, visible: boolean) {
  const had = stage.windows.has(chapter);
  if (had === visible) return;
  if (visible) stage.windows.add(chapter);
  else stage.windows.delete(chapter);
  emit();
}

export function setStageReduced(reduced: boolean) {
  if (stage.reduced === reduced) return;
  stage.reduced = reduced;
  emit();
}

/**
 * Re-measure every `[data-stage-anchor]` element. Called on ScrollTrigger's
 * refresh, which is also when pinned layouts settle, so the numbers always
 * describe the layout the triggers were computed against.
 *
 * An anchor's y is taken relative to its closest `[data-stage-frame]`: the
 * box whose top edge sits at the top of the viewport while that chapter is
 * playing (the pinned journey stage, the hero, the finale). Both rects are
 * read in the same pass, so the current scroll offset cancels out.
 */
export function measureStageAnchors(root: ParentNode = document) {
  const found: Partial<Record<StageChapter, StageAnchor>> = {};
  root.querySelectorAll<HTMLElement>("[data-stage-anchor]").forEach((el) => {
    const chapter = el.dataset.stageAnchor as StageChapter;
    const frame = el.closest<HTMLElement>("[data-stage-frame]");
    if (!frame || found[chapter]) return;
    const a = el.getBoundingClientRect();
    // A chapter may carry one anchor per composition (the hero has a wide
    // and a compact one); the one hidden at this breakpoint measures as an
    // empty box at 0,0 and is skipped.
    if (a.width === 0 && a.height === 0) return;
    const f = frame.getBoundingClientRect();
    found[chapter] = {
      x: a.left + a.width / 2,
      y: a.top - f.top + a.height / 2,
      w: a.width,
      h: a.height,
    };
  });
  for (const chapter of Object.keys(stage.anchors) as StageChapter[]) {
    stage.anchors[chapter] = found[chapter] ?? null;
  }
  emit();
}

/**
 * Under reduced motion the scene renders on demand only; anything that moves
 * the map (scrolling its section) asks for one frame through here.
 */
let frameRequester: (() => void) | null = null;

export function setFrameRequester(fn: (() => void) | null) {
  frameRequester = fn;
}

export function requestStageFrame() {
  frameRequester?.();
}

export function resetStage() {
  Object.assign(stage, initial());
  emit();
}
