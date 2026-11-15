"use client";

import { useMemo } from "react";
import { CITY_POS, X_SPAN, Z_SPAN, provinceRings, surveyField } from "./geo";

/**
 * The stage without WebGL: the same projected provinces, cities and survey
 * crosses as the 3D scene, drawn once as SVG and laid back in CSS
 * perspective so it keeps the scene's sense of depth. No animation — a fallback should be the most
 * reliable version of the picture, not a smaller copy of the effect.
 */
export default function StaticKingdom() {
  const paths = useMemo(
    () =>
      provinceRings().map(
        (ring) => `M${ring.map(([x, z]) => `${x.toFixed(3)} ${z.toFixed(3)}`).join("L")}Z`,
      ),
    [],
  );

  // The survey field the plate floats over in the 3D scene, as one path.
  const survey = useMemo(() => {
    const { seg } = surveyField();
    let d = "";
    for (let i = 0; i < seg.length; i += 4) {
      d += `M${seg[i].toFixed(3)} ${seg[i + 1].toFixed(3)}L${seg[i + 2].toFixed(3)} ${seg[i + 3].toFixed(3)}`;
    }
    return d;
  }, []);

  return (
    <div className="l-stage-static">
      <svg
        viewBox={`${-X_SPAN / 2} ${-Z_SPAN / 2} ${X_SPAN} ${Z_SPAN}`}
        className="l-stage-static-map"
        focusable="false"
      >
        <path d={survey} className="l-stage-static-survey" vectorEffect="non-scaling-stroke" />
        {paths.map((d, i) => (
          <path key={i} d={d} className="l-stage-static-province" vectorEffect="non-scaling-stroke" />
        ))}
        {CITY_POS.map(([x, , z], i) => (
          <circle key={i} cx={x} cy={z} r={i === 0 ? 0.07 : 0.045} className="l-stage-static-city" />
        ))}
      </svg>
    </div>
  );
}
