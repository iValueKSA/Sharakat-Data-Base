import { useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { MAP_Y, project } from "./geo";

const REGIONS: [string, number, number][] = [
  ["الرياض", 24.3, 45.3], ["مكة المكرمة", 21.7, 40.4], ["المدينة المنورة", 24.5, 39.6],
  ["المنطقة الشرقية", 25.4, 49.6], ["عسير", 18.2, 42.5], ["تبوك", 28.4, 36.6],
  ["حائل", 27.5, 41.7], ["القصيم", 26.3, 43.9], ["الحدود الشمالية", 30, 41],
  ["جازان", 16.9, 42.6], ["نجران", 17.5, 44.1], ["الباحة", 20, 41.5], ["الجوف", 29.9, 39.5],
];

export function ProjectedConnections({ overlayRef, titleRef, heroRef }: {
  overlayRef: React.RefObject<SVGSVGElement | null>;
  titleRef: React.RefObject<HTMLElement | null>;
  heroRef: React.RefObject<HTMLElement | null>;
}) {
  const { camera } = useThree();
  const vectors = useMemo(() => REGIONS.map((r) => {
    const [x, , z] = project(r[2], r[1]);
    return new THREE.Vector3(x, MAP_Y + 0.045, z);
  }), []);
  useFrame(() => {
    const svg = overlayRef.current, hero = heroRef.current, title = titleRef.current;
    if (!svg || !hero || !title) return;
    const box = hero.getBoundingClientRect(), titleBox = title.getBoundingClientRect();
    const w = box.width, h = box.height;
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    const endY = Math.max(8, titleBox.bottom - box.top + 3);
    const projected = vectors.map((v, i) => ({ i, p: v.clone().project(camera) }));
    const ranks = new Array<number>(vectors.length);
    projected.slice().sort((a, b) => a.p.x - b.p.x).forEach((point, rank) => { ranks[point.i] = rank; });
    const titleLeft = Math.max(0, titleBox.left - box.left);
    const titleWidth = titleBox.width;
    vectors.forEach((v, i) => {
      const point = v.clone().project(camera);
      const x = (point.x * 0.5 + 0.5) * w;
      const y = (-point.y * 0.5 + 0.5) * h;
      const px = Math.max(4, Math.min(w - 4, x));
      const py = Math.max(4, Math.min(h - 4, y));
      const targetX = titleLeft + titleWidth * (0.08 + (ranks[i] / (vectors.length - 1)) * 0.84);
      const targetY = endY;
      const dx = targetX - px;
      const arch = Math.max(38, Math.min(105, (py - targetY) * 0.24));
      const d = `M ${px.toFixed(1)} ${py.toFixed(1)} C ${(px + dx * 0.28).toFixed(1)} ${(py - arch).toFixed(1)}, ${(targetX - dx * 0.22).toFixed(1)} ${(targetY + arch * 0.2).toFixed(1)}, ${targetX.toFixed(1)} ${targetY.toFixed(1)}`;
      const path = svg.querySelector(`[data-connection="${i}"]`);
      const pin = svg.querySelector(`[data-pin="${i}"]`);
      if (path) path.setAttribute("d", d);
      if (pin) pin.setAttribute("transform", `translate(${px.toFixed(1)} ${py.toFixed(1)})`);
    });
  });
  return null;
}

import { useThree } from "@react-three/fiber";
