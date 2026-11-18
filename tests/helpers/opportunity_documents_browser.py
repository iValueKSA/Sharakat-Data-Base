"""Fresh-context Playwright smoke acceptance using synthetic API payloads only."""
import json
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "app" / "static"
EVIDENCE = ROOT / "docs" / "validation" / "ui-redesign"
EVIDENCE.mkdir(parents=True, exist_ok=True)


def item(identifier, title):
    return {"id": identifier, "title": title, "canonical_id": f"SYNTHETIC-{identifier}",
            "owner": "جهة اختبار", "sector": "الاستثمار", "activity": "اختبار", "sub_activity": "",
            "type": "فرصة استثمارية", "investment_model": "", "asset_facility_type": "غير محدد",
            "geography": {"country": "المملكة العربية السعودية", "region": "منطقة تجريبية",
                          "governorate": "محافظة تجريبية", "locality": "موقع تجريبي", "district": "",
                          "status_ar": "متحقق", "confirmed": True}, "location": "موقع تجريبي",
            "area": None, "area_unit": "م²", "investment_value": None, "currency": None,
            "duration": None, "duration_unit": "year", "deadline": "غير محدد", "reference": f"TEST-{identifier}",
            "confidence": 1, "source_count": 1, "status": "متاحة", "sources": [], "changes": []}


public_opportunity = item(1, "فرصة اختبارية مع مستندات موثقة")
public_opportunity["documents"] = [
    {"id": 101, "source_id": 1, "source_key": "synthetic-source", "source_name": "مصدر تجريبي",
     "source_opportunity_id": 1001, "provider_opportunity_reference": "fixture-1001", "master_opportunity_id": 1,
     "title": "كراسة الشروط التجريبية", "document_category": "TERMS_AND_CONDITIONS_BOOKLET",
     "source_opportunity_url": "https://source.example.invalid/opportunity/1001",
     "official_purchase_url": "https://source.example.invalid/purchase/1001",
     "link_url": "https://source.example.invalid/documents/fixture-booklet.pdf",
     "access_status": "PUBLIC_DIRECT_DOWNLOAD", "rights_status": "DIRECT_LINK_APPROVED",
     "authentication_required": False, "payment_required_for_document": False,
     "participation_requirement": "PURCHASE_REQUIRED_FOR_PARTICIPATION",
     "booklet_price_amount": 300, "currency": "SAR", "link_verification_status": "VERIFIED_PUBLIC",
     "last_verified_at": "2026-11-15T00:00:00+00:00", "document_version": 1},
    {"id": 102, "source_id": 2, "source_key": "synthetic-source-b", "source_name": "مصدر تجريبي ثانٍ",
     "source_opportunity_id": 1002, "provider_opportunity_reference": "fixture-1002", "master_opportunity_id": 1,
     "title": "مرفق فني تجريبي", "document_category": "TECHNICAL_ATTACHMENT",
     "source_opportunity_url": "https://source-b.example.invalid/opportunity/1002",
     "link_url": "https://source-b.example.invalid/opportunity/1002",
     "access_status": "LOGIN_REQUIRED", "rights_status": "SOURCE_PAGE_LINK_ONLY",
     "authentication_required": True, "payment_required_for_document": None,
     "participation_requirement": "UNKNOWN", "booklet_price_amount": None, "currency": None,
     "link_verification_status": "VERIFIED_SOURCE_PAGE", "last_verified_at": "2026-11-15T00:00:00+00:00",
     "document_version": 1},
    {"id": 103, "source_id": 2, "source_key": "synthetic-source-b", "source_name": "مصدر تجريبي ثانٍ",
     "source_opportunity_id": 1002, "provider_opportunity_reference": "fixture-1002", "master_opportunity_id": 1,
     "title": "مستند يتطلب الدفع لدى المصدر", "document_category": "GENERAL_ATTACHMENT",
     "source_opportunity_url": "https://source-b.example.invalid/opportunity/1002",
     "official_purchase_url": "https://source-b.example.invalid/purchase/1002",
     "link_url": "https://source-b.example.invalid/opportunity/1002",
     "access_status": "PAYMENT_REQUIRED_FOR_DOCUMENT", "rights_status": "SOURCE_PAGE_LINK_ONLY",
     "authentication_required": None, "payment_required_for_document": True,
     "purchase_url_verified": True,
     "participation_requirement": "UNKNOWN", "booklet_price_amount": None, "currency": None,
     "link_verification_status": "VERIFIED_SOURCE_PAGE", "last_verified_at": None, "document_version": 1},
    {"id": 104, "source_id": 1, "source_key": "synthetic-source", "source_name": "مصدر تجريبي",
     "source_opportunity_id": 1001, "provider_opportunity_reference": "fixture-1001", "master_opportunity_id": 1,
     "title": "مستند متاح عبر صفحة المصدر", "document_category": "UNKNOWN_DOCUMENT_TYPE",
     "source_opportunity_url": "https://source.example.invalid/opportunity/1001",
     "link_url": "https://source.example.invalid/opportunity/1001",
     "access_status": "PUBLIC_SOURCE_PAGE", "rights_status": "SOURCE_PAGE_LINK_ONLY",
     "authentication_required": False, "payment_required_for_document": False,
     "participation_requirement": "UNKNOWN", "booklet_price_amount": None, "currency": None,
     "link_verification_status": "VERIFIED_SOURCE_PAGE", "last_verified_at": "2026-11-15T00:00:00+00:00", "document_version": 1},
]
public_opportunity["document_source_pages"] = [
    {"source_id": 1, "source_key": "synthetic-source", "source_name": "مصدر تجريبي",
     "source_opportunity_id": 1001, "provider_opportunity_reference": "fixture-1001",
     "url": "https://source.example.invalid/opportunity/1001"}
]
empty_opportunity = item(2, "فرصة اختبارية بلا كراسة موثقة")
empty_opportunity["documents"] = []
empty_opportunity["document_source_pages"] = [
    {"source_id": 1, "source_key": "synthetic-source", "source_name": "مصدر تجريبي",
     "source_opportunity_id": 2001, "provider_opportunity_reference": "fixture-2001",
     "url": "https://source.example.invalid/opportunity/2001"}
]


class StaticHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def translate_path(self, path):
        relative = urlsplit(path).path
        if relative in {"/", "/index.html"}:
            relative = "index.html"
        elif relative.startswith("/static/"):
            relative = relative[len("/static/"):]
        else:
            relative = relative.lstrip("/")
        return str((STATIC / relative).resolve())

    def log_message(self, *_):
        pass


def main():
    external_url = os.getenv("DOCUMENTS_BROWSER_URL")
    server = None
    if external_url:
        url = external_url.rstrip("/") + "/?view=opportunities"
    else:
        server = ThreadingHTTPServer(("127.0.0.1", 0), StaticHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_port}/?view=opportunities"
    browser_errors = []
    unexpected_api = []
    failed_requests = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1100}, locale="ar-SA")
            if context.cookies():
                raise AssertionError("Fresh browser context unexpectedly contains cookies")
            page = context.new_page()
            page.on("pageerror", lambda error: browser_errors.append(str(error)))
            page.on("requestfailed", lambda request: failed_requests.append(f"{request.method} {request.url}: {request.failure}"))

            def api_route(route):
                request_url = route.request.url
                path = request_url.split("?", 1)[0]
                if path.endswith("/api/auth/me"):
                    route.fulfill(status=401, content_type="application/json", body='{"detail":"Not authenticated"}')
                elif path.endswith("/api/filters"):
                    route.fulfill(json={"sectors": [], "activities": [], "sub_activities": [], "subsectors": [],
                                        "statuses": [], "owners": [], "sources": [], "locations": [], "types": [],
                                        "investment_models": [], "asset_facility_types": [], "option_ids": {}})
                elif path.endswith("/api/geography/catalog"):
                    route.fulfill(json={"reference_ready": False, "status": "NOT_CONFIGURED"})
                elif path.endswith("/api/geography/filter-options"):
                    route.fulfill(json={"regions": [], "governorates": []})
                elif path.endswith("/api/opportunities"):
                    route.fulfill(json={"items": [
                        {"id": 1, "title": public_opportunity["title"], "canonical_id": "SYNTHETIC-1", "reference": "TEST-1",
                         "sector": "الاستثمار", "status": "متاحة", "owner": "جهة اختبار", "activity": "اختبار",
                         "sub_activity": "", "asset_facility_type": "غير محدد", "area": None, "area_unit": "م²",
                         "deadline": "غير محدد", "source_count": 2},
                        {"id": 2, "title": empty_opportunity["title"], "canonical_id": "SYNTHETIC-2", "reference": "TEST-2",
                         "sector": "الاستثمار", "status": "متاحة", "owner": "جهة اختبار", "activity": "اختبار",
                         "sub_activity": "", "asset_facility_type": "غير محدد", "area": None, "area_unit": "م²",
                         "deadline": "غير محدد", "source_count": 1}], "total": 2})
                elif path.endswith("/api/opportunities/1"):
                    route.fulfill(json=public_opportunity)
                elif path.endswith("/api/opportunities/2"):
                    route.fulfill(json=empty_opportunity)
                else:
                    unexpected_api.append(request_url)
                    route.fulfill(status=404, json={"detail": "Unexpected synthetic browser API call"})

            page.route("**/api/**", api_route)
            page.goto(url, wait_until="networkidle")
            for unsafe_url in ("javascript:alert(1)", "http://127.0.0.1/admin", "https://source.example.invalid:8443/file",
                               "https://source.example.invalid/file?access%5Ftoken=secret", "https://source.example.invalid/file?api_key=secret",
                               "https://source.example.invalid/file#access_token=secret"):
                if page.evaluate("value => safeExternalHref(value)", unsafe_url):
                    raise AssertionError(f"Unsafe link passed client validation: {unsafe_url.split(':', 1)[0]}")
            page.locator('[data-detail="1"]').click()
            page.locator("#modal.show").wait_for()
            page.get_by_role("heading", name="مستندات الفرصة الاستثمارية").wait_for()
            for label in ("تحميل الكراسة", "يلزم شراء الكراسة للتقديم على المنافسة", "شراء الكراسة عبر المصدر الرسمي",
                          "يلزم تسجيل الدخول لدى المصدر", "الحصول على الكراسة من المصدر الرسمي", "زيارة المصدر الرسمي"):
                if page.get_by_text(label, exact=True).count() == 0:
                    raise AssertionError(f"Expected document action/notice is missing: {label}")
            if page.get_by_text("300 SAR").count() == 0 and page.get_by_text("SAR 300").count() == 0:
                if page.get_by_text("300", exact=False).count() == 0:
                    raise AssertionError("Verified synthetic price was not rendered")
            if page.locator(".document-price").count() != 1:
                raise AssertionError("Unknown or missing prices were displayed as verified amounts")
            if page.locator("html").get_attribute("dir") != "rtl":
                raise AssertionError("Arabic RTL direction changed")
            if "Ahda" not in page.locator("body").evaluate("el => getComputedStyle(el).fontFamily"):
                raise AssertionError("Ahda Text font is not present in computed body typography")
            document_links = page.locator(".opportunity-documents a")
            for index in range(document_links.count()):
                link = document_links.nth(index)
                if link.get_attribute("rel") != "noopener noreferrer" or link.get_attribute("referrerpolicy") != "no-referrer":
                    raise AssertionError("External document link lacks safe browsing attributes")
                if (link.get_attribute("href") or "").startswith(("http://127.", "http://localhost", "javascript:")):
                    raise AssertionError("Unsafe synthetic link appeared in document UI")
            if page.locator(".opportunity-document-card").count() != 4:
                raise AssertionError("Expected four approved synthetic document cards")
            page.screenshot(path=str(EVIDENCE / "opportunity-documents-mvp-synthetic-approved.png"), full_page=True)
            documents_section = page.locator(".opportunity-documents")
            documents_section.scroll_into_view_if_needed()
            documents_section.screenshot(path=str(EVIDENCE / "opportunity-documents-mvp-section-desktop.png"))

            page.set_viewport_size({"width": 390, "height": 844})
            documents_section.scroll_into_view_if_needed()
            page.wait_for_timeout(150)
            if page.evaluate("document.documentElement.scrollWidth > window.innerWidth"):
                raise AssertionError("Synthetic document details overflow on mobile viewport")
            documents_section.screenshot(path=str(EVIDENCE / "opportunity-documents-mvp-section-mobile.png"))
            page.screenshot(path=str(EVIDENCE / "opportunity-documents-mvp-mobile.png"), full_page=True)

            page.locator("#modalClose").click()
            page.locator('[data-detail="2"]').click()
            page.locator("#modal.show").wait_for()
            if page.locator(".opportunity-documents").count() != 0:
                raise AssertionError("The documents section should stay hidden when no approved documents exist")
            if page.locator(".opportunity-document-card").count() != 0:
                raise AssertionError("Empty document cards were rendered")
            page.screenshot(path=str(EVIDENCE / "opportunity-documents-mvp-empty-state.png"), full_page=True)
            if browser_errors:
                raise AssertionError("Browser JavaScript errors: " + "; ".join(browser_errors))
            if unexpected_api:
                raise AssertionError("Unexpected API requests: " + "; ".join(unexpected_api))
            if failed_requests:
                raise AssertionError("Failed browser requests: " + "; ".join(failed_requests))
            if context.cookies():
                raise AssertionError("The synthetic browser test unexpectedly created auth cookies")
            print(json.dumps({"status": "PASS", "authenticated": False, "fresh_context": True,
                              "scenarios": ["public booklet and price", "participation purchase separate from file access",
                                            "login", "payment with separate source purchase", "public source-page attachment",
                                            "multiple source rows", "empty document feature hidden by default", "mobile layout", "safe external links"],
                              "browser_errors": browser_errors, "unexpected_api": unexpected_api, "failed_requests": failed_requests,
                              "screenshots": ["docs/validation/ui-redesign/opportunity-documents-mvp-synthetic-approved.png",
                                              "docs/validation/ui-redesign/opportunity-documents-mvp-section-desktop.png",
                                              "docs/validation/ui-redesign/opportunity-documents-mvp-section-mobile.png",
                                              "docs/validation/ui-redesign/opportunity-documents-mvp-mobile.png",
                                              "docs/validation/ui-redesign/opportunity-documents-mvp-empty-state.png"]}, ensure_ascii=False))
            context.close()
            browser.close()
    finally:
        if server is not None:
            server.shutdown()


if __name__ == "__main__":
    main()
