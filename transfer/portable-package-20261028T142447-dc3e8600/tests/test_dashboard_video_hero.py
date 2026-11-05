from pathlib import Path
import re
import struct
import json


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
CSS = (STATIC / "data-dashboard.css").read_text(encoding="utf-8")
JS = (STATIC / "data-dashboard.js").read_text(encoding="utf-8")
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
MEDIA = STATIC / "media"


def test_video_hero_precedes_existing_dashboard_content():
    dashboard = HTML.split('id="view-data-dashboard"', 1)[1]
    assert dashboard.index('class="rd-video-hero"') < dashboard.index('class="rd-page-head"')
    assert "منصة الفرص الاستثمارية في الأحساء" in dashboard
    assert "استكشف الفرص الاستثمارية المتاحة في محافظة الأحساء" in dashboard


def test_video_uses_local_sources_and_required_playback_contract():
    match = re.search(r'<video\b([^>]*)>(.*?)</video>', HTML, re.S)
    assert match
    attrs, children = match.groups()
    assert 'id="dataDashboardHeroVideo"' in attrs
    assert 'muted' in attrs and 'loop' in attrs and 'playsinline' in attrs
    assert 'preload="none"' in attrs
    assert 'poster="/static/media/ahsa-investment-hero-poster.webp?v=hero-no-map-v1"' in attrs
    assert 'data-src="/static/media/ahsa-investment-hero.webm?v=hero-no-map-v1"' in children
    assert 'type="video/webm"' in children
    assert "heroVideo.autoplay = true" in JS
    assert "heroVideo.play().catch" in JS
    assert "https://alahsa-opportunities.com/video/video.mp4" not in HTML + CSS + JS


def test_poster_and_optimized_motion_asset_are_present_and_web_optimized():
    poster = MEDIA / "ahsa-investment-hero-poster.webp"
    video = MEDIA / "ahsa-investment-hero.webm"
    assert poster.is_file() and poster.read_bytes()[:4] == b"RIFF"
    assert poster.read_bytes()[8:12] == b"WEBP"
    assert video.is_file() and video.read_bytes()[:4] == bytes.fromhex("1A45DFA3")
    assert poster.stat().st_size < 500_000
    assert video.stat().st_size < 12_000_000
    data = video.read_bytes()
    duration_32 = data.find(b"\x44\x89\x84")
    duration_64 = data.find(b"\x44\x89\x88")
    if duration_32 >= 0:
        duration_ms = struct.unpack(">f", data[duration_32 + 3:duration_32 + 7])[0]
    else:
        assert duration_64 >= 0
        duration_ms = struct.unpack(">d", data[duration_64 + 3:duration_64 + 11])[0]
    assert 22_000 <= duration_ms <= 22_500


def test_video_has_no_map_scenes_and_replaces_them_with_cinematic_landscapes():
    validation = ROOT / "docs" / "validation" / "ui" / "video-hero"
    manifest = json.loads((validation / "video-hero-manifest.json").read_text(encoding="utf-8"))
    assert manifest["map_scene_count"] == 0
    assert all(scene["type"] == "landscape" for scene in manifest["scenes"])
    scene_ids = {scene["id"] for scene in manifest["scenes"]}
    assert {"irrigation", "road"} <= scene_ids
    assert {"opening", "oasis", "heritage", "investment"} <= scene_ids
    assert all((validation / "source-frames" / scene["evidence_frame"]).is_file() for scene in manifest["scenes"])
    assert manifest["poster_contains_map"] is False
    assert manifest["poster_frame"] == "scene-01-opening.webp"
    assert manifest["loop_design"]["native_loop_verified"] is True
    assert not any("map" in frame.stem.lower() for frame in (validation / "source-frames").iterdir())


def test_cta_uses_existing_keyboard_accessible_opportunity_navigation():
    dashboard = HTML.split('id="view-data-dashboard"', 1)[1]
    assert re.search(r'<button[^>]*class="rd-video-hero-cta"[^>]*data-dash-goto[^>]*>\s*استعرض الفرص', dashboard)
    assert 'if (event.target.closest("[data-dash-goto]")) goToOpportunities();' in APP_JS
    assert ".rd-video-hero-cta:focus-visible" in CSS


def test_reduced_motion_and_video_failure_keep_the_poster_available():
    assert 'window.matchMedia?.("(prefers-reduced-motion: reduce)")' in JS
    assert "heroVideo.pause()" in JS
    assert 'heroVideo.addEventListener("error"' in JS
    assert "showPoster();" in JS
    assert ".rd-video-hero-poster" in CSS
    assert "@media(prefers-reduced-motion:reduce)" in CSS


def test_existing_dashboard_calculation_and_deadline_card_remain_present():
    dashboard = HTML.split('id="view-data-dashboard"', 1)[1]
    for identifier in (
        "rdHeroTotal",
        "rdActiveValue",
        "rdDeadlineTotal",
        "rdSectorChart",
        "rdOpportunityMap",
        "rdUpcomingList",
    ):
        assert f'id="{identifier}"' in dashboard
    assert "توزيع الفرص حسب الموعد" in dashboard
    assert "k.deadline_distribution_total" in JS
    assert "data.deadline_buckets" in JS


def test_hero_has_responsive_mobile_styles_without_viewport_width_expansion():
    assert "@media(max-width:680px)" in CSS
    assert "min-height:clamp(225px,64vw,280px)" in CSS
    assert "object-fit:cover" in CSS
    assert "overflow:hidden" in CSS


def test_hero_is_decorative_to_assistive_technology_and_has_real_html_copy():
    assert 'aria-label="الفرص الاستثمارية في الأحساء"' in HTML
    assert 'aria-hidden="true" tabindex="-1"' in HTML
    assert 'class="rd-video-hero-content"' in HTML
    assert 'class="rd-video-hero-cta" type="button"' in HTML
