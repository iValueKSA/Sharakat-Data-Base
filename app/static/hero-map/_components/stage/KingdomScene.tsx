"use client";

import { useMemo, useRef, type RefObject } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { MAP_Y, buildConstellation, thin } from "./geo";
import { BACKGROUND, createUniforms } from "./materials";
import { CityLabels, CityNodes, Constellation, Plate, Routes } from "./KingdomLayers";
import { Beacon, Pings, SurveyField, Underglow } from "./SurveyLayers";
import { CameraRig } from "./CameraRig";
import { ProjectedConnections } from "./RegionConnections";

/**
 * The Kingdom stage: Saudi Arabia as a lit plate floating over a survey
 * field, behind the whole landing page.
 *
 * The canvas is transparent: behind it is the recorded media (StageMedia), the
 * atmosphere the map floats in.
 *
 * Layers, bottom to top — each one draw call:
 *   survey field  graticule crosses every 2°, spreading out as the stage opens
 *   underglow     light pooled around the land
 *   plate         the provinces as one thin solid, rim-lit
 *   routes        province borders, feeders, city routes (gold in the finale)
 *   constellation the points, flashing as tenders publish
 *   pings         rings where the monitoring sweep finds a tender
 *   cities        nodes; Riyadh holds its light when the rest dims
 *   beacon        Riyadh's light column while its tender is the subject
 *   labels        city names, in the page language
 *
 * Why it looks the way it does:
 *  - Depth from geometry and light, not post-processing: the gap between the
 *    plate and the field, the plate's lit edge, fog, a pool of light where
 *    the story is looking. No Bloom pass; glow is soft additive sprites.
 *  - The camera is directed, not orbited: scroll picks a pose
 *    (`poses.ts`), the rig damps toward it (`CameraRig.tsx`).
 *  - Everything the story changes is a uniform shared by every material,
 *    set once per frame by the rig (`materials.ts`, `shaders.ts`).
 */

/** Reports the first rendered frame, so the stage can retire its placeholder. */
function FirstFrame({ onReady }: { onReady: () => void }) {
  const done = useRef(false);
  useFrame(() => {
    if (done.current) return;
    done.current = true;
    onReady();
  });
  return null;
}

export default function KingdomScene({
  lang,
  compact,
  frameloop,
  media,
  onReady,
  overlayRef,
  titleRef,
  heroRef,
}: {
  lang: "ar" | "en";
  compact: boolean;
  frameloop: "always" | "demand" | "never";
  /** The recorded media layer behind the canvas (StageMedia). */
  media: RefObject<HTMLDivElement | null>;
  onReady: () => void;
  overlayRef: RefObject<SVGSVGElement | null>;
  titleRef: RefObject<HTMLElement | null>;
  heroRef: RefObject<HTMLElement | null>;
}) {
  const uniforms = useMemo(createUniforms, []);
  const labelRefs = useRef<(HTMLSpanElement | null)[]>([]);

  // Built once per density. Phones get every other point.
  const positions = useMemo(() => {
    const full = buildConstellation(900);
    return compact ? thin(full, 2) : full;
  }, [compact]);

  return (
    <Canvas
      frameloop={frameloop}
      // Capped at 1.5 (1.25 on phones): past that, retina pays four times the
      // fragments for a glow nobody can tell apart.
      dpr={[1, compact ? 1.25 : 1.5]}
      camera={{ fov: 50, near: 0.1, far: 80, position: [0, 6, 6] }}
      // Transparent: the recorded media shows through wherever the map isn't.
      gl={{ antialias: !compact, alpha: true, powerPreference: "high-performance" }}
      onCreated={({ gl }) => gl.setClearColor(BACKGROUND, 0)}
      // Purely a backdrop: nothing to click or drag, and touches must always
      // reach the page underneath. R3F writes `pointer-events: auto` inline
      // on its wrapper, so the override has to be inline too.
      style={{ pointerEvents: "none" }}
    >
      {/* First, so its frame callback runs before the layers': they read
          the uniforms it writes (e.g. to skip a draw call while dark). */}
      <CameraRig uniforms={uniforms} compact={compact} dir={lang === "ar" ? -1 : 1} labelRefs={labelRefs} media={media} />
      <ProjectedConnections overlayRef={overlayRef} titleRef={titleRef} heroRef={heroRef} />
      <group position={[0, MAP_Y, 0]}>
        <SurveyField uniforms={uniforms} />
        <Underglow uniforms={uniforms} />
        <Plate uniforms={uniforms} />
        <Routes positions={positions} uniforms={uniforms} />
        <Constellation positions={positions} uniforms={uniforms} compact={compact} />
        <Pings positions={positions} uniforms={uniforms} count={compact ? 26 : 44} />
        <CityNodes uniforms={uniforms} />
        <Beacon uniforms={uniforms} />
        <CityLabels lang={lang} labelRefs={labelRefs} />
      </group>
      <FirstFrame onReady={onReady} />
    </Canvas>
  );
}
