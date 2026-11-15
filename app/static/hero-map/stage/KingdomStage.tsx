"use client";

import dynamic from "next/dynamic";
import { Component, useCallback, useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { MQ, ScrollTrigger, gsap, useGSAP } from "../../_motion/gsap";
import { StageMedia } from "./StageMedia";
import { mayPlayMedia } from "./media";
import { useMediaQuery } from "../../_motion/useMediaQuery";
import {
  measureStageAnchors,
  onStageChange,
  requestStageFrame,
  resetStage,
  setStageReduced,
  stage,
} from "../../_motion/stageState";

/**
 * The fixed stage behind the landing page.
 *
 * Sections with a transparent background (hero, journey, finale) are windows
 * onto it; every other section is opaque and covers it. While nothing is
 * looking through a window the stage is hidden and its render loop stopped.
 *
 * Layers, back to front: the recorded media (StageMedia — the still, and on
 * capable desktops the loop), the live map on a transparent canvas, the
 * vignette. The media is the atmosphere the map floats in; the rig fades and
 * pushes it with the story.
 *
 * Loading order is deliberate. The still is in the server HTML, so the first
 * paint already has the atmosphere. The WebGL chunk (three, R3F, the province
 * geometry — the heaviest thing on the page) is only requested once the
 * browser is idle after first paint, and the loop only after the map's first
 * frame, on desktops that can afford it.
 *
 * Fallbacks, from most to least capable:
 *   webgl  — the full scene over the media
 *   static — an SVG of the same projected provinces, tilted in CSS 3D, over
 *            the still: used with no WebGL, with Save-Data on, or if the
 *            scene throws
 */

const KingdomScene = dynamic(() => import("./KingdomScene"), { ssr: false });
const StaticKingdom = dynamic(() => import("./StaticKingdom"), { ssr: false });

type Mode = "pending" | "webgl" | "static";

export function KingdomStage({ lang }: { lang: "ar" | "en" }) {
  const [mode, setMode] = useState<Mode>("pending");
  const [ready, setReady] = useState(false);
  const [loop, setLoop] = useState(false);
  const media = useRef<HTMLDivElement>(null);
  const visible = useSyncExternalStore(onStageChange, isVisible, alwaysTrue);
  const reduced = useSyncExternalStore(onStageChange, isReduced, alwaysFalse);
  const compact = useMediaQuery(MQ.compact);

  useEffect(() => {
    const saveData = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData;
    if (saveData || !supportsWebGL()) {
      setMode("static");
      return;
    }
    const w = window as Window & {
      requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number;
      cancelIdleCallback?: (id: number) => void;
    };
    if (w.requestIdleCallback) {
      const id = w.requestIdleCallback(() => setMode("webgl"), { timeout: 1500 });
      return () => w.cancelIdleCallback?.(id);
    }
    const id = window.setTimeout(() => setMode("webgl"), 300);
    return () => window.clearTimeout(id);
  }, []);

  useEffect(() => {
    const mq = window.matchMedia(MQ.reduce);
    const apply = () => setStageReduced(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  // The loop: desktop, full motion, the map already running, and a device and
  // connection that can afford it — requested a moment after the map's first
  // frame so it never competes with it.
  useEffect(() => {
    if (!ready || mode !== "webgl" || reduced || compact || !mayPlayMedia()) {
      setLoop(false);
      return;
    }
    const id = window.setTimeout(() => setLoop(true), 1200);
    return () => window.clearTimeout(id);
  }, [ready, mode, reduced, compact]);

  // Nothing decodes while the stage is covered; the rig resumes the loop when
  // the hero or the finale opens it again.
  useEffect(() => {
    if (visible) return;
    media.current?.querySelector("video")?.pause();
  }, [visible]);

  // The media settles back into place as the page opens — the one entrance
  // it has; it is never hidden (it is the first paint).
  useGSAP(
    () => {
      const frame = media.current?.querySelector("[data-stage-media-frame]");
      if (!frame) return;
      const mm = gsap.matchMedia();
      mm.add(MQ.motion, () => {
        gsap.fromTo(frame, { scale: 1.07 }, { scale: 1, duration: 6, ease: "power2.out" });
      });
      return () => mm.revert();
    },
    { scope: media },
  );

  // Reduced motion: the hero's map scrolls away with the hero, one frame per
  // scroll event, instead of standing still behind moving content.
  useEffect(() => {
    if (!reduced) return;
    const onScroll = () => {
      stage.heroTop = -window.scrollY;
      requestStageFrame();
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      stage.heroTop = 0;
    };
  }, [reduced]);

  // Layout anchors are re-measured whenever ScrollTrigger refreshes, which
  // is also exactly when pinned layouts settle after a resize or font load.
  useEffect(() => {
    const measure = () => measureStageAnchors();
    ScrollTrigger.addEventListener("refresh", measure);
    measure();
    return () => {
      ScrollTrigger.removeEventListener("refresh", measure);
      gsap.killTweensOf(stage);
      resetStage();
    };
  }, []);

  /**
   * First frame on screen: retire the placeholder and let the camera settle
   * from high above into the hero pose. Started from here, not on mount, so
   * a slow chunk never means the settle already happened off-screen; and
   * tweened by GSAP, not the scene clock, so a paused render loop can't
   * strand it halfway.
   */
  const onReady = useCallback(() => {
    setReady(true);
    const onHero = window.scrollY < window.innerHeight * 0.4;
    if (stage.reduced || !onHero) {
      stage.intro = 1;
      return;
    }
    gsap.to(stage, { intro: 1, duration: 3.2, ease: "none" });
  }, []);

  // Pointer parallax, for mice and trackpads only.
  useEffect(() => {
    const mq = window.matchMedia(`${MQ.finePointer} and ${MQ.motion}`);
    const onMove = (e: PointerEvent) => {
      stage.pointerX = (e.clientX / window.innerWidth) * 2 - 1;
      stage.pointerY = -((e.clientY / window.innerHeight) * 2 - 1);
    };
    const bind = () => {
      window.removeEventListener("pointermove", onMove);
      stage.pointerX = 0;
      stage.pointerY = 0;
      if (mq.matches) window.addEventListener("pointermove", onMove, { passive: true });
    };
    bind();
    mq.addEventListener("change", bind);
    return () => {
      mq.removeEventListener("change", bind);
      window.removeEventListener("pointermove", onMove);
    };
  }, []);

  const frameloop = !visible ? "never" : reduced ? "demand" : "always";

  return (
    <div
      aria-hidden="true"
      className="l-stage"
      data-visible={visible ? "true" : "false"}
      data-ready={ready || mode === "static" ? "true" : "false"}
    >
      <StageMedia ref={media} video={loop} />

      {mode === "webgl" ? (
        <SceneBoundary onError={() => setMode("static")}>
          <div className="l-stage-scene">
            <KingdomScene
              lang={lang}
              compact={compact}
              frameloop={frameloop}
              media={media}
              onReady={onReady}
            />
          </div>
        </SceneBoundary>
      ) : null}

      {mode === "static" ? <StaticKingdom /> : null}

      <div className="l-stage-vignette" />
    </div>
  );
}

/* ── Helpers ────────────────────────────────────────────────────────── */

const isVisible = () => stage.windows.size > 0;
const isReduced = () => stage.reduced;
const alwaysTrue = () => true;
const alwaysFalse = () => false;

function supportsWebGL(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

/** A WebGL context can still fail after the capability probe (lost GPU,
 *  blocklisted driver). Fall back to the SVG rather than a blank stage. */
class SceneBoundary extends Component<{ onError: () => void; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch() {
    this.props.onError();
  }

  render() {
    return this.state.failed ? null : this.props.children;
  }
}
