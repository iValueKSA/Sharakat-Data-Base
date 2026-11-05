# Dashboard Hero — Map Scene Removal Review

**Status: COMPLETE.** The live Dashboard now serves the revised local video with **zero map scenes**. Both previous map sections were replaced by cinematic Al-Ahsa-related landscapes: an irrigation-channel pass through the date palms and a palm-lined investment road at twilight. The poster shows the non-map opening oasis scene.

## Before revision

The previous premium Hero video was `app/static/media/ahsa-investment-hero.webm`, WebM VP9, 1920×540, 22.093396 seconds, and 9,790,340 bytes. It contained two map scenes:

- **03.65–07.65 seconds:** wide Al-Ahsa boundary reveal.
- **18.25–22.09 seconds:** closer boundary/map view with pulse.

## Revised video

The new local asset remains `app/static/media/ahsa-investment-hero.webm`: **WebM VP9, 1920×540, 24 fps, 22.131582 seconds, 9,790,136 bytes**. It contains six distinct landscape scenes and no maps, boundary outlines, geographic pulses, map zooms, or map overlays:

1. **Opening oasis:** date palms and escarpment at dawn.
2. **Irrigation:** low cinematic pass beside an irrigation channel and cultivated palm plots at golden hour, replacing the former wide-map slot.
3. **Oasis detail:** closer palms, farm plots, and water channels.
4. **Heritage:** warm architecture and shaded street.
5. **Investment district:** low-rise business/logistics district at sunset.
6. **Development road:** palm-lined road and illuminated low-rise district at twilight, replacing the former map-focus slot.

Gentle camera drift and crossfades preserve the video’s rhythm. The closing road shot blends back to the opening oasis. Live browser playback wrapped natively to the beginning and continued. The local WebP poster is **243,874 bytes** and uses the opening oasis frame; visual inspection confirms it contains no map.

The new landscape and development shots are AI-generated promotional illustrations. They do not claim to document a named site or a specific listed opportunity. No media from the reference site was copied or used at runtime.

## Live validation

Only the frontend image was rebuilt and only `alahsa-local-frontend-1` was recreated. Database, API, worker, scheduler, and Redis containers were not restarted. The live Dashboard served the versioned local asset and its SHA-256 matched the project file. The actual live video decoded at 1920×540 and reported a finite duration; it played automatically, muted, inline, and looped.

Live screenshots were captured at the replacement irrigation and road scene times and at all five required viewport sizes. The screenshots show landscape footage, readable title/subtitle/CTA, and no map visuals. The displayed dashboard total stayed **566** and `مواعيد خلال 30 يوماً` stayed **60**. The CTA still navigates to opportunities.

| Viewport | Video/title/subtitle/CTA | RTL | Text overlap/clipping | Horizontal overflow |
|---|---|---|---|---|
| 1920×1080 | PASS | PASS | None | No |
| 1440×900 | PASS | PASS | None | No |
| 1366×768 | PASS | PASS | None | No |
| 768×900 | PASS | PASS | None | No |
| 390×844 | PASS | PASS | None | No |

Reduced-motion mode leaves the video paused, does not attach the video source, and displays the poster. When the versioned video request is aborted, the poster, title, CTA, and Dashboard metric remain visible. JavaScript errors: **0**. Unexpected HTTP 4xx/5xx: **0**. Runtime requests to `alahsa-opportunities.com`: **0**.

## Tests and scope

- Focused Hero UI tests: **9 passed, 0 failed** (`tests/test_dashboard_video_hero.py`).
- Live Playwright: **5/5 viewport sizes passed**, with loop boundary, CTA, reduced-motion poster, media-request fallback, asset hash, and zero-reference-request checks.
- The title, subtitle, CTA behavior, Hero container, overlay, Dashboard calculations, filters, chart logic, and application map logic were not changed. No business API, database write endpoint, or sync control was called.
- No source sync was manually started; no master, source opportunity, review, or canonical data was changed.

## Evidence

- `video-hero-manifest.json` — six scene timings, zero map scenes, replacements, and poster statement.
- `video-media-provenance.json` — generated landscape sources and local asset hash.
- `video-optimization.json` — previous and revised asset metadata.
- `video-hero-playwright.json` — live browser results and five viewport measurements.
- `video-hero-performance.json` — prior/current local performance measurements.
- `video-hero-comparison.json` — map removal and replacement-scene comparison.
- `screenshots/premium-hero-irrigation-replacement-live.png`
- `screenshots/premium-hero-road-replacement-live.png`
- `screenshots/premium-hero-390x844.png`

## Final assertions

```text
DASHBOARD_VIDEO_HERO_MAP_REMOVAL = COMPLETE
CURRENT_VIDEO_ASSET = app/static/media/ahsa-investment-hero.webm
CURRENT_VIDEO_DURATION = 22.131582 seconds
CURRENT_VIDEO_FILE_SIZE_MB = 9.790136
CURRENT_MAP_SCENE_1_TIME_RANGE = 03.65–07.65 seconds
CURRENT_MAP_SCENE_2_TIME_RANGE = 18.25–22.09 seconds
MAP_SCENE_COUNT_BEFORE = 2
MAP_SCENE_COUNT_AFTER = 0
NO_MAP_VISUALS_PRESENT = TRUE
REPLACEMENT_SCENES = irrigation-channel pass; palm-lined development road at twilight
MULTI_SCENE_VIDEO = TRUE (6 distinct landscape scenes)
SMOOTH_LOOP = TRUE
VIDEO_HOSTING_STRATEGY = LOCAL
RUNTIME_DEPENDENCY_ON_REFERENCE_SITE = FALSE
HERO_TITLE = منصة الفرص الاستثمارية في الأحساء
HERO_SUBTITLE = استكشف الفرص الاستثمارية المتاحة في محافظة الأحساء
CTA_TEXT = استعرض الفرص
CTA_BEHAVIOR_CHANGED = FALSE
VIDEO_AUTOPLAY = TRUE
VIDEO_MUTED = TRUE
VIDEO_LOOP = TRUE
VIDEO_PLAYSINLINE = TRUE
VIDEO_POSTER_AVAILABLE = TRUE
POSTER_CONTAINS_MAP = FALSE
LIVE_SCREENSHOT_PROVES_NO_MAP = TRUE
PLAYWRIGHT_1920x1080 = PASSED
PLAYWRIGHT_1440x900 = PASSED
PLAYWRIGHT_1366x768 = PASSED
PLAYWRIGHT_768x900 = PASSED
PLAYWRIGHT_390x844 = PASSED
RTL = PASSED
NO_TEXT_OVERLAP = TRUE
NO_CLIPPING = TRUE
NO_HORIZONTAL_OVERFLOW = TRUE
JAVASCRIPT_ERRORS = 0
UNEXPECTED_HTTP_5XX = 0
DASHBOARD_METRICS_CHANGED = FALSE
DASHBOARD_FILTERS_CHANGED = FALSE
DASHBOARD_CHART_LOGIC_CHANGED = FALSE
MAP_LOGIC_CHANGED = FALSE
MASTER_CHANGES = 0
SOURCE_OPPORTUNITY_CHANGES = 0
REVIEW_CHANGES = 0
CANONICAL_CHANGES = 0
MANUAL_SOURCE_SYNC_STARTED = FALSE
```
