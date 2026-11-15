# Supplied map hero reference inspection

Date: 2026-11-09

## Archive and source availability

Inspected `C:\Users\QusaiAbdElhalim\Downloads\landing-page-code.zip` directly. The archive contains the actual landing-page source for `KingdomStage`, `KingdomScene`, `KingdomLayers`, `SurveyLayers`, `CameraRig`, `geo`, `materials`, `shaders`, `poses`, `stageState`, `StageMedia`, `StaticKingdom`, `saudi-provinces`, and landing CSS, plus landscape/portrait AVIF/WebP art and a 10-second WebM/MP4 survey loop. It does not contain a package manifest/lockfile or explicit LICENSE/NOTICE file.

## Original map and effects

The live reference is a transparent Three.js scene rendered through React Three Fiber. It is not Leaflet and not an SVG. The scene layers an extruded 13-province Saudi plate, illuminated province routes, a 2-degree survey graticule, soft additive underglow, a 900-point deterministic constellation, shader-driven point flashes, sweep-reveal and monitoring scan, sweep-triggered pings, city lights/labels, and a Riyadh beacon. Custom vertex/fragment shaders carry the material, edge/rim, route, point, grid, glow and scan effects. Perspective comes from the directed damped camera rig, with fine-pointer parallax and a small ambient camera breath.

`KingdomStage` lazy-loads WebGL after idle, starts the hero reveal only after the first rendered frame (3.2 seconds, linear), and overlays an art-directed still. On capable desktop it starts the included 10-second survey loop after 1.2 seconds, synchronized to the map scan. On reduced-motion, compact/mobile, save-data or WebGL failure, it renders the supplied `StaticKingdom` fallback over the still. Motion and the render loop are gated by reduced-motion and visibility. The motion spec explicitly rejects travelling light packets on arcs, a rotating radar sweep, and post-processing bloom; it instead uses source-directed scans, points/pings, geometry, fog, rim lighting and soft additive sprites.

The stage is a full-page shared visual and the original supplied landing hero also contains paragraphs, CTAs and facts. This platform adaptation must retain only the requested title, map and region pins/curved title connections while placing the stage in the existing first-screen hero and leaving the existing page below intact. The supplied geometry is adapted to the 13 pins. The map itself stays the supplied map artwork and renderer.

## Reuse and dependency notes

The user supplied the archive and explicitly requests its integration. The archive contains no explicit license for the reference-specific source/art, so no separate grant beyond that user-provided authorization was found in the archive. The rendering dependencies are third-party packages and their notices must accompany the bundled runtime. Official package/repository records identify React, Three.js, React Three Fiber and Drei as MIT-licensed. Only the dependency subset needed for the isolated map runtime should be bundled. The original app remains HTML/CSS/JavaScript; no platform-wide React/Next.js migration is required.

## Existing implementation identified for replacement

The prior hero is `app/static/national-map-hero.svg` with `app/static/national-map-hero.css` and markup in `app/static/index.html`. The SVG's fixed trunk/bus connectors are not part of the source implementation. The isolated frontend integration should replace that art/runtime only; preserve the title, existing page content below, app navigation, platform API and all business functionality.

## Pre-change gate

This inspection was completed before changing platform source. A fresh live frontend image/files/config backup and exact image digest will be recorded before the implementation is edited or deployed. Deployment will target only the frontend service.
