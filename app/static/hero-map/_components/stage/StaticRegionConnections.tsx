import { useEffect } from "react";
import { CITY_LABEL_POS, CITIES, project } from "./geo";

const REGIONS: [string, number, number][] = [
  ["الرياض", 24.3, 45.3], ["مكة المكرمة", 21.7, 40.4], ["المدينة المنورة", 24.5, 39.6],
  ["المنطقة الشرقية", 25.4, 49.6], ["عسير", 18.2, 42.5], ["تبوك", 28.4, 36.6],
  ["حائل", 27.5, 41.7], ["القصيم", 26.3, 43.9], ["الحدود الشمالية", 30, 41],
  ["جازان", 16.9, 42.6], ["نجران", 17.5, 44.1], ["الباحة", 20, 41.5], ["الجوف", 29.9, 39.5],
];

export function StaticRegionConnections({ overlayRef, titleRef, heroRef }: {
  overlayRef: React.RefObject<SVGSVGElement | null>;
  titleRef: React.RefObject<HTMLElement | null>;
  heroRef: React.RefObject<HTMLElement | null>;
}) {
  useEffect(() => {
    let raf = 0;
    const draw = () => {
      const overlay = overlayRef.current, hero = heroRef.current, title = titleRef.current;
      const map = hero?.querySelector<SVGSVGElement>(".l-stage-static-map");
      const matrix = map?.getScreenCTM();
      if (!overlay || !hero || !title || !map || !matrix) return;
      const box = hero.getBoundingClientRect(), titleBox = title.getBoundingClientRect();
      const w = box.width, h = box.height;
      overlay.setAttribute("viewBox", `0 0 ${w} ${h}`);
      const targetX = Number((((titleBox.left + titleBox.right) * 0.5) - box.left).toFixed(2));
      const targetY = Number((titleBox.bottom - box.top + 5).toFixed(2));
      const convergence = overlay.querySelector("[data-convergence-point]");
      if (convergence) {
        convergence.setAttribute("cx", String(targetX));
        convergence.setAttribute("cy", String(targetY));
      }
      const pts = REGIONS.map((region) => {
        const [x, , z] = project(region[2], region[1]);
        const point = map.createSVGPoint(); point.x = x; point.y = z;
        const screen = point.matrixTransform(matrix);
        return { x: screen.x - box.left, y: screen.y - box.top };
      });
      pts.forEach((p, i) => {
        const px = Math.max(3, Math.min(w - 3, p.x)), py = Math.max(3, Math.min(h - 3, p.y));
        const dx = targetX - px, rise = Math.max(32, py - targetY);
        const side = Math.max(-1, Math.min(1, (px - targetX) / (w * 0.5)));
        const spread = Math.min(1, Math.abs(dx) / Math.max(1, w));
        const bow = side * Math.min(52, w * 0.045) * (0.55 + spread * 0.45);
        const c1x = px + dx * 0.22 + bow;
        const c2x = targetX - dx * 0.15 + bow * 0.45;
        const c1y = py - rise * (0.46 + Math.abs(side) * 0.035);
        const c2y = targetY + rise * 0.13;
        const d = `M ${px.toFixed(1)} ${py.toFixed(1)} C ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${targetX.toFixed(2)} ${targetY.toFixed(2)}`;
        const path = overlay.querySelector(`[data-connection="${i}"]`);
        const pin = overlay.querySelector(`[data-pin="${i}"]`);
        if (path) path.setAttribute("d", d);
        if (pin) pin.setAttribute("transform", `translate(${px.toFixed(1)} ${py.toFixed(1)})`);
      });
      const ahsaIndex = CITIES.findIndex((city) => city.key === "dammam");
      const ahsaLabel = overlay.querySelector("[data-ahsa-fallback-label]");
      if (ahsaIndex >= 0 && ahsaLabel) {
        const [x, , z] = CITY_LABEL_POS[ahsaIndex];
        const point = map.createSVGPoint(); point.x = x; point.y = z;
        const screen = point.matrixTransform(matrix);
        ahsaLabel.setAttribute("x", (screen.x - box.left).toFixed(2));
        ahsaLabel.setAttribute("y", (screen.y - box.top).toFixed(2));
      }
    };
    const schedule = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(draw); };
    schedule();
    const resize = new ResizeObserver(schedule);
    if (heroRef.current) resize.observe(heroRef.current);
    if (titleRef.current) resize.observe(titleRef.current);
    window.addEventListener("resize", schedule, { passive: true });
    return () => { cancelAnimationFrame(raf); resize.disconnect(); window.removeEventListener("resize", schedule); };
  }, [overlayRef, titleRef, heroRef]);
  return null;
}
