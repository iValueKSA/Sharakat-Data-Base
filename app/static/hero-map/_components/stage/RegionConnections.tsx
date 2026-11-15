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
    const targetX = Number((((titleBox.left + titleBox.right) * 0.5) - box.left).toFixed(2));
    const targetY = Number((titleBox.bottom - box.top + 5).toFixed(2));
    const convergence = svg.querySelector("[data-convergence-point]");
    if (convergence) {
      convergence.setAttribute("cx", String(targetX));
      convergence.setAttribute("cy", String(targetY));
    }
    vectors.forEach((v, i) => {
      const point = v.clone().project(camera);
      const x = (point.x * 0.5 + 0.5) * w;
      const y = (-point.y * 0.5 + 0.5) * h;
      const px = Math.max(4, Math.min(w - 4, x));
      const py = Math.max(4, Math.min(h - 4, y));
      const dx = targetX - px;
      const rise = Math.max(42, py - targetY);
      const side = Math.max(-1, Math.min(1, (px - targetX) / (w * 0.5)));
      const spread = Math.min(1, Math.abs(dx) / Math.max(1, w));
      const bow = side * Math.min(52, w * 0.045) * (0.55 + spread * 0.45);
      const c1x = px + dx * 0.22 + bow;
      const c2x = targetX - dx * 0.15 + bow * 0.45;
      const c1y = py - rise * (0.46 + Math.abs(side) * 0.035);
      const c2y = targetY + rise * 0.13;
      const d = `M ${px.toFixed(1)} ${py.toFixed(1)} C ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${targetX.toFixed(2)} ${targetY.toFixed(2)}`;
      const path = svg.querySelector(`[data-connection="${i}"]`);
      const pin = svg.querySelector(`[data-pin="${i}"]`);
      if (path) path.setAttribute("d", d);
      if (pin) pin.setAttribute("transform", `translate(${px.toFixed(1)} ${py.toFixed(1)})`);
    });
  });
  return null;
}

import { useThree } from "@react-three/fiber";
