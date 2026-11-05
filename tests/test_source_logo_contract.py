import re
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def test_source_logo_map_covers_all_configured_source_keys_and_local_assets():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    block = re.search(r"const SOURCE_LOGOS = \{(?P<body>.*?)\n\};", js, re.S)
    assert block, "central source logo map must exist"
    keys = set(re.findall(r'^\s*(?:"([^"]+)"|([a-z][a-z-]*))\s*:', block.group("body"), re.M))
    keys = {a or b for a, b in keys}
    assert keys == {"furas", "alahsa-opportunities", "ahda", "invest-saudi", "kfu", "modon", "ncp", "nhc", "pif", "mwan", "waha-development", "rcjy-investment-opportunities"}
    paths = re.findall(r'path: "(/static/source-logos/[^\"]+)"', block.group("body"))
    assert len(paths) == 7
    provenance = (ROOT / "docs" / "design" / "source-logo-system.md").read_text(encoding="utf-8")
    for url_path in paths:
        asset = STATIC / url_path.removeprefix("/static/")
        assert asset.is_file(), f"missing local source logo: {asset}"
        raw = asset.read_bytes()
        assert len(raw) > 100
        assert hashlib.sha256(raw).hexdigest().upper() in provenance
        if asset.suffix == ".svg":
            assert b"<svg" in raw[:500] or b"<svg" in raw[:1000]
        elif asset.suffix == ".png":
            assert raw.startswith(b"\x89PNG\r\n\x1a\n")
        elif asset.suffix == ".webp":
            assert raw[:4] == b"RIFF" and raw[8:12] == b"WEBP"
        else:
            raise AssertionError(f"unexpected logo type: {asset.suffix}")


def test_source_cards_show_source_logo_and_lazy_source_filtered_opportunities():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'sourceLogoMarkup(source.key)' in js
    assert 'source: sourceKey, limit: "50"' in js
    assert 'data-detail="${item.id}"' in js
    assert 'source?.url' in js
    assert 'onerror="this.hidden=true;this.nextElementSibling.hidden=false"' in js


def test_source_logo_css_preserves_shape_and_rtl_row_layout():
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    assert "object-fit:contain" in css.replace(" ", "")
    assert ".source-opportunity-row" in css and "direction:rtl" in css
    assert "@media(max-width:520px)" in css
