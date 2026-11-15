import { useEffect } from "react";
import * as THREE from "three";
import { RIYADH, mulberry32 } from "./geo";

/**
 * The stage's palette, its shared story uniforms and the material helpers
 * every layer uses. One uniforms object is shared by every material, so the
 * rig sets each value once per frame and the whole map follows.
 */

export const TEAL = new THREE.Color("#28E0D6");
export const TEAL_BRIGHT = new THREE.Color("#2FF0E2");
export const FLASH = new THREE.Color("#E6FFFC");
export const GOLD = new THREE.Color("#E3C98A");
export const SURVEY = new THREE.Color("#5FA9B4");

export const BACKGROUND = "#0B1420";
export const PLATE_TOP = new THREE.Color("#0E1C29");
export const PLATE_WALL = new THREE.Color("#15404A");
export const PLATE_WALL_DEEP = new THREE.Color("#09121B");

export type Uniforms = {
  uTime: { value: number };
  uPixelRatio: { value: number };
  uDim: { value: number };
  uFocus: { value: number };
  uFocusPos: { value: THREE.Vector3 };
  uSpark: { value: number };
  uGold: { value: number };
  uFogNear: { value: number };
  uFogFar: { value: number };
  /** Reading direction of every scan: +1 west → east, −1 east → west. */
  uDir: { value: number };
  /** The reveal front's scene-x, and whether its edge is still lit. */
  uRevealX: { value: number };
  uRevealOn: { value: number };
  /** The monitoring sweep's scene-x, strength, speed and pass number. */
  uSweepX: { value: number };
  uSweep: { value: number };
  uSweepSpeed: { value: number };
  uPass: { value: number };
  /** The survey field spreading out as the stage opens, 0 … 1. */
  uGrid: { value: number };
  /** Riyadh's light column, 0 … 1. */
  uBeacon: { value: number };
  /** Finale: the "handled" gold spreading over the tender sites, 0 … 1. */
  uHandled: { value: number };
  /** How present the recorded media behind the canvas is, 0 … 1. */
  uMedia: { value: number };
};

export function createUniforms(): Uniforms {
  return {
    uTime: { value: 0 },
    uPixelRatio: { value: 1 },
    uDim: { value: 1 },
    uFocus: { value: 0 },
    // Local to the map group, which is lifted to MAP_Y.
    uFocusPos: { value: new THREE.Vector3(RIYADH[0], 0, RIYADH[2]) },
    uSpark: { value: 0 },
    uGold: { value: 0 },
    uFogNear: { value: 6 },
    uFogFar: { value: 14 },
    uDir: { value: 1 },
    uRevealX: { value: 99 },
    uRevealOn: { value: 0 },
    uSweepX: { value: -99 },
    uSweep: { value: 0 },
    uSweepSpeed: { value: 1 },
    uPass: { value: 0 },
    uGrid: { value: 1 },
    uBeacon: { value: 0 },
    uHandled: { value: 0 },
    uMedia: { value: 0 },
  };
}

/** Additive, depth-tested, not depth-writing: light, not matter. */
export function additive(
  uniforms: Uniforms,
  own: Record<string, { value: unknown }>,
  vertexShader: string,
  fragmentShader: string,
  side: THREE.Side = THREE.FrontSide,
) {
  return new THREE.ShaderMaterial({
    uniforms: { ...uniforms, ...own },
    vertexShader,
    fragmentShader,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    side,
  });
}

/** Same seed as the constellation so point flashes are stable across loads. */
export function seeds(count: number, seed: number): Float32Array {
  const rand = mulberry32(seed);
  const out = new Float32Array(count);
  for (let i = 0; i < count; i++) out[i] = rand();
  return out;
}

/** Frees a geometry or material when it is replaced or the scene unmounts. */
export function useDispose(resource: { dispose: () => void }) {
  useEffect(() => () => resource.dispose(), [resource]);
}
