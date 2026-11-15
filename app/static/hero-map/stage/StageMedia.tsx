"use client";

import { forwardRef, useEffect, useRef } from "react";
import { MEDIA, PORTRAIT_MEDIA, srcSet } from "./media";

/**
 * The hero's recorded layer, behind the live map: the art-directed still
 * (always — it is the first paint, the poster, the reduced-motion and
 * no-WebGL picture) and, on capable desktops, the loop over it.
 *
 * The stage's camera rig drives this layer's opacity and push-in with the
 * story (`data-stage-media`), and starts the loop in step with the map's own
 * sweep; see CameraRig. Arabic mirrors the frame (CSS), so the scan and the
 * warm horizon follow the reading direction and the map's side.
 */
export const StageMedia = forwardRef<HTMLDivElement, { video: boolean }>(function StageMedia({ video }, ref) {
  const { landscape: L, portrait: P } = MEDIA;
  return (
    <div ref={ref} className="l-stage-media" data-stage-media>
      <div className="l-stage-media-frame" data-stage-media-frame>
        <picture>
          <source media={PORTRAIT_MEDIA} type="image/avif" srcSet={srcSet(P.base, P.widths, "avif")} sizes="100vw" />
          <source media={PORTRAIT_MEDIA} type="image/webp" srcSet={srcSet(P.base, P.widths, "webp")} sizes="100vw" />
          <source type="image/avif" srcSet={srcSet(L.base, L.widths, "avif")} sizes="100vw" />
          {/* A plain <picture>, not next/image: these are pre-encoded AVIF/WebP
              renders, and the source switch is by aspect ratio (art direction). */}
          <img
            className="l-stage-still"
            src={L.fallback}
            srcSet={srcSet(L.base, L.widths, "webp")}
            sizes="100vw"
            width={2560}
            height={1440}
            alt=""
            decoding="async"
            fetchPriority="high"
          />
        </picture>
        {video ? <StageLoop /> : null}
      </div>
    </div>
  );
});

/**
 * The loop, mounted only when allowed. It loads, seeks to the still's moment
 * and waits there, invisible (`data-state="ready"`): the rig shows it and
 * presses play when the map's sweep reaches the same moment, so the swap from
 * still to video is frame-identical and the two scans run as one.
 *
 * Muted, inline and looping, without the `autoplay` attribute: the start is
 * programmatic so it can be in step (muted playback needs no gesture).
 */
function StageLoop() {
  const ref = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    // React does not reflect `muted` as an attribute; set the property
    // before any playback is attempted.
    v.muted = true;
    const seek = () => {
      v.currentTime = MEDIA.stillAt;
    };
    const ready = () => {
      if (v.dataset.state === "loading") v.dataset.state = "ready";
    };
    if (v.readyState >= 1) seek();
    else v.addEventListener("loadedmetadata", seek, { once: true });
    v.addEventListener("seeked", ready, { once: true });
    return () => {
      v.removeEventListener("loadedmetadata", seek);
      v.removeEventListener("seeked", ready);
      v.pause();
    };
  }, []);

  return (
    <video
      ref={ref}
      className="l-stage-video"
      data-state="loading"
      muted
      loop
      playsInline
      preload="auto"
      disablePictureInPicture
      disableRemotePlayback
      tabIndex={-1}
    >
      <source src={MEDIA.video.webm} type='video/webm; codecs="vp9"' />
      <source src={MEDIA.video.mp4} type="video/mp4" />
    </video>
  );
}
