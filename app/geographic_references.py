"""Validation and transactional import for public national geography references.

Public official references may be used without waiting for separate written
reuse permission. Access must remain anonymous/public and source evidence,
stable IDs, hierarchy, and completeness still need to be verified.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .geography import geography_key
from .models import GeographicReferenceDataset, GeographicReferenceUnit

LEVEL_PARENT = {"country": None, "region": "country", "governorate": "region", "city": "governorate"}
SCOPES = {"SPECIFIC_LOCATION", "MULTIPLE_VERIFIED_LOCATIONS", "REGION_WIDE", "NATIONWIDE", "UNSPECIFIED"}


def canonical_dataset_digest(units: list[dict]) -> str:
    # Unit array order is presentation/source transport detail. Import and
    # database readback use different stable orderings, so the digest must be
    # based on immutable unit identities rather than list position.
    ordered = sorted(units, key=lambda row: (str(row.get("level") or "").strip().lower(),
                                              str(row.get("external_id") or "").strip()))
    payload = json.dumps(ordered, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_reference_payload(metadata: dict, units: list[dict], *, test_mode: bool = False) -> dict:
    """Return a dry-run validation report; no DB writes are performed."""
    errors: list[str] = []
    warnings: list[str] = []
    required = ("dataset_key", "version", "operator", "source_url", "content_sha256", "effective_date")
    for key in required:
        if not str(metadata.get(key) or "").strip():
            errors.append(f"MISSING_METADATA:{key}")
    if not str(metadata.get("source_url") or "").startswith("https://"):
        errors.append("INVALID_SOURCE_URL")
    if metadata.get("public_access_verified") is not True:
        errors.append("PUBLIC_ACCESS_NOT_VERIFIED")
    if metadata.get("source_authority_verified") is not True:
        errors.append("SOURCE_AUTHORITY_NOT_VERIFIED")
    effective_date=str(metadata.get("effective_date") or "").strip()
    if effective_date and not (test_mode and metadata.get("test_only") is True and effective_date.startswith("TEST_ONLY_")):
        try:
            date.fromisoformat(effective_date)
        except ValueError:
            errors.append("INVALID_EFFECTIVE_DATE")
    if metadata.get("stable_external_ids") is not True:
        errors.append("STABLE_EXTERNAL_IDS_NOT_ATTESTED")
    if metadata.get("parent_relationships_verified") is not True:
        errors.append("PARENT_RELATIONSHIPS_NOT_VERIFIED")
    if metadata.get("completeness_verified") is not True:
        errors.append("COMPLETENESS_NOT_VERIFIED")
    if not units:
        errors.append("EMPTY_DATASET")

    coverage = metadata.get("coverage_by_level") or {}
    expected_counts = metadata.get("expected_counts") or {}
    if not test_mode and (coverage.get("region") is not True or coverage.get("governorate") is not True):
        errors.append("REGION_GOVERNORATE_COVERAGE_NOT_VERIFIED")
    if not test_mode and coverage.get("region") is True and expected_counts.get("region") != 13:
        errors.append("SAUDI_REGION_COUNT_MUST_BE_13")

    identities: set[tuple[str, str]] = set()
    by_identity: dict[tuple[str, str], dict] = {}
    for index, row in enumerate(units):
        level = str(row.get("level") or "").strip().lower()
        external_id = str(row.get("external_id") or "").strip()
        if level not in LEVEL_PARENT:
            errors.append(f"INVALID_LEVEL:{index}")
            continue
        if not external_id:
            errors.append(f"MISSING_STABLE_ID:{index}")
            continue
        if (metadata.get("test_only") is True or external_id.startswith("TEST_")) and not test_mode:
            errors.append(f"TEST_FIXTURE_NOT_ALLOWED:{level}:{external_id}")
        identity = (level, external_id)
        if identity in identities:
            errors.append(f"DUPLICATE_ID:{level}:{external_id}")
        identities.add(identity)
        by_identity[identity] = row
        if not str(row.get("name_ar") or "").strip():
            errors.append(f"MISSING_ARABIC_NAME:{level}:{external_id}")
        if not isinstance(row.get("source_record"), dict):
            errors.append(f"MISSING_SOURCE_RECORD:{level}:{external_id}")
        if LEVEL_PARENT[level] is None and row.get("parent_external_id") not in (None, ""):
            errors.append(f"COUNTRY_HAS_PARENT:{external_id}")
        elif LEVEL_PARENT[level] is not None and not str(row.get("parent_external_id") or "").strip():
            errors.append(f"MISSING_PARENT:{level}:{external_id}")

    for level, external_id in identities:
        row = by_identity[(level, external_id)]
        parent_level = LEVEL_PARENT[level]
        parent_id = str(row.get("parent_external_id") or "").strip()
        if parent_level and parent_id and any(candidate_id == parent_id and candidate_level != parent_level
                                              for candidate_level, candidate_id in identities):
            errors.append(f"INVALID_PARENT_LEVEL:{level}:{external_id}:{parent_id}")
        elif parent_level and parent_id and (parent_level, parent_id) not in identities:
            errors.append(f"UNKNOWN_PARENT:{level}:{external_id}:{parent_id}")

    digest = canonical_dataset_digest(units)
    supplied_digest = str(metadata.get("content_sha256") or "").lower()
    if supplied_digest and supplied_digest != digest:
        errors.append("CONTENT_DIGEST_MISMATCH")
    counts = {level: sum(1 for row in units if str(row.get("level") or "").strip().lower() == level)
              for level in LEVEL_PARENT}
    if metadata.get("completeness_verified") is True:
        for level, expected in expected_counts.items():
            if level in counts and expected != counts[level]:
                errors.append(f"RECORD_COUNT_MISMATCH:{level}:{expected}:{counts[level]}")
        for level, complete in coverage.items():
            if complete is True and level in LEVEL_PARENT and level not in expected_counts:
                errors.append(f"EXPECTED_COUNT_MISSING:{level}")
    return {"valid": not errors, "errors": sorted(set(errors)), "warnings": warnings,
            "unit_count": len(units), "counts_by_level": counts, "computed_sha256": digest}


def evaluate_reference_readiness(metadata: dict, units: list[dict], *, is_current: bool = True) -> dict:
    """Evaluate Phase 1 readiness without importing rows or changing state."""
    report = validate_reference_payload(metadata, units)
    reasons = list(report["errors"])
    if not is_current:
        reasons.append("REFERENCE_NOT_CURRENT")
    normalized = set()
    for reason in reasons:
        if reason == "PUBLIC_ACCESS_NOT_VERIFIED":
            normalized.add("public_access_not_verified")
        elif reason == "SOURCE_AUTHORITY_NOT_VERIFIED":
            normalized.add("source_authority_not_verified")
        elif reason == "MISSING_METADATA:version":
            normalized.add("version_missing")
        elif reason == "MISSING_METADATA:effective_date":
            normalized.add("effective_date_missing")
        elif reason == "STABLE_EXTERNAL_IDS_NOT_ATTESTED" or reason.startswith("MISSING_STABLE_ID:"):
            normalized.add("stable_ids_missing")
        elif reason.startswith(("PARENT_RELATIONSHIPS_", "UNKNOWN_PARENT:", "INVALID_PARENT_LEVEL:")):
            normalized.add("parent_relationship_missing")
        elif reason.startswith(("COMPLETENESS_", "REGION_GOVERNORATE_COVERAGE_", "RECORD_COUNT_",
                                "EXPECTED_COUNT_", "SAUDI_REGION_COUNT_")):
            normalized.add("incomplete_membership")
        elif reason.startswith("MISSING_METADATA:operator"):
            normalized.add("source_authority_missing")
        else:
            normalized.add(reason.lower())
    counts = report["counts_by_level"]
    if counts.get("region", 0) == 0:
        normalized.add("region_ids_missing")
    if counts.get("governorate", 0) == 0:
        normalized.add("governorate_ids_missing")
    return {"ready": report["valid"] and is_current, "reasons": sorted(normalized),
            "counts_by_level": counts, "validation": report}


def import_reference_dataset(db: Session, metadata: dict, units: list[dict], *, dry_run: bool = True,
                             test_mode: bool = False) -> dict:
    """Validate then import an immutable dataset version inside the caller's transaction."""
    report = validate_reference_payload(metadata, units, test_mode=test_mode)
    if dry_run:
        return {**report, "dry_run": True, "imported": False}
    if not report["valid"]:
        raise ValueError("Geographic reference validation failed: " + ", ".join(report["errors"]))
    duplicate = db.scalar(select(GeographicReferenceDataset.id).where(
        GeographicReferenceDataset.dataset_key == metadata["dataset_key"],
        GeographicReferenceDataset.version == metadata["version"]))
    if duplicate:
        raise ValueError("Dataset version already exists; imports are immutable")

    dataset = GeographicReferenceDataset(
        dataset_key=metadata["dataset_key"], version=metadata["version"],
        effective_date=metadata.get("effective_date"), operator=metadata["operator"],
        source_url=metadata["source_url"], license_name=metadata.get("license_name"),
        license_url=metadata.get("license_url"), license_verified=False,
        coverage_json=metadata.get("coverage_by_level") or {}, provenance_json={
            **(metadata.get("provenance") or {}),
            "stable_external_ids_verified": metadata.get("stable_external_ids") is True,
            "parent_relationships_verified": metadata.get("parent_relationships_verified") is True,
            "completeness_verified": metadata.get("completeness_verified") is True,
            "expected_counts": metadata.get("expected_counts") or {},
            "public_access_verified": metadata.get("public_access_verified") is True,
            "source_authority_verified": metadata.get("source_authority_verified") is True,
            "license_evidence_url": metadata.get("license_evidence_url"),
            "test_only": bool(metadata.get("test_only")),
        },
        content_sha256=report["computed_sha256"],
        import_status="IMPORTED", is_current=True, created_at=datetime.now(timezone.utc),
        imported_at=datetime.now(timezone.utc))
    prior_versions = db.scalars(select(GeographicReferenceDataset).where(
        GeographicReferenceDataset.dataset_key == metadata["dataset_key"],
        GeographicReferenceDataset.is_current.is_(True))).all()
    for prior in prior_versions:
        prior.is_current = False
    db.add(dataset)
    db.flush()

    unit_ids: dict[tuple[str, str], int] = {}
    for level in LEVEL_PARENT:
        for row in units:
            if str(row.get("level") or "").strip().lower() != level:
                continue
            parent_level = LEVEL_PARENT[level]
            parent_external_id = str(row.get("parent_external_id") or "").strip() or None
            parent_id = unit_ids.get((parent_level, parent_external_id)) if parent_level else None
            unit = GeographicReferenceUnit(
                dataset_id=dataset.id, level=level, external_id=str(row["external_id"]).strip(),
                parent_id=parent_id, parent_external_id=parent_external_id,
                name_ar=str(row["name_ar"]).strip(), name_en=(str(row["name_en"]).strip() if row.get("name_en") else None),
                aliases_json=row.get("aliases") or [], geometry_json=row.get("geometry"),
                source_record_json=row["source_record"])
            db.add(unit)
            db.flush()
            unit_ids[(level, unit.external_id)] = unit.id
    return {**report, "dry_run": False, "imported": True, "dataset_id": dataset.id}


def resolve_reference_alias(db: Session, dataset_id: int, level: str, raw_value: object,
                            *, parent_external_id: str | None = None) -> GeographicReferenceUnit | None:
    """Resolve one published value by exact canonical name or stored alias.

    The raw value remains unchanged. No substring or fuzzy matching is used;
    ambiguous aliases and unknown values return None for review.
    """
    key = geography_key(raw_value)
    if not key or level not in LEVEL_PARENT:
        return None
    query = select(GeographicReferenceUnit).where(
        GeographicReferenceUnit.dataset_id == dataset_id,
        GeographicReferenceUnit.level == level)
    if parent_external_id:
        parent_level = LEVEL_PARENT[level]
        if parent_level is None:
            return None
        parent = db.scalar(select(GeographicReferenceUnit).where(
            GeographicReferenceUnit.dataset_id == dataset_id,
            GeographicReferenceUnit.level == parent_level,
            GeographicReferenceUnit.external_id == parent_external_id))
        if parent is None:
            return None
        query = query.where(GeographicReferenceUnit.parent_id == parent.id)
    matches = []
    for unit in db.scalars(query):
        aliases = [unit.name_ar, unit.name_en, *(unit.aliases_json or [])]
        if any(geography_key(alias) == key for alias in aliases if alias):
            matches.append(unit)
    return matches[0] if len(matches) == 1 else None


def rollback_reference_import(db: Session, dataset_id: int) -> dict:
    """Switch the dataset key back to its latest earlier version without deleting history."""
    dataset = db.get(GeographicReferenceDataset, dataset_id)
    if dataset is None:
        raise ValueError("Unknown geographic reference dataset version")
    dataset.is_current = False
    dataset.import_status = "ROLLED_BACK"
    previous = db.scalars(select(GeographicReferenceDataset).where(
        GeographicReferenceDataset.dataset_key == dataset.dataset_key,
        GeographicReferenceDataset.id != dataset.id,
        GeographicReferenceDataset.import_status == "IMPORTED")
        .order_by(GeographicReferenceDataset.imported_at.desc(), GeographicReferenceDataset.id.desc())).first()
    if previous:
        previous.is_current = True
    provenance=dict(dataset.provenance_json or {})
    history=list(provenance.get("rollback_history") or [])
    history.append({"rolled_back_at":datetime.now(timezone.utc).isoformat(),
                    "restored_dataset_id":previous.id if previous else None})
    provenance["rollback_history"]=history
    dataset.provenance_json=provenance
    db.flush()
    return {"rolled_back_dataset_id": dataset.id, "restored_dataset_id": previous.id if previous else None}
