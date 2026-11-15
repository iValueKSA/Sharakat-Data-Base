import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { gsap } from "gsap";
import KingdomScene from "./_components/stage/KingdomScene";
import StaticKingdom from "./_components/stage/StaticKingdom";
import { StageMedia } from "./_components/stage/StageMedia";
import { StaticRegionConnections } from "./_components/stage/StaticRegionConnections";
import { stage, setStageReduced, requestStageFrame } from "./_motion/stageState";

const REGIONS = [
  ["الرياض", 24.3, 45.3], ["مكة المكرمة", 21.7, 40.4], ["المدينة المنورة", 24.5, 39.6],
  ["المنطقة الشرقية", 25.4, 49.6], ["عسير", 18.2, 42.5], ["تبوك", 28.4, 36.6],
  ["حائل", 27.5, 41.7], ["القصيم", 26.3, 43.9], ["الحدود الشمالية", 30.0, 41.0],
  ["جازان", 16.9, 42.6], ["نجران", 17.5, 44.1], ["الباحة", 20.0, 41.5], ["الجوف", 29.9, 39.5],
];

function App() {
  const heroRef = useRef(null), titleRef = useRef(null), mediaRef = useRef(null), overlayRef = useRef(null);
  const [mode, setMode] = useState("pending"), [ready, setReady] = useState(false), [video, setVideo] = useState(false);
  const reducedQuery = useRef(null);
  const compact = window.matchMedia("(max-width: 1023.98px)").matches;
  const motion = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  useEffect(() => {
    const reducedMq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const applyReduced = () => { setStageReduced(reducedMq.matches); stage.intro = reducedMq.matches ? 1 : 0; requestStageFrame(); };
    reducedQuery.current = reducedMq; applyReduced();
    reducedMq.addEventListener("change", applyReduced);
    const isCompact = window.matchMedia("(max-width: 1023.98px)").matches;
    const region = heroRef.current, title = titleRef.current;
    const setAnchor = () => {
      const rect = region.getBoundingClientRect();
      stage.anchors.hero = { x: rect.width / 2, y: rect.height * (isCompact ? .62 : .59), w: rect.width, h: rect.height * .74 };
      requestStageFrame();
    };
    setAnchor();
    const resize = new ResizeObserver(setAnchor); resize.observe(region);
    let cancelled = false;
    const enable = () => { if (!cancelled) setMode("webgl"); };
    if (navigator.connection?.saveData || !window.WebGLRenderingContext) setMode("static");
    else if (window.requestIdleCallback) { const id = window.requestIdleCallback(enable, { timeout: 1200 }); return () => { cancelled = true; window.cancelIdleCallback(id); resize.disconnect(); reducedMq.removeEventListener("change", applyReduced); }; }
    else { const id = setTimeout(enable, 250); return () => { cancelled = true; clearTimeout(id); resize.disconnect(); reducedMq.removeEventListener("change", applyReduced); }; }
    return () => { cancelled = true; resize.disconnect(); reducedMq.removeEventListener("change", applyReduced); };
  }, []);

  useEffect(() => {
    if (!ready || mode !== "webgl" || !motion || compact || navigator.connection?.saveData) { setVideo(false); return; }
    const id = setTimeout(() => setVideo(true), 1200);
    return () => clearTimeout(id);
  }, [ready, mode, motion, compact]);

  const onReady = () => {
    if (ready) return;
    setReady(true);
    const prefersReduced = reducedQuery.current?.matches;
    if (prefersReduced) stage.intro = 1;
    else gsap.to(stage, { intro: 1, duration: 3.2, ease: "none" });
  };

  const referenceOnly = new URLSearchParams(window.location.search).get("mapReference") === "1";
  return <div className="map-hero-runtime" data-reference={referenceOnly ? "true" : "false"} data-renderer={mode} ref={heroRef}>
    <div className="reference-stage">
      <StageMedia ref={mediaRef} video={video} />
      {mode === "webgl" ? <KingdomScene lang="ar" compact={compact} frameloop={motion ? "always" : "demand"} media={mediaRef} onReady={onReady} overlayRef={overlayRef} titleRef={titleRef} heroRef={heroRef} /> : mode === "static" ? <><StaticKingdom /><StaticRegionConnections overlayRef={overlayRef} titleRef={titleRef} heroRef={heroRef} /></> : null}
      <div className="reference-vignette" aria-hidden="true" />
    </div>
    <svg ref={overlayRef} className="map-hero-connections" aria-hidden="true" focusable="false">
      {REGIONS.map(([name], i) => <g key={name} aria-label={name}>
        <title>{name}</title>
        <path data-connection={i} className="map-connection-path" pathLength="1" style={{animationDelay:`${i * 0.045}s`}} />
        <g data-pin={i} className="map-region-pin-anchor">
          <g className="map-region-pin">
            <path className="map-pin-halo" d="M 0 0 C -1.8 -2.7 -6.5 -7 -6.5 -10 A 6.5 6.5 0 1 1 6.5 -10 C 6.5 -7 1.8 -2.7 0 0 Z" />
            <path className="map-pin-ring" d="M 0 0 C -1.8 -2.7 -6.5 -7 -6.5 -10 A 6.5 6.5 0 1 1 6.5 -10 C 6.5 -7 1.8 -2.7 0 0 Z" />
            <circle className="map-pin-core" cx="0" cy="-10" r="2.2" />
          </g>
        </g>
      </g>)}
      <circle data-convergence-point="true" className="map-convergence-point" r="2" />
      <text data-ahsa-fallback-label="true" className="map-hero-city-label" textAnchor="middle" dominantBaseline="central">الأحساء</text>
    </svg>
    <h1 ref={titleRef} className="map-hero-title" id="map-hero-title">منصة فرص الاستثمار</h1>
  </div>;
}

const mount = document.getElementById("mapHeroRuntime");
if (mount) createRoot(mount).render(<App />);

