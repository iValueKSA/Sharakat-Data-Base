import { SAUDI_PROVINCES } from "../../saudi-provinces";

/**
 * Geometry for the Kingdom stage: the lat/lng → scene projection, the
 * constellation sample, the cities and the arcs between them.
 *
 * Pure data and maths, no three.js imports, so the static SVG fallback can
 * reuse the same projection without pulling the WebGL chunk.
 *
 * Scene axes: x runs west → east, z runs south → north as −z (so north is
 * "away" from a camera at +z), y is up. The map lies in the y = 0 plane of
 * its own group; the scene lifts the group to MAP_Y.
 */

const LNG_MIN = 34;
const LNG_MAX = 56;
const LAT_MIN = 16;
// The province data reaches 32.154°N, so a box ending at 32 left the northern
// tip poking out of its own bounds.
const LAT_MAX = 32.2;

/**
 * An equirectangular projection needs a cos(latitude) correction: away from
 * the equator a degree of longitude covers less ground than a degree of
 * latitude — at this map's centre (~24°N) only ~91% as much.
 *
 * That correction was once missing (X/Z hardcoded as 6.4/4.0, an aspect of
 * 1.60 against a true ground aspect of 1.265), which drew the country 27% too
 * wide. X_SPAN is derived from Z_SPAN so the two can never drift apart again.
 */
const DEG = Math.PI / 180;
const LAT_MID = (LAT_MIN + LAT_MAX) / 2;

export const Z_SPAN = 4.5;
export const X_SPAN =
  Z_SPAN * ((LNG_MAX - LNG_MIN) / (LAT_MAX - LAT_MIN)) * Math.cos(LAT_MID * DEG);

/** Height of the map plane in the scene. */
export const MAP_Y = 0.35;

export type Vec3 = [number, number, number];

export function project(lng: number, lat: number): Vec3 {
  const x = ((lng - LNG_MIN) / (LNG_MAX - LNG_MIN)) * X_SPAN - X_SPAN / 2;
  const z = -(((lat - LAT_MIN) / (LAT_MAX - LAT_MIN)) * Z_SPAN - Z_SPAN / 2);
  return [x, 0, z];
}

/** Cheap deterministic PRNG so the constellation is identical on every load. */
export function mulberry32(seed: number) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function pointInPolygon(x: number, y: number, poly: [number, number][]): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i][0], yi = poly[i][1];
    const xj = poly[j][0], yj = poly[j][1];
    const intersect =
      yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi + 1e-12) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

/**
 * The constellation: `total` points, a fifth sampled along the province
 * borders (weighted by edge length, so coastlines read evenly) and the rest a
 * jittered grid clipped to the provinces (uniform fill, no clumps or gaps).
 */
export function buildConstellation(total: number): Float32Array {
  const rand = mulberry32(424242);
  const out: number[] = [];

  let minLng = Infinity, maxLng = -Infinity, minLat = Infinity, maxLat = -Infinity;
  for (const p of SAUDI_PROVINCES) {
    for (const [lng, lat] of p.outline) {
      if (lng < minLng) minLng = lng;
      if (lng > maxLng) maxLng = lng;
      if (lat < minLat) minLat = lat;
      if (lat > maxLat) maxLat = lat;
    }
  }

  const borderTarget = Math.floor(total * 0.2);
  const interiorTarget = total - borderTarget;

  type Edge = { a: [number, number]; b: [number, number]; len: number };
  const edges: Edge[] = [];
  let totalLen = 0;
  for (const p of SAUDI_PROVINCES) {
    const o = p.outline;
    for (let i = 0; i < o.length; i++) {
      const a = o[i];
      const b = o[(i + 1) % o.length];
      const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
      edges.push({ a, b, len });
      totalLen += len;
    }
  }
  for (let k = 0; k < borderTarget; k++) {
    let r = rand() * totalLen;
    let chosen = edges[0];
    for (const e of edges) {
      if (r <= e.len) {
        chosen = e;
        break;
      }
      r -= e.len;
    }
    const t = rand();
    const [x, , z] = project(
      chosen.a[0] + (chosen.b[0] - chosen.a[0]) * t,
      chosen.a[1] + (chosen.b[1] - chosen.a[1]) * t,
    );
    out.push(x, (rand() - 0.5) * 0.04, z);
  }

  // Most of the bounding box is sea or neighbouring land, so oversample ~2.2×
  // and let the polygon test discard the rest.
  const step = Math.sqrt(((maxLng - minLng) * (maxLat - minLat)) / (interiorTarget * 2.2));
  const cols = Math.ceil((maxLng - minLng) / step);
  const rows = Math.ceil((maxLat - minLat) / step);
  let placed = 0;
  for (let r = 0; r < rows && placed < interiorTarget; r++) {
    for (let c = 0; c < cols && placed < interiorTarget; c++) {
      const lng = minLng + (c + 0.5) * step + (rand() - 0.5) * step * 0.8;
      const lat = minLat + (r + 0.5) * step + (rand() - 0.5) * step * 0.8;
      if (!SAUDI_PROVINCES.some((p) => pointInPolygon(lng, lat, p.outline))) continue;
      const [x, , z] = project(lng, lat);
      out.push(x, (rand() - 0.5) * 0.05, z);
      placed++;
    }
  }

  return new Float32Array(out);
}

/** Every Nth point of a constellation — the phone-density version. */
export function thin(positions: Float32Array, every: number): Float32Array {
  const n = Math.floor(positions.length / 3 / every);
  const out = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    out.set(positions.subarray(i * every * 3, i * every * 3 + 3), i * 3);
  }
  return out;
}

/** Province outlines as flat [x, z] rings in scene units. */
export function provinceRings(): [number, number][][] {
  return SAUDI_PROVINCES.filter((p) => p.outline.length >= 3).map((p) =>
    p.outline.map(([lng, lat]) => {
      const [x, , z] = project(lng, lat);
      return [x, z] as [number, number];
    }),
  );
}

/* ── Cities ─────────────────────────────────────────────────────────── */

export type City = {
  key: string;
  ar: string;
  en: string;
  lng: number;
  lat: number;
  /**
   * Only labelled cities get text; every city keeps its node. The minor
   * member of each near-neighbour pair (Arar/Sakaka, Bahah, Jazan) stays
   * unlabelled or the labels stack illegibly.
   */
  labeled?: boolean;
  /** Scene-space label nudge [dx, dz] for Jeddah/Mecca, which nearly touch. */
  labelOffset?: [number, number];
  /** Presentation-only hero label override; city identity and coordinates stay unchanged. */
  labelText?: { ar: string; en: string };
  /** Presentation-only [longitude, latitude] label anchor, independent from the city node. */
  labelLngLat?: [number, number];
};

/** Riyadh is first: the journey's tender is published there. */
export const CITIES: City[] = [
  { key: "riyadh", ar: "الرياض", en: "Riyadh", lng: 46.6753, lat: 24.7136, labeled: true },
  { key: "jeddah", ar: "جدة", en: "Jeddah", lng: 39.1925, lat: 21.4858, labeled: true, labelOffset: [-0.2, 0.06] },
  { key: "mecca", ar: "مكة", en: "Makkah", lng: 39.8262, lat: 21.4225, labeled: true, labelOffset: [0.22, 0.12] },
  { key: "madinah", ar: "المدينة", en: "Madinah", lng: 39.5692, lat: 24.5247, labeled: true },
  { key: "dammam", ar: "الدمام", en: "Dammam", lng: 50.0888, lat: 26.4207, labeled: true, labelText: { ar: "الأحساء", en: "Al-Ahsa" }, labelLngLat: [49.588981, 25.36268], labelOffset: [-0.06, -0.03] },
  { key: "abha", ar: "أبها", en: "Abha", lng: 42.505, lat: 18.2164, labeled: true },
  { key: "tabuk", ar: "تبوك", en: "Tabuk", lng: 36.5662, lat: 28.3835, labeled: true },
  { key: "hail", ar: "حائل", en: "Hail", lng: 41.6873, lat: 27.5114, labeled: true },
  { key: "buraydah", ar: "بريدة", en: "Buraydah", lng: 43.973, lat: 26.326, labeled: true },
  { key: "sakaka", ar: "سكاكا", en: "Sakaka", lng: 40.2064, lat: 29.9697 },
  { key: "arar", ar: "عرعر", en: "Arar", lng: 41.0231, lat: 30.9753 },
  { key: "bahah", ar: "الباحة", en: "Al Bahah", lng: 41.4677, lat: 20.0129 },
  { key: "najran", ar: "نجران", en: "Najran", lng: 44.1277, lat: 17.4924, labeled: true },
  { key: "jazan", ar: "جازان", en: "Jazan", lng: 42.5511, lat: 16.8892 },
];

export const CITY_POS: Vec3[] = CITIES.map((c) => project(c.lng, c.lat));
/** Display-only label positions; city nodes, routes, and source coordinates use CITY_POS. */
export const CITY_LABEL_POS: Vec3[] = CITIES.map((c, i) => {
  const [x, y, z] = c.labelLngLat ? project(c.labelLngLat[0], c.labelLngLat[1]) : CITY_POS[i];
  const [dx, dz] = c.labelOffset ?? [0, 0];
  return [x + dx, y, z + dz];
});

/** Scene position of Riyadh on the lifted map plane. */
export const RIYADH: Vec3 = [CITY_POS[0][0], MAP_Y, CITY_POS[0][2]];
export const MAP_CENTER: Vec3 = [0, MAP_Y, 0.1];

/* ── Arcs ───────────────────────────────────────────────────────────── */

/** Each city joined to its two nearest neighbours, deduplicated. */
export function trunkPairs(): [number, number][] {
  const keys = new Set<string>();
  const pairs: [number, number][] = [];
  for (let i = 0; i < CITY_POS.length; i++) {
    const a = CITY_POS[i];
    const near = CITY_POS.map((b, j) => ({ j, d2: (a[0] - b[0]) ** 2 + (a[2] - b[2]) ** 2 }))
      .filter(({ j }) => j !== i)
      .sort((u, v) => u.d2 - v.d2)
      .slice(0, 2);
    for (const { j } of near) {
      const lo = Math.min(i, j);
      const hi = Math.max(i, j);
      const key = `${lo}-${hi}`;
      if (keys.has(key)) continue;
      keys.add(key);
      pairs.push([lo, hi]);
    }
  }
  return pairs;
}

/**
 * Sample a quadratic arc between two scene points, bowed sideways by `curve`
 * and upward by `lift`. Returns `samples + 1` points.
 */
export function arcPoints(a: Vec3, b: Vec3, curve: number, lift: number, samples: number): Vec3[] {
  const dx = b[0] - a[0];
  const dz = b[2] - a[2];
  const len = Math.hypot(dx, dz) || 1;
  const c: Vec3 = [
    (a[0] + b[0]) / 2 + (-dz / len) * curve,
    (a[1] + b[1]) / 2 + lift,
    (a[2] + b[2]) / 2 + (dx / len) * curve,
  ];
  const pts: Vec3[] = [];
  for (let i = 0; i <= samples; i++) {
    const t = i / samples;
    const u = 1 - t;
    pts.push([
      u * u * a[0] + 2 * u * t * c[0] + t * t * b[0],
      u * u * a[1] + 2 * u * t * c[1] + t * t * b[1],
      u * u * a[2] + 2 * u * t * c[2] + t * t * b[2],
    ]);
  }
  return pts;
}

/** Each city's place in the finale's gold sweep: its distance from Riyadh, 0 … 1. */
export const CITY_ORDER: number[] = (() => {
  const d = CITY_POS.map(([x, , z]) => Math.hypot(x - CITY_POS[0][0], z - CITY_POS[0][2]));
  const max = Math.max(...d);
  return d.map((v) => v / max);
})();

/* ── Layers under and on the land ───────────────────────────────────── */

/** The Kingdom plate: its top face sits just under the points and borders. */
export const PLATE_TOP_Y = -0.07;
export const PLATE_BOTTOM_Y = -0.2;
/** The survey field floats this far below the plate — the stage's depth gap. */
export const SURVEY_Y = -0.38;

/** Scene-x beyond which a scan front is clear of the land on either side. */
export const SCAN_REACH = X_SPAN / 2 + 0.45;

/**
 * The survey field: graticule crosses every 2° of latitude and longitude
 * (longer arms every 10°), plus the 20°/30° N and 40°/50° E lines themselves.
 * Returned as flat line segments [x0, z0, x1, z1] with a per-segment weight.
 * Long lines are cut into short pieces so the per-vertex fades stay smooth.
 */
export function surveyField(): { seg: number[]; weight: number[] } {
  const seg: number[] = [];
  const weight: number[] = [];
  const push = (a: Vec3, b: Vec3, w: number) => {
    seg.push(a[0], a[2], b[0], b[2]);
    weight.push(w);
  };

  for (let lng = 26; lng <= 64; lng += 2) {
    for (let lat = 6; lat <= 42; lat += 2) {
      const major = lng % 10 === 0 && lat % 10 === 0;
      const [x, , z] = project(lng, lat);
      const arm = major ? 0.11 : 0.05;
      const w = major ? 1 : 0.62;
      push([x - arm, 0, z], [x + arm, 0, z], w);
      push([x, 0, z - arm], [x, 0, z + arm], w);
    }
  }

  const line = (a: Vec3, b: Vec3) => {
    const n = Math.ceil(Math.hypot(b[0] - a[0], b[2] - a[2]) / 0.2);
    for (let i = 0; i < n; i++) {
      const t0 = i / n;
      const t1 = (i + 1) / n;
      push(
        [a[0] + (b[0] - a[0]) * t0, 0, a[2] + (b[2] - a[2]) * t0],
        [a[0] + (b[0] - a[0]) * t1, 0, a[2] + (b[2] - a[2]) * t1],
        0.2,
      );
    }
  };
  for (const lat of [20, 30]) line(project(26, lat), project(64, lat));
  for (const lng of [40, 50]) line(project(lng, 6), project(lng, 42));

  return { seg, weight };
}

/**
 * Where the monitoring sweep "finds" tenders: points of the constellation,
 * drawn more often near cities — public tenders cluster where people are.
 * Deterministic, so the same places ping on every load.
 */
export function pingSites(positions: Float32Array, count: number): { center: Float32Array; seed: Float32Array } {
  const rand = mulberry32(1337);
  const n = positions.length / 3;
  const taken = new Set<number>();
  const center: number[] = [];
  const seed: number[] = [];
  for (let guard = 0; center.length / 3 < count && guard < count * 400; guard++) {
    const i = Math.floor(rand() * n);
    if (taken.has(i)) continue;
    const x = positions[i * 3];
    const z = positions[i * 3 + 2];
    let d = Infinity;
    for (const [cx, , cz] of CITY_POS) d = Math.min(d, Math.hypot(x - cx, z - cz));
    if (rand() > 0.2 + 0.8 * Math.exp(-d * 2.4)) continue;
    taken.add(i);
    center.push(x, PLATE_TOP_Y + 0.012, z);
    seed.push(rand());
  }
  return { center: new Float32Array(center), seed: new Float32Array(seed) };
}
