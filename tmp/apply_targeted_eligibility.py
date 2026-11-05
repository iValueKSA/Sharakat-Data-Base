import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from sqlalchemy import select, text

from app.database import SessionLocal, engine
from app.models import LocationReview, Opportunity, Source, SourceOpportunity, SystemEvent


EVIDENCE = {
    283: (
        "OPPORTUNITY_LOCATION_CONFIRMED_AL_AHSA. Official Invest Saudi title identifies a "
        "peri-urban distripark in Al-Ahsa; its full description says the facility is in Al Ahsa. "
        "The Eastern Province/Riyadh/GCC wording describes service corridors, not alternate "
        "facility sites. No linked brochure was supplied."
    ),
    466: (
        "OPPORTUNITY_LOCATION_CONFIRMED_AL_AHSA. The source description places the proposed "
        "ecotourism site inside Al-Ahsa National Park. The referenced official Envi-004 brochure "
        "states Location (Region): Al-Ahsa Governate, Eastern Region, and describes an on-site "
        "site/vegetation. This is direct asset-location evidence."
    ),
    671: (
        "OPPORTUNITY_LOCATION_CONFIRMED_AL_AHSA. The official title names Al-Ahsa and the "
        "full source description proposes establishing private international early-years "
        "centers in Al-Ahsa. The referenced brochure title matches the opportunity; its body "
        "is a generic template and is not relied on for geography."
    ),
    1038: (
        "OPPORTUNITY_LOCATION_CONFIRMED_AL_AHSA. The official title names the Al-Ahsaa ISWR; "
        "the source description explicitly says the strategic potable-water reservoirs are "
        "located in Al Ahsaa. Its separate clause about procuring Asir ISWR names another "
        "project and does not contradict the Al-Ahsaa site. Structured region is Sharqia. "
        "The referenced brochure is title-only and is not relied on for geography."
    ),
    1166: (
        "OPPORTUNITY_LOCATION_CONFIRMED_AL_AHSA. Official title is Alahsa intracity Bus Project; "
        "the description specifies an intracity service for residents, tourists, and beneficiaries "
        "in Alahsa. The referenced brochure title matches; its body is a generic template and is "
        "not relied on for geography. This is an operating service footprint, not merely an owner "
        "or market mention."
    ),
    1167: (
        "OPPORTUNITY_LOCATION_CONFIRMED_AL_AHSA. Official title is AlAhsa Bus Stop Stations "
        "Project; the description proposes stations in Al-Ahsa supporting public transport "
        "in the city. The referenced brochure title matches; its body is a generic template and "
        "is not relied on for geography."
    ),
    2358: (
        "OPPORTUNITY_LOCATION_CONFIRMED_AL_AHSA. Official opportunity text names the "
        "Al-Ahsa Maternity and Children's Hospital as the physical ATM lease site. The source "
        "payload contains Furas opportunity number 06-26-183737-46016 and its Furas link. "
        "Coordinates are absent and raw siteArea=2 has no stated unit; neither is used to infer "
        "geography. No matching current Master/reference was found."
    ),
    2359: (
        "OPPORTUNITY_LOCATION_CONFIRMED_AL_AHSA. Official opportunity text names Prince Saud "
        "bin Jalawi Hospital in Al-Ahsa as the physical ATM lease site. The source payload "
        "contains Furas opportunity number 06-26-183737-46015 and its Furas link. Coordinates "
        "are absent and raw siteArea=2 has no stated unit; neither is used to infer geography. "
        "No matching current Master/reference was found."
    ),
    2360: (
        "OPPORTUNITY_LOCATION_CONFIRMED_AL_AHSA. Official opportunity text names King Faisal "
        "Hospital in Al-Ahsa as the physical ATM lease site. The source payload contains Furas "
        "opportunity number 06-26-183737-46017 and its Furas link. Coordinates are absent and "
        "raw siteArea=2 has no stated unit; neither is used to infer geography. No matching "
        "current Master/reference was found."
    ),
    2361: (
        "OPPORTUNITY_LOCATION_CONFIRMED_AL_AHSA. Official opportunity text names Al-Omran "
        "General Hospital in Al-Ahsa as the physical ATM lease site. The source payload contains "
        "Furas opportunity number 06-26-183737-46018 and its Furas link. Coordinates are absent "
        "and raw siteArea=2 has no stated unit; neither is used to infer geography. No matching "
        "current Master/reference was found."
    ),
    2362: (
        "OPPORTUNITY_LOCATION_CONFIRMED_AL_AHSA. Official opportunity text names the Mental "
        "Health Hospital in Al-Ahsa as the physical ATM lease site. The source payload contains "
        "Furas opportunity number 06-26-183737-46019 and its Furas link. Coordinates are absent "
        "and raw siteArea=2 has no stated unit; neither is used to infer geography. No matching "
        "current Master/reference was found."
    ),
}

TARGET_IDS = sorted(EVIDENCE)
API = "http://127.0.0.1:8000"


def main():
    with SessionLocal() as db:
        source = db.scalar(select(Source).where(Source.source_key == "invest-saudi"))
        assert source is not None
        for record_id in TARGET_IDS:
            row = db.get(SourceOpportunity, record_id)
            assert row is not None and row.source_id == source.id
            assert row.master_opportunity_id is None
            raw = row.raw_data_json or {}
            assert raw.get("qualified_location") is False
            review = db.scalar(select(LocationReview).where(
                LocationReview.source_id == source.id,
                LocationReview.external_id == row.source_opportunity_id,
            ))
            assert review is not None and review.status == "PENDING"
            assert review.source_record_id == row.id
            review.evidence = EVIDENCE[record_id]
            review.reason = "Targeted evidence review confirmed opportunity/site geography in Al-Ahsa."

        # The 14-hit locality screen contains one additional Invest Saudi item. Its
        # multi-city title includes Al-Ahsa but its structured region is Al Madinah and
        # the brochure is a placeholder, so retain it as an explicit pending case.
        extra = db.get(SourceOpportunity, 601)
        assert extra is not None and extra.master_opportunity_id is None
        extra_raw = extra.raw_data_json or {}
        assert extra_raw.get("qualified_location") is False
        review_601 = db.scalar(select(LocationReview).where(
            LocationReview.source_id == extra.source_id,
            LocationReview.external_id == extra.source_opportunity_id,
        ))
        if review_601 is None:
            review_601 = LocationReview(
                source_id=extra.source_id,
                external_id=extra.source_opportunity_id,
                source_record_id=extra.id,
                title=extra.source_title,
                sector=extra_raw.get("normalized_taxonomy", {}).get("sector"),
                source_location=extra.raw_location,
                description=extra_raw.get("description"),
                latitude=None,
                longitude=None,
                evidence=(
                    "INSUFFICIENT_EVIDENCE_REVIEW. The title lists Al-Ahsa among several city "
                    "venues, but the structured region is Al Madinah and the referenced PDF is "
                    "a generic placeholder with no populated location or opportunity details. "
                    "Do not infer an Al-Ahsa asset from the city list alone."
                ),
                confidence_score=0.0,
                reason="Structured location conflicts with a multi-city title; verify a project/site in Al-Ahsa.",
                status="PENDING",
                created_at=datetime.now(timezone.utc),
            )
            db.add(review_601)

        # The NCP row is a verified same-article technical alias of the source
        # listing already on Master 228. Link only this one row and persist a
        # reversible before/after identity event; leave source payload untouched.
        ncp_alias = db.get(SourceOpportunity, 2810)
        ncp_survivor = db.get(Opportunity, 228)
        ncp_existing = db.get(SourceOpportunity, 2781)
        assert ncp_alias and ncp_survivor and ncp_existing
        assert ncp_alias.master_opportunity_id is None
        assert ncp_survivor.merged_into_id is None
        assert ncp_existing.master_opportunity_id == 228
        assert ncp_alias.source_id == ncp_existing.source_id
        assert ncp_alias.source_url == ncp_existing.source_url
        assert ncp_alias.source_title == ncp_existing.source_title
        assert ncp_alias.source_url == "https://ncp.gov.sa/en/MediaCenter/News/Pages/FoodSafetyLabs.aspx"
        db.flush()
        db.add(SystemEvent(
            event_type="SOURCE_RECORD_IDENTITY_LINKED",
            created_at=datetime.now(timezone.utc),
            payload={
                "source_record_id": ncp_alias.id,
                "source_key": "ncp",
                "external_id": ncp_alias.source_opportunity_id,
                "master_id_before": None,
                "master_id_after": ncp_survivor.id,
                "reversible": True,
                "rule": "same_source_exact_article_url_and_normalized_title_v1",
                "evidence": {
                    "same_source_id": True,
                    "same_exact_official_article_url": True,
                    "same_exact_title": True,
                    "same_raw_multimunicipality_scope_including_al_ahsa": True,
                    "existing_master_id": 228,
                    "matching_linked_source_record_id": 2781,
                },
                "raw_payload_modified": False,
                "source_observations_modified": False,
                "actor": "targeted_master_identity_eligibility_review",
            },
        ))
        ncp_alias.master_opportunity_id = ncp_survivor.id
        db.commit()

    approvals = []
    for record_id in TARGET_IDS:
        with SessionLocal() as db:
            row = db.get(SourceOpportunity, record_id)
            review = db.scalar(select(LocationReview).where(
                LocationReview.source_id == row.source_id,
                LocationReview.external_id == row.source_opportunity_id,
            ))
            review_id = review.id
        req = Request(f"{API}/api/admin/location-reviews/{review_id}/accept", method="POST")
        try:
            with urlopen(req, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
                assert response.status == 200 and payload.get("ok") and payload.get("status") == "ACCEPTED"
        except HTTPError as exc:
            raise RuntimeError(f"Location review {review_id} failed: HTTP {exc.code} {exc.read().decode('utf-8')}") from exc
        with SessionLocal() as db:
            row = db.get(SourceOpportunity, record_id)
            assert row.master_opportunity_id is not None
            master = db.get(Opportunity, row.master_opportunity_id)
            assert master and master.merged_into_id is None
            assert (row.raw_data_json or {}).get("qualified_location") is True
            assert (row.raw_data_json or {}).get("location_detection_method") == "ADMIN_LOCATION_REVIEW"
            approvals.append({"source_record_id": record_id, "external_id": row.source_opportunity_id,
                              "review_id": review_id, "master_id": master.id,
                              "master_title": master.title_ar})

    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        tx = conn.begin()
        conn.execute(text("SET TRANSACTION READ ONLY"))
        counts = dict(conn.execute(text("""
            SELECT
              (SELECT count(*) FROM opportunities) AS total_masters,
              (SELECT count(*) FROM opportunities WHERE merged_into_id IS NULL) AS current_masters,
              (SELECT count(*) FROM opportunities WHERE merged_into_id IS NOT NULL) AS merged_masters,
              (SELECT count(*) FROM source_opportunities) AS source_rows,
              (SELECT count(*) FROM source_opportunities WHERE master_opportunity_id IS NOT NULL) AS linked_rows,
              (SELECT count(*) FROM source_opportunities WHERE master_opportunity_id IS NULL) AS unlinked_rows,
              (SELECT count(*) FROM source_opportunities WHERE coalesce((raw_data_json->>'qualified_location')::boolean,false)) AS literal_qualified_rows,
              (SELECT count(*) FROM source_opportunities WHERE coalesce((raw_data_json->>'qualified_location')::boolean,false) AND master_opportunity_id IS NULL) AS literal_qualified_unlinked,
              (SELECT count(*) FROM source_opportunities WHERE source_id=(SELECT id FROM sources WHERE source_key='ncp') AND master_opportunity_id=228) AS ncp_228_rows,
              (SELECT count(*) FROM opportunities o WHERE o.merged_into_id IS NULL AND NOT EXISTS (SELECT 1 FROM source_opportunities so WHERE so.master_opportunity_id=o.id)) AS current_masters_without_sources,
              (SELECT count(*) FROM location_reviews WHERE status='PENDING') AS pending_location_reviews
        """)).mappings().one())
        tx.commit()

    print(json.dumps({"approvals": approvals, "counts": counts,
                      "ncp_source_record_2810_linked_to_master_228": True,
                      "location_601_retained_pending_review": True}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
