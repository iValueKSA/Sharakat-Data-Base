from datetime import datetime, timezone

import pytest

from app.adapters import NcpAdapter, RawOpportunity, normalize_sector, normalized_record


PROJECT_1 = "fe95dde7-9741-4885-3c01-08ddf6955843"
PROJECT_2 = "62b92c20-59ac-5b07-964b-07152d234b70"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    async def get(self, url, params=None, headers=None):
        self.calls.append((url, params, dict(headers or {})))
        if url.endswith("config.prod.json"):
            return FakeResponse({"apiBaseUrl": "https://investors.ncp.gov.sa/api/v1"})
        if url.endswith("/projects/pipeline"):
            page = (params or {}).get("pageNumber", 1)
            return FakeResponse(self.payloads["pages"][page])
        project_id = url.rsplit("/", 1)[-1]
        return FakeResponse(self.payloads["details"].get(project_id, {"success": False}))


def summary(project_id, name, location):
    return {
        "id": project_id,
        "nameAr": name,
        "nameEn": name,
        "sectorNameEn": "Transport",
        "locationNameEn": location,
        "displayStageSubNameEn": "Request For Proposals (RFP)",
        "stageStartDate": "2026-01-01T00:00:00",
        "deadline": "2026-12-31T00:00:00",
        "isAvailableToSubmit": False,
    }


def detail(project_id, name, location):
    return {
        "success": True,
        "data": {
            "id": project_id,
            "nameAr": name,
            "nameEn": name,
            "projectDescriptionEn": "Public project description",
            "locationNameEn": location,
            "sectorNameEn": "Transport",
            "projectOwnerNameEn": "Public authority",
            "projectStageNameEn": "Request For Proposals (RFP)",
            "isClosed": False,
            "isAvailableToSubmit": False,
            "projectAttachments": [],
        },
    }


def two_page_payloads(ids=(PROJECT_1, PROJECT_2)):
    first = summary(ids[0], "Airport PPP", "Riyadh")
    second = summary(ids[1], "Water PPP", "Tabuk")
    return {
        "pages": {
            1: {"success": True, "data": {"items": [first], "pageNumber": 1, "pageSize": 1, "totalPages": 2, "totalCount": 2}},
            2: {"success": True, "data": {"items": [second], "pageNumber": 2, "pageSize": 1, "totalPages": 2, "totalCount": 2}},
        },
        "details": {
            ids[0]: detail(ids[0], "Airport PPP", "Riyadh"),
            ids[1]: detail(ids[1], "Water PPP", "Tabuk"),
        },
    }


@pytest.mark.asyncio
async def test_public_portal_enumeration_paginates_and_uses_uuid_identity():
    adapter = NcpAdapter()
    adapter.investor_portal_page_size = 1
    client = FakeClient(two_page_payloads())

    records, metrics = await adapter.fetch_investor_portal(client)

    assert [record.external_id for record in records] == [f"ncp-portal:{PROJECT_1}", f"ncp-portal:{PROJECT_2}"]
    assert metrics["public_project_count"] == 2
    assert metrics["pages"] == 2
    assert metrics["is_closed_false"] == 2
    assert metrics["available_to_submit"] == 0
    assert all(record.raw["provider_id_field"] == "id (UUID)" for record in records)
    assert all(record.raw["provider"] == "NCP_INVESTORS_PORTAL" for record in records)
    assert all(record.raw["ncp_portal_record"]["detail"]["projectOwnerNameEn"] == "Public authority" for record in records)
    assert all(record.status is None and record.deadline is None and not record.location_source_filtered for record in records)
    requested_paths = {url.split("?", 1)[0].removeprefix("https://investors.ncp.gov.sa") for url, _, _ in client.calls}
    assert requested_paths == {
        "/assets/config.prod.json", "/api/v1/projects/pipeline",
        f"/api/v1/projects/{PROJECT_1}", f"/api/v1/projects/{PROJECT_2}",
    }
    assert all(url.startswith("https://investors.ncp.gov.sa/") for url, _, _ in client.calls)
    assert all(not any(name.casefold() == "authorization" for name in headers) for _, _, headers in client.calls)
    assert all(not any(term in url.casefold() for term in ("/login", "/auth", "/token")) for url, _, _ in client.calls)


@pytest.mark.asyncio
async def test_public_portal_duplicate_provider_ids_fail_closed():
    payloads = two_page_payloads((PROJECT_1, PROJECT_1))
    payloads["pages"] = {
        1: {"success": True, "data": {"items": [summary(PROJECT_1, "Airport PPP", "Riyadh"), summary(PROJECT_1, "Duplicate", "Riyadh")], "pageNumber": 1, "pageSize": 100, "totalPages": 1, "totalCount": 2}}
    }
    adapter = NcpAdapter()

    with pytest.raises(RuntimeError, match="duplicate project UUIDs"):
        await adapter.fetch_investor_portal(FakeClient(payloads))


@pytest.mark.asyncio
async def test_public_portal_detail_uuid_must_match_listing_uuid():
    payloads = two_page_payloads()
    payloads["pages"] = {1: {"success": True, "data": {"items": [summary(PROJECT_1, "Airport PPP", "Riyadh")], "pageNumber": 1, "pageSize": 100, "totalPages": 1, "totalCount": 1}}}
    payloads["details"][PROJECT_1] = detail(PROJECT_2, "Wrong record", "Tabuk")

    with pytest.raises(RuntimeError, match="detail identity did not match"):
        await NcpAdapter().fetch_investor_portal(FakeClient(payloads))


@pytest.mark.asyncio
async def test_public_portal_detail_cache_avoids_repeat_detail_requests():
    adapter = NcpAdapter()
    payloads = two_page_payloads()
    payloads["pages"] = {1: {"success": True, "data": {"items": [summary(PROJECT_1, "Airport PPP", "Riyadh")], "pageNumber": 1, "pageSize": 100, "totalPages": 1, "totalCount": 1}}}
    cache_detail = detail(PROJECT_1, "Airport PPP", "Riyadh")["data"]
    listing = payloads["pages"][1]["data"]["items"][0]
    adapter.portal_detail_cache = {PROJECT_1: {
        "listing_fingerprint": adapter._portal_fingerprint(listing),
        "detail_observed_at": datetime.now(timezone.utc).isoformat(),
        "detail": cache_detail,
    }}
    client = FakeClient(payloads)

    records, metrics = await adapter.fetch_investor_portal(client)

    assert metrics["details_refreshed"] == 0
    assert not any(url.endswith("/" + PROJECT_1) for url, _, _ in client.calls)
    assert records[0].raw["ncp_portal_record"]["detail"]["isClosed"] is False


def test_portal_source_only_record_is_not_geographically_or_canonically_promoted():
    raw = RawOpportunity(
        external_id=f"ncp-portal:{PROJECT_1}",
        title="National PPP",
        url=f"https://investors.ncp.gov.sa/projects/{PROJECT_1}",
        raw={"provider": "NCP_INVESTORS_PORTAL", "provider_id": PROJECT_1},
    )

    normalized = normalized_record(raw)

    assert normalized["relevant"] is False
    assert normalized["location_detection_method"] == "NCP_PORTAL_SOURCE_CAPTURE_NO_AUTOPROMOTION"


def test_portal_image_payloads_are_replaced_with_hash_evidence():
    value = "A" * 1200
    stripped = NcpAdapter._portal_strip_binary({"projectBackground": value, "backgroundAttachmentId": "stable-id"})

    assert "projectBackground" not in stripped
    assert stripped["projectBackground_encoded_length"] == len(value)
    assert len(stripped["projectBackground_sha256"]) == 64
    assert stripped["backgroundAttachmentId"] == "stable-id"


def test_exact_ncp_macro_sector_labels_map_without_collapsing_combined_categories():
    assert normalize_sector("Hajj and Umrah Sector") == "الحج والعمرة"
    assert normalize_sector("Environment, Water & Agriculture Sector") == "البيئة والمياه والزراعة"
    assert normalize_sector("Municipalities and Housing Sector") == "البلديات والإسكان"
    assert normalize_sector("Zakat, Tax and Customs Sector") == "الزكاة والضريبة والجمارك"
    assert normalize_sector("Transport and Logistic Services Sector") == "النقل والخدمات اللوجستية"
    assert normalize_sector("Sports Sector") == "الرياضة"
    assert normalize_sector("Education Sector") == "التعليم"
    assert normalize_sector("municipalities-related project") is None
