"""Dry-run the v16 Investment Model rules without opening a database session."""
from __future__ import annotations

import json

from app.standardization import standardize_field, standardize_opportunity


def main():
    lease = standardize_field("investment_model", "LEASE_OPPORTUNITY", source_key="kfu")
    eomt = standardize_field("investment_model", "EOMT", source_key="ncp")
    missing = standardize_field("investment_model", None, source_key="ncp")
    wrong_dimension = standardize_field("investment_model", "PPP_PROJECT", source_key="ncp")
    unknown = standardize_field("investment_model", "FUTURE_UNKNOWN_MODEL", source_key="ncp")
    kfu_review = standardize_opportunity(
        {"title_ar": "مزايدة خدمات", "opportunity_type": "COMMERCIAL_FACILITY_OPPORTUNITY", "investment_model": None},
        source_key="kfu", source_record={"raw": {"content_type": "COMMERCIAL_FACILITY_OPPORTUNITY"}, "title": "مزايدة خدمات"},
    )
    ahda_review = standardize_opportunity(
        {"title_ar": "تطوير فندق", "investment_model": None},
        source_key="ahda", source_record={"raw": {"raw_text": "نموذج الاستثمار: خيارات متعددة (تأجير، مشاركة إيرادات، أو ملكية كاملة)."}, "title": "تطوير فندق"},
    )

    assert lease["canonical_id"] == "investment_model:lease" and lease["canonical_label"] == "التأجير"
    assert eomt["canonical_id"] == "investment_model:eomt" and eomt["canonical_label"] == "التجهيز والتشغيل والصيانة والنقل"
    assert missing["canonical_id"] == "investment_model:missing" and missing["canonical_label"] == "غير محدد"
    assert wrong_dimension["mapping_status"] == "DIMENSION_REDIRECT" and wrong_dimension["canonical_id"] == "investment_model:missing"
    assert unknown["mapping_status"] == "UNMAPPED" and unknown["canonical_id"].startswith("unmapped:investment_model:")
    assert kfu_review["values"]["investment_model"] is None
    assert kfu_review["metadata"]["fields"]["investment_model_evidence"]["mapping_status"] == "REVIEW_REQUIRED"
    assert ahda_review["values"]["investment_model"] is None
    assert ahda_review["metadata"]["fields"]["investment_model_evidence"]["mapping_status"] == "REVIEW_REQUIRED"
    print(json.dumps({
        "engine_version": __import__("app.standardization", fromlist=["STANDARDIZATION_VERSION"]).STANDARDIZATION_VERSION,
        "lease": lease, "eomt": eomt, "missing": missing,
        "wrong_dimension": wrong_dimension, "unknown": unknown,
        "kfu_ambiguous_review": True, "ahda_multiple_options_review": True,
        "production_database_used": False, "source_sync_started": False,
    }, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
