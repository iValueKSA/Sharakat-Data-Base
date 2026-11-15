"use client";

import { useMemo } from "react";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import {
  CITIES,
  CITY_ORDER,
  CITY_POS,
  CITY_LABEL_POS,
  PLATE_BOTTOM_Y,
  PLATE_TOP_Y,
  RIYADH,
  arcPoints,
  provinceRings,
  trunkPairs,
  type Vec3,
} from "./geo";
import {
  FLASH,
  GOLD,
  PLATE_TOP,
  PLATE_WALL,
  PLATE_WALL_DEEP,
  TEAL,
  TEAL_BRIGHT,
  additive,
  seeds,
  useDispose,
  type Uniforms,
} from "./materials";
import {
  CITY_FRAG,
  CITY_VERT,
  LINE_FRAG,
  LINE_VERT,
  PLATE_FRAG,
  PLATE_VERT,
  POINTS_FRAG,
  POINTS_VERT,
} from "./shaders";

/**
 * The Kingdom itself: the plate the land is made of, the constellation of
 * points on it, the city nodes, and the lines between them. One draw call
 * per layer.
 */

/* ── Plate ──────────────────────────────────────────────────────────── */

/**
 * Province polygons as one thin solid: triangulated top faces plus the walls
 * around every ring. Walls between provinces sit under the top faces and are
 * never seen; the coastline walls give the land its edge and thickness.
 */
function buildPlate(): THREE.BufferGeometry {
  const pos: number[] = [];
  const top: number[] = [];
  const side: number[] = [];
  const T = PLATE_TOP_Y;
  const B = PLATE_BOTTOM_Y;

  for (const ring of provinceRings()) {
    const contour = ring.map(([x, z]) => new THREE.Vector2(x, z));
    for (const tri of THREE.ShapeUtils.triangulateShape(contour, [])) {
      for (const i of tri) {
        pos.push(ring[i][0], T, ring[i][1]);
        top.push(1);
        side.push(0);
      }
    }
    for (let i = 0; i < ring.length; i++) {
      const [ax, az] = ring[i];
      const [bx, bz] = ring[(i + 1) % ring.length];
      pos.push(ax, T, az, bx, T, bz, bx, B, bz, ax, T, az, bx, B, bz, ax, B, az);
      top.push(1, 1, 0, 1, 0, 0);
      side.push(1, 1, 1, 1, 1, 1);
    }
  }

  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("aTop", new THREE.Float32BufferAttribute(top, 1));
  g.setAttribute("aSide", new THREE.Float32BufferAttribute(side, 1));
  return g;
}

export function Plate({ uniforms }: { uniforms: Uniforms }) {
  const geometry = useMemo(buildPlate, []);
  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        uniforms: {
          ...uniforms,
          uTop: { value: PLATE_TOP },
          uWall: { value: PLATE_WALL },
          uWallDeep: { value: PLATE_WALL_DEEP },
          uLight: { value: TEAL },
        },
        vertexShader: PLATE_VERT,
        fragmentShader: PLATE_FRAG,
        side: THREE.DoubleSide,
        // Blended so its far edge fades into the media behind the canvas;
        // still depth-writing, and drawn first, so the light layers test
        // against the land.
        transparent: true,
        depthWrite: true,
      }),
    [uniforms],
  );
  useDispose(geometry);
  useDispose(material);
  // Drawn before the light layers so they depth-test against the land.
  return <mesh geometry={geometry} material={material} frustumCulled={false} renderOrder={-1} />;
}

/* ── Constellation ──────────────────────────────────────────────────── */

export function Constellation({ positions, uniforms, compact }: {
  positions: Float32Array;
  uniforms: Uniforms;
  compact: boolean;
}) {
  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    g.setAttribute("aSeed", new THREE.BufferAttribute(seeds(positions.length / 3, 99), 1));
    return g;
  }, [positions]);

  const material = useMemo(
    () =>
      additive(
        uniforms,
        // Fewer, larger points on phones read as the same density.
        { uSize: { value: compact ? 44 : 36 }, uColor: { value: TEAL }, uFlashColor: { value: FLASH } },
        POINTS_VERT,
        POINTS_FRAG,
      ),
    [uniforms, compact],
  );
  useDispose(geometry);
  useDispose(material);

  return <points geometry={geometry} material={material} frustumCulled={false} />;
}

/* ── Cities ─────────────────────────────────────────────────────────── */

export function CityNodes({ uniforms }: { uniforms: Uniforms }) {
  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry();
    const pos = new Float32Array(CITY_POS.length * 3);
    CITY_POS.forEach(([x, , z], i) => pos.set([x, 0.04, z], i * 3));
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setAttribute("aSeed", new THREE.BufferAttribute(seeds(CITY_POS.length, 7), 1));
    g.setAttribute(
      "aMain",
      new THREE.BufferAttribute(new Float32Array(CITY_POS.map((_, i) => (i === 0 ? 1 : 0))), 1),
    );
    g.setAttribute("aOrder", new THREE.BufferAttribute(new Float32Array(CITY_ORDER), 1));
    return g;
  }, []);

  const material = useMemo(
    () =>
      additive(
        uniforms,
        { uSize: { value: 120 }, uColor: { value: TEAL_BRIGHT }, uGoldColor: { value: GOLD } },
        CITY_VERT,
        CITY_FRAG,
      ),
    [uniforms],
  );
  useDispose(geometry);
  useDispose(material);

  return <points geometry={geometry} material={material} frustumCulled={false} />;
}

/* ── Lines ──────────────────────────────────────────────────────────── */

const NOT_A_ROUTE = 2;

/** Arcs → one LineSegments geometry with per-vertex fade and sweep order. */
function buildLines(arcs: { pts: Vec3[]; order: number; fade: boolean }[]): THREE.BufferGeometry {
  const pos: number[] = [];
  const fade: number[] = [];
  const order: number[] = [];
  for (const { pts, order: o, fade: f } of arcs) {
    for (let i = 0; i < pts.length - 1; i++) {
      const t0 = i / (pts.length - 1);
      const t1 = (i + 1) / (pts.length - 1);
      pos.push(...pts[i], ...pts[i + 1]);
      // sin(πt): 0 at the ends, so arcs dissolve instead of stopping on a pixel.
      fade.push(f ? Math.sin(Math.PI * t0) : 1, f ? Math.sin(Math.PI * t1) : 1);
      order.push(o, o);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("aFade", new THREE.Float32BufferAttribute(fade, 1));
  g.setAttribute("aOrder", new THREE.Float32BufferAttribute(order, 1));
  return g;
}

function lineMaterial(uniforms: Uniforms, color: THREE.Color, opacity: number, focusFloor: number) {
  return additive(
    uniforms,
    {
      uOpacity: { value: opacity },
      uColor: { value: color },
      uGoldColor: { value: GOLD },
      uFlashColor: { value: FLASH },
      uFocusFloor: { value: focusFloor },
    },
    LINE_VERT,
    LINE_FRAG,
  );
}

export function Routes({ positions, uniforms }: { positions: Float32Array; uniforms: Uniforms }) {
  // Feeders: every 7th point bends toward its nearest city. Fewer and
  // fainter than the routes, so the cities read as hubs, not as the centres
  // of a web.
  const feeders = useMemo(() => {
    const arcs: { pts: Vec3[]; order: number; fade: boolean }[] = [];
    for (let i = 0; i < positions.length / 3; i += 7) {
      const p: Vec3 = [positions[i * 3], positions[i * 3 + 1], positions[i * 3 + 2]];
      let best = 0;
      let bestD = Infinity;
      CITY_POS.forEach(([cx, , cz], c) => {
        const d = (p[0] - cx) ** 2 + (p[2] - cz) ** 2;
        if (d < bestD) {
          bestD = d;
          best = c;
        }
      });
      // Long feeders are what turned the east into a fan of spokes.
      if (bestD > 1.1) continue;
      arcs.push({ pts: arcPoints(p, [CITY_POS[best][0], 0, CITY_POS[best][2]], 0.05, 0.03, 14), order: NOT_A_ROUTE, fade: true });
    }
    return buildLines(arcs);
  }, [positions]);

  // Trunks: city ↔ nearest two cities. Sweep order = distance of the route's
  // midpoint from Riyadh, normalised, so the gold spreads outward from where
  // the journey's tender was published.
  const trunks = useMemo(() => {
    const pairs = trunkPairs();
    const mids = pairs.map(([a, b]) =>
      Math.hypot(
        (CITY_POS[a][0] + CITY_POS[b][0]) / 2 - RIYADH[0],
        (CITY_POS[a][2] + CITY_POS[b][2]) / 2 - RIYADH[2],
      ),
    );
    const max = Math.max(...mids);
    return buildLines(
      pairs.map(([a, b], i) => ({
        pts: arcPoints(CITY_POS[a], CITY_POS[b], 0.18, 0.16, 26),
        order: mids[i] / max,
        fade: true,
      })),
    );
  }, []);

  // Province borders, all in one geometry, a hair above the plate.
  const outline = useMemo(() => {
    const arcs = provinceRings().map((ring) => ({
      pts: [...ring, ring[0]].map(([x, z]) => [x, PLATE_TOP_Y + 0.02, z] as Vec3),
      order: NOT_A_ROUTE,
      fade: false,
    }));
    return buildLines(arcs);
  }, []);

  const feederMat = useMemo(() => lineMaterial(uniforms, TEAL, 0.17, 0.12), [uniforms]);
  const trunkMat = useMemo(() => lineMaterial(uniforms, TEAL_BRIGHT, 0.8, 0.3), [uniforms]);
  const outlineMat = useMemo(() => lineMaterial(uniforms, TEAL, 0.42, 0.45), [uniforms]);
  useDispose(feeders);
  useDispose(trunks);
  useDispose(outline);
  useDispose(feederMat);
  useDispose(trunkMat);
  useDispose(outlineMat);

  return (
    <>
      <lineSegments geometry={outline} material={outlineMat} frustumCulled={false} />
      <lineSegments geometry={feeders} material={feederMat} frustumCulled={false} />
      <lineSegments geometry={trunks} material={trunkMat} frustumCulled={false} />
    </>
  );
}

/* ── Labels ─────────────────────────────────────────────────────────── */

/** Labelled cities, in the order their label elements are registered. */
export const LABELED = CITIES.map((c, i) => ({ c, i })).filter(({ c }) => c.labeled);

/**
 * City names as DOM text projected onto the map (drei `Html`). Pure glow
 * text, no box: a label that belongs to the light beside it, not a sticker.
 * The rig writes each label's opacity straight to the DOM.
 */
export function CityLabels({ lang, labelRefs }: {
  lang: "ar" | "en";
  labelRefs: React.MutableRefObject<(HTMLSpanElement | null)[]>;
}) {
  return (
    <group>
      {LABELED.map(({ c, i }, n) => {
        const [x, , z] = CITY_LABEL_POS[i];
        return (
          <Html key={c.key} position={[x, 0.2, z]} center zIndexRange={[2, 0]} pointerEvents="none">
            <span
              ref={(el) => {
                labelRefs.current[n] = el;
              }}
              className="l-map-label"
              lang={lang}
              dir={lang === "ar" ? "rtl" : "ltr"}
            >
              {lang === "ar" ? c.labelText?.ar ?? c.ar : c.labelText?.en ?? c.en}
            </span>
          </Html>
        );
      })}
    </group>
  );
}
