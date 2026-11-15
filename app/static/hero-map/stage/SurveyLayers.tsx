"use client";

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { PLATE_TOP_Y, RIYADH, SURVEY_Y, X_SPAN, Z_SPAN, pingSites, surveyField } from "./geo";
import { FLASH, GOLD, SURVEY, TEAL, TEAL_BRIGHT, additive, useDispose, type Uniforms } from "./materials";
import {
  BEACON_FRAG,
  BEACON_VERT,
  GLOW_FRAG,
  GLOW_VERT,
  HALO_FRAG,
  PING_FRAG,
  PING_VERT,
  SURVEY_FRAG,
  SURVEY_VERT,
} from "./shaders";

/**
 * Everything around the land: the survey field it floats over, the light
 * pooled beneath it, the rings where the monitoring sweep finds tenders, and
 * Riyadh's beacon. Each is one draw call.
 */

/**
 * Hides a layer whose light is fully off, so it costs no draw call at all
 * (the beacon is dark except in the journey; the pings except while the
 * sweep runs and in the finale).
 */
function useLitWhen<T extends THREE.Object3D>(lit: () => boolean) {
  const ref = useRef<T>(null);
  useFrame(() => {
    if (ref.current) ref.current.visible = lit();
  });
  return ref;
}

/** Graticule crosses on a plane below the plate. */
export function SurveyField({ uniforms }: { uniforms: Uniforms }) {
  const geometry = useMemo(() => {
    const { seg, weight } = surveyField();
    const pos = new Float32Array((seg.length / 4) * 6);
    const w = new Float32Array((seg.length / 4) * 2);
    for (let i = 0; i < seg.length / 4; i++) {
      pos.set([seg[i * 4], 0, seg[i * 4 + 1], seg[i * 4 + 2], 0, seg[i * 4 + 3]], i * 6);
      w[i * 2] = weight[i];
      w[i * 2 + 1] = weight[i];
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setAttribute("aWeight", new THREE.BufferAttribute(w, 1));
    return g;
  }, []);
  const material = useMemo(
    () => additive(uniforms, { uColor: { value: SURVEY }, uOpacity: { value: 0.34 } }, SURVEY_VERT, SURVEY_FRAG),
    [uniforms],
  );
  useDispose(geometry);
  useDispose(material);
  return <lineSegments geometry={geometry} material={material} position={[0, SURVEY_Y, 0]} frustumCulled={false} />;
}

/**
 * Soft light pooled on the survey plane under the Kingdom, so the plate
 * reads as lit from below its edge — a halo around the land, not a stain on it.
 */
export function Underglow({ uniforms }: { uniforms: Uniforms }) {
  const geometry = useMemo(() => new THREE.PlaneGeometry(X_SPAN * 1.7, Z_SPAN * 1.9), []);
  const material = useMemo(
    () => additive(uniforms, { uColor: { value: TEAL }, uStrength: { value: 0.2 } }, GLOW_VERT, GLOW_FRAG),
    [uniforms],
  );
  useDispose(geometry);
  useDispose(material);
  return (
    <mesh
      geometry={geometry}
      material={material}
      rotation-x={-Math.PI / 2}
      position={[0, SURVEY_Y - 0.01, 0.1]}
      frustumCulled={false}
    />
  );
}

/** Expanding rings on the land where the sweep has just found a tender. */
export function Pings({ positions, uniforms, count }: {
  positions: Float32Array;
  uniforms: Uniforms;
  count: number;
}) {
  const geometry = useMemo(() => {
    const { center, seed } = pingSites(positions, count);
    // Distance from Riyadh, normalised: the order the finale's gold arrives.
    const order = new Float32Array(seed.length);
    for (let i = 0; i < seed.length; i++) {
      order[i] = Math.hypot(center[i * 3] - RIYADH[0], center[i * 3 + 2] - RIYADH[2]);
    }
    const far = Math.max(...order);
    for (let i = 0; i < order.length; i++) order[i] /= far;
    const base = new THREE.PlaneGeometry(1, 1);
    const g = new THREE.InstancedBufferGeometry();
    g.index = base.index;
    g.setAttribute("position", base.getAttribute("position"));
    g.setAttribute("uv", base.getAttribute("uv"));
    g.setAttribute("aCenter", new THREE.InstancedBufferAttribute(center, 3));
    g.setAttribute("aSeed", new THREE.InstancedBufferAttribute(seed, 1));
    g.setAttribute("aOrder", new THREE.InstancedBufferAttribute(order, 1));
    g.instanceCount = seed.length;
    return g;
  }, [positions, count]);
  const material = useMemo(
    () =>
      additive(
        uniforms,
        { uColor: { value: TEAL_BRIGHT }, uFlashColor: { value: FLASH }, uGoldColor: { value: GOLD } },
        PING_VERT,
        PING_FRAG,
        THREE.DoubleSide,
      ),
    [uniforms],
  );
  useDispose(geometry);
  useDispose(material);
  const ref = useLitWhen<THREE.Mesh>(() => uniforms.uSweep.value > 0.001 || uniforms.uHandled.value > 0.001);
  return <mesh ref={ref} geometry={geometry} material={material} frustumCulled={false} />;
}

/**
 * Riyadh's light: a column rising out of the city, and the pool it throws on
 * the land. Shown while the journey's tender is the subject (`uBeacon`).
 */
export function Beacon({ uniforms }: { uniforms: Uniforms }) {
  const column = useMemo(() => new THREE.PlaneGeometry(1, 1), []);
  const pool = useMemo(() => new THREE.PlaneGeometry(0.9, 0.9), []);
  const columnMat = useMemo(
    () =>
      additive(
        uniforms,
        {
          uColor: { value: TEAL_BRIGHT },
          uBase: { value: new THREE.Vector3(RIYADH[0], PLATE_TOP_Y, RIYADH[2]) },
          uWidth: { value: 0.16 },
          uHeight: { value: 1.5 },
        },
        BEACON_VERT,
        BEACON_FRAG,
        THREE.DoubleSide,
      ),
    [uniforms],
  );
  const poolMat = useMemo(
    () => additive(uniforms, { uColor: { value: TEAL } }, GLOW_VERT, HALO_FRAG),
    [uniforms],
  );
  useDispose(column);
  useDispose(pool);
  useDispose(columnMat);
  useDispose(poolMat);
  const ref = useLitWhen<THREE.Group>(() => uniforms.uBeacon.value > 0.003);
  return (
    <group ref={ref}>
      <mesh
        geometry={pool}
        material={poolMat}
        rotation-x={-Math.PI / 2}
        position={[RIYADH[0], PLATE_TOP_Y + 0.01, RIYADH[2]]}
        frustumCulled={false}
      />
      <mesh geometry={column} material={columnMat} frustumCulled={false} />
    </group>
  );
}
