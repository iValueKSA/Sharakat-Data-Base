# Mandatory Map Hero Corrections — 2026-11-10

## Outcome

| Gate | Result | Evidence |
|---|---|---|
| ALAHSA_LABEL | PASS | Hero label is `الأحساء`, projected at Al-Hufuf/Al-Ahsa (49.588981° E, 25.362680° N); it is no longer anchored to Dammam. The [UNGEGN city record](https://ungegn.un.org/dashboard/cities/details?id=3392) identifies these Al-Hufuf coordinates. |
| DAMMAM_REMOVED_FROM_HERO | PASS | No `الدمام` rendered among the hero labels; other city labels remain. |
| PROFESSIONAL_PIN_ICONS | PASS | 13 SVG teardrop pins with pointed geographic anchors, cyan outline, dark fill and inner point; the anchor remains at each existing region projection. |
| PIN_COUNT | PASS | Exactly 13 rendered region anchors. |
| CONNECTION_COUNT | PASS | Exactly 13 cubic connection paths. |
| SINGLE_SHARED_ENDPOINT | PASS | All 13 path `d` strings end at the exact same SVG coordinate at each viewport (values below). The single convergence marker uses that same coordinate. |
| TITLE_ALIGNMENT | PASS | Endpoint is centered beneath the actual rendered title bounding box, at title bottom + 5 CSS px. |
| TITLE_TEXT | PASS | Exact hero heading: `منصة فرص الاستثمار`. |
| LEFT_RIGHT_CURVATURE | PASS | 13 distinct cubic control-point pairs at desktop; side-aware curvature remains. |
| MAP_PRESERVED | PASS | Existing Three.js map and province/constellation geometry retained. Only the decorative label anchor, overlay pin shapes and connection curves changed. |
| THREEJS_EFFECTS_PRESERVED | PASS | WebGL renderer loaded with no page exceptions; original stage, lighting and animation assets were retained. |
| EXISTING_PLATFORM_PRESERVED | PASS | Overview screenshot retained; dashboard and opportunities views opened successfully. No overflow or page exceptions in tested viewports. |
| RESPONSIVE_VALIDATION | PASS | Desktop 1440×900, tablet 768×1024, mobile 390×844, reduced-motion and forced static fallback. |
| LIVE_DEPLOYMENT_STATUS | PASS | Only the local frontend container was recreated. `Start Platform.bat` opened the already-ready platform successfully. |
| PRODUCTION_DATA_MUTATIONS | 0 | No database, API, map eligibility, business-data, or source-sync operations were run. |

## Runtime geometry evidence

The coordinates below are SVG coordinates relative to the hero. Runtime inspection found 13 paths and 13 pins at every tested viewport, with one unique endpoint and one marker coordinate:

| View | Shared endpoint for paths 0–12 and marker | Rendered title center / target |
|---|---:|---:|
| Desktop 1440×900 | `(588, 91.06)` | `(588, 91.0625)` |
| Tablet 768×1024 | `(384, 60)` | `(384, 60)` |
| Mobile 390×844 | `(195, 52.30)` | `(195, 52.296875)` |
| Static fallback 1440×900 | `(588, 91.06)` | `(588, 91.0625)` |

Every path ended in the same final pair; no path-specific title destination remains. The rendered teardrop path starts at its pointed anchor (`M 0 0`) so connection origins stay attached to each pin. Region anchor inputs and map projection were not changed.

## Deployment boundary

- New frontend image: `sha256:e46321285e2f988ac7ee7640ff8872d7289b90c8087695f365ca74f1fcfe304b`
- Frontend container: recreated and running as `alahsa-local-frontend-1`.
- API, Worker, scheduler, PostgreSQL and Redis container IDs remained unchanged.
- Deployment staging began from the served frontend asset tree (79 static files). Its content manifest differed in exactly: `index.html` (two hero cache keys advanced to `reference-r3f-v3`), `static/hero-map/hero.css`, and `static/hero-map/runtime.js`.
- No source/data assets outside the hero runtime bundle were deployed.
- Rollback image: `alahsa-local-frontend:rollback-map-three-corrections-20261110-102806` (`sha256:f88ecda8afbe88a18abfdf2fa8511c6aaa210c26b51a5f3b8848e6c2945b380a`). Saved archive: `C:\Users\QusaiAbdElhalim\AppData\Local\Sharakat Data Base\backups\map-three-corrections-predeploy-20261110-102806\frontend-image.tar`.

## Files changed

- `app/static/hero-map/_components/stage/geo.ts` — presentation-only Al-Hufuf label coordinates and Arabic display override; geographic Dammam city data preserved.
- `app/static/hero-map/_components/stage/KingdomLayers.tsx` — apply the display label and projection override to the existing city-label renderer.
- `app/static/hero-map/_components/stage/CameraRig.tsx` — keep the existing reveal tied to the label's corrected projected position.
- `app/static/hero-map/_components/stage/RegionConnections.tsx` — compute one rendered-title-centered destination for all paths and the single marker.
- `app/static/hero-map/_components/stage/StaticRegionConnections.tsx` — same shared destination and correctly projected Al-Ahsa fallback label.
- `app/static/hero-map/entry.tsx` — exact title, 13 teardrop SVG pin icons and one convergence marker.
- `app/static/hero-map/hero.css` — restrained pin styling, mobile sizing, convergence marker and fallback label styling.
- `app/static/hero-map/runtime.js` — rebuilt browser bundle from the hero entry point.

## Focused validation

- Served homepage, hero CSS and runtime returned HTTP 200; hero cache keys were `reference-r3f-v3`.
- WebGL and static fallback each rendered 13 pins and 13 cubic paths with one shared endpoint.
- The Al-Ahsa label rendered and the Dammam label did not. Remaining city labels were preserved.
- Reduced-motion mode rendered all 13 pins and paths.
- No horizontal overflow or Playwright page exceptions were observed at the tested sizes.
- Dashboard and opportunities navigation targets opened; no page exceptions were observed.
- `Start Platform.bat` reported the platform was already running and opened the browser without rebuilding services or applying migrations.
- No backend services were restarted. Frontend-only replacement completed; all five backend service container IDs are unchanged.

## Screenshots

- Baseline before: `docs/validation/ui-redesign/landing/mandatory-corrections-before-desktop-1440x900-20261110.png`
- Updated desktop hero: `docs/validation/ui-redesign/landing/mandatory-corrections-after-desktop-1440x900-20261110.png`
- Updated tablet hero: `docs/validation/ui-redesign/landing/mandatory-corrections-after-tablet-768x1024-20261110.png`
- Updated mobile hero: `docs/validation/ui-redesign/landing/mandatory-corrections-after-mobile-390x844-20261110.png`
- Al-Ahsa label close-up: `docs/validation/ui-redesign/landing/mandatory-corrections-after-ahsa-label-closeup-20261110.png`
- Pin icons close-up: `docs/validation/ui-redesign/landing/mandatory-corrections-after-pin-icons-closeup-20261110.png`
- Shared convergence close-up: `docs/validation/ui-redesign/landing/mandatory-corrections-after-convergence-closeup-20261110.png`
- All 13 connections, settled: `docs/validation/ui-redesign/landing/mandatory-corrections-after-full-connections-settled-20261110.png`
- Existing overview below hero: `docs/validation/ui-redesign/landing/mandatory-corrections-after-overview-below-20261110.png`

**Final acceptance: PASS.** Local platform updated at `http://localhost:8080/`.
