"use client";

import { useEffect, useMemo, useRef, type RefObject } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { CITY_LABEL_POS, CITY_POS, SCAN_REACH } from "./geo";
import { LABELED } from "./KingdomLayers";
import { MEDIA } from "./media";
import type { Uniforms } from "./materials";
import { copyFrame, emptyFrame, targetFrame, type Frame } from "./poses";
import { onStageChange, setFrameRequester, stage } from "../../_motion/stageState";

/**
 * The camera rig: once per frame it resolves where the story wants the
 * camera, damps toward it, and writes every story uniform the layers read.
 *
 * Two clocks, on purpose:
 *  - the entrance (survey field spreading, the first scan revealing the
 *    Kingdom) is a pure function of `stage.intro`, which GSAP tweens. A
 *    paused render loop can't strand it halfway — it is simply correct on
 *    the next frame;
 *  - ambient motion (the monitoring sweep, point flashes) runs on the scene
 *    clock, which is exactly what should stop when the stage is hidden.
 *
 * Once the recorded loop is playing, the sweep's clock *is* the video's
 * clock: the loop's scan and the map's scan are one front, and a stalled or
 * paused video can never leave them out of step.
 */

const FRAME_KEYS = Object.keys(emptyFrame()) as (keyof Frame)[];

/** Monitoring sweep: speed (scene units/s), first delay (s). */
const SWEEP_SPEED = 1.05;
const SWEEP_DELAY = 0.9;
/**
 * One pass plus its rest — the recorded loop's length, so they can lock. A
 * pass (the front from one side of the land to past the other,
 * 2 × SCAN_REACH + 0.3 at SWEEP_SPEED ≈ 7.5 s) must stay shorter than this.
 */
const SWEEP_PERIOD = MEDIA.loop;
/** The sweep phase at which the video, waiting on its still frame, starts. */
const SYNC_PHASE = MEDIA.stillAt - MEDIA.syncOffset;

const mod = (a: number, n: number) => ((a % n) + n) % n;

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);
const smooth01 = (v: number) => {
  const t = clamp01(v);
  return t * t * (3 - 2 * t);
};

export function CameraRig({ uniforms, compact, dir, labelRefs, media }: {
  uniforms: Uniforms;
  compact: boolean;
  /** Reading direction: +1 LTR, −1 RTL. Every scan travels this way. */
  dir: 1 | -1;
  labelRefs: React.MutableRefObject<(HTMLSpanElement | null)[]>;
  /** The recorded media layer (StageMedia): faded, pushed and synced here. */
  media: RefObject<HTMLDivElement | null>;
}) {
  const current = useRef<Frame | null>(null);
  const target = useMemo(emptyFrame, []);
  const snap = useRef(true);
  const sweepClock = useRef(0);
  const lastPhase = useRef(-1);
  const pass = useRef(0);
  const invalidate = useThree((s) => s.invalidate);

  // A stage that was hidden (covered by an opaque section) must not glide in
  // from wherever the camera was when it disappeared: snap on reappearing.
  // Structural changes also need a frame drawn when the loop is on demand.
  useEffect(() => {
    let wasVisible = stage.windows.size > 0;
    setFrameRequester(invalidate);
    const off = onStageChange(() => {
      const visible = stage.windows.size > 0;
      if (visible && !wasVisible) snap.current = true;
      wasVisible = visible;
      invalidate();
    });
    return () => {
      off();
      setFrameRequester(null);
    };
  }, [invalidate]);

  useFrame((state, delta) => {
    const { width: w, height: h } = state.size;
    targetFrame(stage, { w, h, compact, anchors: stage.anchors }, target);

    if (!stage.reduced) {
      // A slow breath of the camera plus a little pointer parallax. The
      // journey is framed tightly around Riyadh, so it drifts least there.
      const calm = 1 - Math.min(1, stage.journey * 5) * 0.7;
      target.azim += Math.sin(state.clock.elapsedTime * 0.11) * 0.06 * calm + stage.pointerX * 0.07 * calm;
      target.polar -= stage.pointerY * 0.035 * calm;
    }

    // Exponential damping cannot overshoot, so a long frame just lands
    // closer to the target; the cap only guards against a resumed tab
    // reporting its whole pause as one delta.
    const dt = Math.min(delta, 0.25);
    if (!current.current || snap.current || stage.reduced) {
      current.current = copyFrame(target, current.current ?? undefined);
      snap.current = false;
    } else {
      const c = current.current;
      for (const k of FRAME_KEYS) c[k] = THREE.MathUtils.damp(c[k], target[k], 3.2, dt);
    }

    const f = current.current;
    const cam = state.camera as THREE.PerspectiveCamera;
    const sp = Math.sin(f.polar);
    cam.position.set(
      f.tx + f.dist * sp * Math.sin(f.azim),
      f.ty + f.dist * Math.cos(f.polar),
      f.tz + f.dist * sp * Math.cos(f.azim),
    );
    cam.lookAt(f.tx, f.ty, f.tz);
    // Off-axis projection: puts the look-at point under the chapter's DOM
    // anchor instead of at the centre of the screen.
    cam.setViewOffset(w, h, w / 2 - f.ax, h / 2 - f.ay, w, h);

    /* The entrance: survey field first, then one scan pass reveals the land. */
    const intro = stage.reduced ? 1 : stage.intro;
    const grid = smooth01(intro / 0.45);
    const reveal = smooth01((intro - 0.14) / 0.66);
    const revealX = dir * SCAN_REACH * (2 * reveal - 1);

    /* The monitoring sweep, once the Kingdom is revealed — on its own clock
       until the recorded loop plays, then on the loop's. */
    const gate = stage.reduced ? 0 : smooth01((intro - 0.86) / 0.14);
    const mediaEl = media.current;
    const video = mediaEl?.querySelector("video") ?? null;
    const locked = video?.dataset.state === "playing";
    let phase: number;
    if (locked) {
      phase = mod(video.currentTime - MEDIA.syncOffset, SWEEP_PERIOD);
    } else {
      if (gate > 0) sweepClock.current += dt;
      const t = sweepClock.current - SWEEP_DELAY;
      phase = t < 0 ? -1 : t % SWEEP_PERIOD;
    }
    const prev = lastPhase.current;
    if (phase >= 0 && prev >= 0 && phase < prev - SWEEP_PERIOD / 2) pass.current++;

    // The loop waits on the still's frame; it starts the moment the map's
    // sweep reaches that frame's moment, so the swap is frame-identical.
    if (video && !stage.reduced && f.media > 0.5 && video.dataset.state === "ready" &&
        prev >= 0 && prev < SYNC_PHASE && phase >= SYNC_PHASE) {
      video.dataset.state = "playing";
      video.play().catch(() => {
        video.dataset.state = "ready";
      });
    }
    // Only decode while it can be seen. A resume that is refused hands the
    // sweep back to its own clock rather than retrying every frame.
    if (locked) {
      const wanted = f.media > 0.03;
      if (wanted && video.paused) {
        video.play().catch(() => {
          video.dataset.state = "ready";
        });
      } else if (!wanted && !video.paused) video.pause();
    }
    lastPhase.current = phase;

    uniforms.uTime.value = state.clock.elapsedTime;
    uniforms.uPixelRatio.value = state.viewport.dpr;
    uniforms.uDim.value = f.dim;
    uniforms.uFocus.value = f.focus;
    uniforms.uSpark.value = stage.reduced ? 0 : f.spark;
    uniforms.uGold.value = f.gold;
    uniforms.uFogNear.value = f.dist + 0.6;
    uniforms.uFogFar.value = f.dist + 7;
    uniforms.uDir.value = dir;
    uniforms.uGrid.value = grid;
    uniforms.uRevealX.value = revealX;
    uniforms.uRevealOn.value = 1 - smooth01((reveal - 0.9) / 0.1);
    uniforms.uSweep.value = f.sweep * gate;
    uniforms.uSweepSpeed.value = SWEEP_SPEED;
    uniforms.uSweepX.value = phase < 0 ? -dir * 99 : dir * (phase * SWEEP_SPEED - SCAN_REACH - 0.3);
    uniforms.uPass.value = pass.current;
    uniforms.uBeacon.value = stage.reduced ? 0 : f.beacon;
    uniforms.uHandled.value = f.handled;
    uniforms.uMedia.value = f.media;

    // The media layer follows the same damped frame as the camera: it fades
    // and pushes in as the camera dives toward Riyadh, returns in the finale.
    if (mediaEl) {
      const o = Math.round(f.media * 100) / 100;
      const z = Math.round(f.mediaZoom * 1000) / 1000;
      const key = `${o}|${z}`;
      if (mediaEl.dataset.f !== key) {
        mediaEl.dataset.f = key;
        mediaEl.style.opacity = String(o);
        mediaEl.style.transform = z === 1 ? "" : `scale(${z})`;
      }
    }

    // Each label appears as the reveal passes its city. Written only when
    // the rounded value changes, and remembered per element: labels
    // re-created by a language switch start from nothing.
    LABELED.forEach(({ i }, n) => {
      const el = labelRefs.current[n];
      if (!el) return;
      const shown = smooth01(((revealX - CITY_LABEL_POS[i][0]) * dir) / 0.3);
      const v = String(Math.round(f.labels * shown * 50) / 50);
      if (el.dataset.o !== v) {
        el.dataset.o = v;
        el.style.opacity = v;
      }
    });
  });

  return null;
}
