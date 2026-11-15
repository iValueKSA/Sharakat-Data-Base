# Saudi Map Hero Reference Restoration — 2026-11-10

## Result

**Status: PASS — live frontend updated and verified.** The supplied map stage was already integrated into the live platform. This change corrects the uniform connection fan and slightly improves the legibility of its existing animated pins and paths. The original 3D map scene, geometry, color treatment, shaders, media and animation logic were left intact.

## Reference inspection and cause

Inspected `Downloads/landing-page-code.zip` before editing. Its original landing implementation contains a Three.js / React Three Fiber `KingdomScene`, province geometry and projection (`geo.ts`, `saudi-provinces.ts`), layered province/city/route rendering (`KingdomLayers.tsx`), shaders and materials, the GSAP camera/stage state, and responsive still/video background assets. Its motion specification describes a lit solid province plate, additive sparks, a damped camera and a static SVG province fallback for reduced-motion, `saveData`, or browsers without WebGL. The original specification rejects light packets on route arcs; none were added.

The original ZIP does not contain the root package manifest or Next.js app configuration needed to run the whole original site as a separate application. The map-stage source and assets needed for this integration are present. Source hash comparison found `geo.ts`, `saudi-provinces.ts`, `KingdomLayers.tsx`, `CameraRig.tsx`, `shaders.ts`, and `materials.ts` byte-for-byte identical to the ZIP. `KingdomScene.tsx` differs only by the platform-specific projected region connection overlay.

At the start of this execution, the live application was already rendering that 3D stage in default Chrome: one WebGL canvas, detailed province and city geometry, lighting, particles and the original media layer. There was no `app/static/national-map-hero.svg`, and `index.html` mounts `/static/hero-map/runtime.js`. The actual remaining defect was in the added overlay: every Bezier curve had the same positive horizontal bow, so the set read as a rigid, nearly parallel fan. The reference-specified no-WebGL fallback is intentionally a flat SVG projection; forcing WebGL off reproduces that fallback, while default Chrome on this machine reports WebGL available and renders the original 3D view.

The supplied source and assets were user-provided for reuse. The bundled MIT/Apache notices remain in `THIRD-PARTY-LICENSES.txt`; the runtime preserves the GSAP 3.13.0 license notice. GSAP's current standard license permits use in websites and web applications, including commercial use, subject to its listed restrictions ([official GSAP standard license](https://gsap.com/standard-license)).

## Changes

- Replaced the single-direction curve controls with side-aware Bezier controls in both the WebGL and static fallback connection renderers. The left and right sides now bow in opposing directions; all paths still originate at their corresponding region pins and converge under the title.
- Increased the thin connection stroke from 0.8 to 1 CSS pixel and slightly enlarged the existing halo, ring and core. Mobile uses a 0.9-pixel stroke and the existing pulse/draw motion remains subtle.
- Changed only the hero CSS/runtime query version from `reference-r3f-v1` to `reference-r3f-v2` to avoid stale browser assets.
- Rebuilt the isolated runtime with esbuild. The original map geometry, materials, shaders, camera rig, stage data, background assets, page navigation and overview content were not edited.

## Validation

- Predeployment Playwright check against the rebuilt runtime/CSS at 1440×900, 768×1024 and 390×844: WebGL rendered, 13 pins and 13 cubic paths, all 13 path starts matched pin positions, all 13 path ends landed on the title, opposing left/right curve directions, no horizontal overflow, and no JavaScript page exceptions.
- Postdeployment live checks at `http://localhost:8080/`: CSS and runtime assets with `reference-r3f-v2` both returned HTTP 200; 13 pins and 13 cubic connections rendered at all three viewports; title was `منصة الفرص الاستثمارية`; computed font was Ahda Text; no horizontal overflow or JavaScript page exceptions.
- Desktop video layer was playing at capture (`currentTime` 6.36 s). The tablet and mobile layouts rendered the live map without the desktop video, as configured.
- Forced no-WebGL fallback: 13 province shapes, 13 pins, 13 cubic paths and the title rendered, with no JavaScript page exceptions.
- Reduced-motion preference: honored; connection and pin animation durations reduced to `0.00001s`.
- Scrolling past the hero showed the existing overview metrics, opportunity list and source panel directly below it. No extra landing section was added.
- `Start Platform.bat` completed successfully, found the platform healthy, and opened the browser without starting or rebuilding other services.
- Live readiness returned `ready` (database, Redis and worker OK). The API, worker, scheduler, database and Redis container IDs did not change.
- The only browser error response observed was the expected unauthenticated `GET /api/auth/me` returning 401 in a fresh Playwright context. It produced no JavaScript exception and is unrelated to hero assets.

## Deployment and rollback

The image was built from the deployed frontend's existing static asset tree, then only the hero runtime, CSS, connection source files, pin markup and cache version were replaced. This avoided packaging the worktree's unrelated pending frontend/backend changes.

- Frontend image: `alahsa-local-frontend:latest`, image ID `sha256:f88ecda8afbe88a18abfdf2fa8511c6aaa210c26b51a5f3b8848e6c2945b380a`.
- Recreated service: `frontend` only. No other services were restarted.
- Rollback image: `alahsa-local-frontend:rollback-reference-map-hero-20261110-095146`.
- Full image archive and manifest: `C:\Users\QusaiAbdElhalim\AppData\Local\Sharakat Data Base\backups\reference-map-hero-predeploy-20261110-095146`.
- Database, coordinates, opportunity data, authentication configuration and API behavior: unchanged.

## Evidence

All screenshots are under `docs/validation/ui-redesign/landing/`:

- `reference-reference-render-1440x900-20261110.png` — supplied map stage in reference-only view, with the added platform title and overlay hidden.
- `reference-map-before-desktop-1440x900-20261110.png` — live before-state.
- `hero-reference-corrected-live-desktop-1440x900-20261110.png`
- `hero-reference-corrected-live-tablet-768x1024-20261110.png`
- `hero-reference-corrected-live-mobile-390x844-20261110.png`
- `hero-reference-animated-draw-900ms-20261110.png` and `hero-reference-animated-settled-5400ms-20261110.png` — connection draw and settled animated state.
- `hero-reference-static-fallback-after-1440x900-20261110.png` — expected static no-WebGL fallback.
- `hero-reference-overview-transition-20261110.png` — hero-to-existing-overview transition.

## Files changed

- `app/static/hero-map/_components/stage/RegionConnections.tsx`
- `app/static/hero-map/_components/stage/StaticRegionConnections.tsx`
- `app/static/hero-map/entry.tsx`
- `app/static/hero-map/hero.css`
- `app/static/hero-map/runtime.js` (compiled output)
- `app/static/index.html` (hero cache version only)

## Final fields

```text
REFERENCE_CODE_INSPECTED = YES
ORIGINAL_MAP_COMPONENT_IDENTIFIED = KingdomScene + KingdomLayers + CameraRig
REFERENCE_EFFECTS_REUSED = YES
MAP_GEOMETRY_FIDELITY = PASS (reference geometry/source hashes match)
MAP_COLOR_FIDELITY = PASS (reference materials/shaders unchanged)
MAP_ANIMATIONS = PASS
THIRTEEN_REGION_PINS = PASS
CURVED_CONNECTION_LINES = PASS
TITLE_CONNECTION = PASS
ORIGINAL_CONTENT_PRESERVED = PASS
RESPONSIVE_VALIDATION = PASS (desktop/tablet/mobile)
LIVE_DEPLOYMENT_STATUS = PASS (frontend only)
SERVICES_RESTARTED = frontend only
PRODUCTION_DATA_MUTATIONS = NONE
REMAINING_ISSUES = Full original Next site cannot be launched independently because its package manifest/app bootstrap are absent from the supplied ZIP; the supplied map-stage source and assets were available and verified. A separate user's browser with WebGL disabled will show the reference's intentional static fallback.
```
