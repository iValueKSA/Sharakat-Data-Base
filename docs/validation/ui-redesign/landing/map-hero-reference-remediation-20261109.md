# Saudi map hero reference restoration

Date: 2026-11-09  
Live URL: http://localhost:8080/  
Status: **PASS — local frontend deployment**

## Reference implementation

- **REFERENCE_CODE_INSPECTED:** Yes. Inspected `landing-page-code.zip` source and assets before editing platform files. See [the source inspection](REFERENCE-IMPLEMENTATION-INSPECTION-20261109.md).
- **ORIGINAL_MAP_COMPONENT_IDENTIFIED:** `KingdomStage` / `KingdomScene`, with `KingdomLayers`, `SurveyLayers`, `CameraRig`, `geo`, `materials`, `shaders`, `poses`, `StageMedia`, and `StaticKingdom`.
- **REFERENCE_EFFECTS_REUSED:** Three.js / React Three Fiber geometry and shaders, 13-province extruded map plate, survey graticule, illuminated boundaries/routes, constellation and point flashes, reveal/monitoring scan, pings, city lights/labels, Riyadh beacon, damped perspective camera/parallax, art-directed still, and synchronized desktop WebM loop. The app itself remains HTML/CSS/JavaScript with this renderer mounted in isolation.
- **MAP_GEOMETRY_FIDELITY:** Reuses the supplied reference region polygons and projection. No Leaflet or generated map SVG is used for the live WebGL map.
- **MAP_COLOR_FIDELITY:** Reuses the reference palette and shader materials (navy background, teal survey/edge light, pale flashes, muted gold route accent).
- **MAP_ANIMATIONS:** Desktop browser showed the reference WebM in `playing` state while the scan ran. The mobile layout intentionally uses the supplied still, as in the reference behavior. Reduced-motion validation kept a single-frame map, 13 pins and 13 connections, omitted video, and reduced the connection animation to 0.00001 seconds.
- **THIRTEEN_REGION_PINS:** Exactly 13. Region representative coordinates are projected each frame from the same map geometry; the pins remain attached while camera framing changes. These are presentation points, not official administrative centroid data.
- **CURVED_CONNECTION_LINES / TITLE_CONNECTION:** Exactly 13 cubic Bézier paths, sorted by screen position to avoid the old wiring/bus appearance. The paths draw in with staggered timing and terminate immediately below the title `منصة الفرص الاستثمارية`. The reference animation spec rejects traveling light packets on arcs; its map scan, flashes and pings remain the moving-light effects.
- **ORIGINAL_CONTENT_PRESERVED:** Only the existing hero markup was replaced. Fixed right navigation and overview/dashboard content below it remain in their existing order and rendering. The transition screenshot confirms the overview starts below the hero.

The supplied archive has no explicit license file for its reference-specific code or media; reuse follows the user's explicit instruction to use the supplied source. Packaged notices for the third-party runtime dependencies are included in `app/static/hero-map/THIRD-PARTY-LICENSES.txt`.

## Validation

- Desktop 1440×900: visible reference map and media, title, 13 pins, 13 paths, and no horizontal overflow.
- Mobile 390×844: visible reference map, title, 13 pins, 13 paths, and no horizontal overflow.
- No-WebGL static fallback: displayed the supplied static map, title, all 13 pins and all 13 curved connections.
- Motion sequence: early and settled frames captured; the source-only comparison uses the same renderer/media with the title and custom overlays hidden.
- Page transition: scrolling below the hero reveals the existing overview/dashboard content.
- Browser page errors: none in final Playwright desktop, mobile, reduced-motion, or static-fallback captures. Two dashboard opportunity requests were aborted by deliberate page navigation during screenshot capture; no persistent request failure was observed.
- Responsive screenshot dimensions and pin/path counts came from the rendered pages, not source inspection alone.
- `Start Platform.bat`: reported “Platform is already running; opening the browser.” `/health/ready` returned `ready`; the launcher did not enter its startup/migration branch.

## Deployment and safety

- **LIVE_DEPLOYMENT_STATUS:** Deployed to `http://localhost:8080/`.
- **FRONTEND_IMAGE:** `sha256:e8717ac337150d03d2c0183f31668c77c504f6d2acee3851348a9148c86eab14`.
- **SERVICES_RESTARTED:** Frontend service only (`alahsa-local-frontend-1`). API, PostgreSQL, Redis, Worker and scheduler remained running; readiness reported database, Redis and worker healthy.
- **PRODUCTION_DATA_MUTATIONS:** None. No API/business logic, database, opportunity coordinates, map eligibility, synchronization, authentication or RBAC changes.
- **ROLLBACK_BACKUP_PATH:** `C:\Users\QusaiAbdElhalim\AppData\Local\Sharakat Data Base\backups\map-hero-reference-predeploy-20261109-232510`
- **ROLLBACK_IMAGE_TAG:** `alahsa-local-frontend:rollback-map-hero-20261109-232510`
- **INITIAL_IMAGE_ID:** `sha256:24a79678b0fcd51270686751bd1ac2d3844045b54492b507bac8110de9a8a3bc`

## Files changed

- `app/static/index.html` — replace only the hero image with the isolated runtime mount and bundle links.
- `app/static/hero-map/` — supplied stage sources/assets, isolated runtime bundle, platform hero CSS, projected connection/pin overlays, and third-party notices.
- Removed the rejected `app/static/national-map-hero.svg` and `app/static/national-map-hero.css`.
- `docs/validation/ui-redesign/landing/REFERENCE-IMPLEMENTATION-INSPECTION-20261109.md` and this report.
- `app/static/app.js`, Nginx configuration, launcher files and every backend component were left unchanged.

## Screenshot evidence

All files are under `docs/validation/ui-redesign/landing/`:

- `map-reference-baseline-no-overlays-1440x900-20261109.png` — supplied scene/media without title or custom pins/connections.
- `map-hero-live-desktop-1440x900-20261109.png` — deployed desktop hero.
- `map-hero-live-mobile-390x844-20261109.png` — deployed mobile hero.
- `map-hero-motion-frame-early-1440x900-20261109.png` — early line-draw / map-reveal state.
- `map-hero-transition-overview-1440x900-20261109.png` — existing overview below the hero.
- `map-hero-static-fallback-mobile-390x844-20261109.png` — no-WebGL fallback.

No known functional blockers remain for local use. The marker positions are reference points for presentation and should not be treated as official administrative centroids.
