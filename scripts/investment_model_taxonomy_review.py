"""Read-only source and Master audit for the Investment Model dimension."""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import SessionLocal
from app.models import Opportunity, Source, SourceOpportunity, TaxonomyMapping
from app.standardization import STANDARDIZATION_VERSION, comparison_key

OUT = Path("docs/validation/data/investment-model-taxonomy")
OFFICIAL_SOURCES = {
    "furas": "فرص – البوابة الموحدة للاستثمار",
    "alahsa-opportunities": "منصة الفرص الاستثمارية بالأحساء",
    "ahda": "هيئة تطوير الأحساء",
    "invest-saudi": "استثمر في السعودية",
    "kfu": "جامعة الملك فيصل",
    "modon": "مدن",
    "ncp": "المركز الوطني للتخصيص",
    "nhc": "NHC الاستثمار",
    "pif": "بوابة القطاع الخاص لصندوق الاستثمارات العامة",
    "mwan": "موان",
}
SEARCH_TERMS = [
    "PPP", "PPP_PROJECT", "PPP_PROJECT_ANNOUNCEMENT", "Public-Private Partnership",
    "BTO", "BOT", "BOOT", "BOO", "DBFO", "DBFOM", "DBFOMT", "DBFMOT", "DBFM",
    "EOMT", "ROMT", "Concession", "امتياز", "حق انتفاع", "مساطحة", "مشاركة بالإيرادات",
    "Revenue Share", "Revenue Sharing", "Joint Venture", "JV", "Development Agreement",
    "Management Agreement", "Operation Agreement", "LEASE_OPPORTUNITY", "TemporaryRental",
    "تأجير", "إيجار", "Lease", "Operating", "COMMERCIAL_FACILITY_OPPORTUNITY",
    "INVESTMENT_OPPORTUNITY",
]


def strings(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)
    elif isinstance(value, str):
        yield value


def nested_values(value, prefix=""):
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if any(word in str(key).casefold() for word in (
                "model", "contract", "lease", "concession", "partnership", "procurement",
            )):
                if child not in (None, "", [], {}):
                    yield path, child
            yield from nested_values(child, path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from nested_values(child, f"{prefix}[{index}]")


def term_pattern(term: str):
    escaped = re.escape(term)
    if term.isascii() and term.replace("_", "").replace("-", "").isalnum():
        return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.I)
    return re.compile(escaped, re.I)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        sources = {row.source_key: row for row in db.scalars(select(Source)).all()}
        records = db.scalars(select(SourceOpportunity).order_by(SourceOpportunity.id)).all()
        masters = db.scalars(select(Opportunity).where(Opportunity.merged_into_id.is_(None)).order_by(Opportunity.id)).all()
        master_by_id = {row.id: row for row in masters}

        candidate_counts = Counter()
        candidate_masters = defaultdict(set)
        candidate_record_ids = defaultdict(set)
        candidate_example = {}
        model_field_counts = Counter()
        source_totals = Counter()
        source_model_raw = Counter()
        source_model_projection = Counter()
        source_model_canonical = Counter()
        source_model_unmapped = Counter()
        source_model_wrong_dimension = Counter()
        source_model_review = Counter()
        keyword_counts = Counter()
        keyword_masters = defaultdict(set)
        keyword_examples = defaultdict(list)
        model_projection_records = defaultdict(set)
        model_missing_projection_records = defaultdict(set)
        records_by_source = defaultdict(list)

        for record in records:
            source_key = record.source.source_key
            source_totals[source_key] += 1
            raw = record.raw_data_json if isinstance(record.raw_data_json, dict) else {}
            standardized = record.standardized_data_json if isinstance(record.standardized_data_json, dict) else {}
            fields = standardized.get("fields") if isinstance(standardized.get("fields"), dict) else {}
            records_by_source[source_key].append(record)

            # Direct source-model fields and separately typed contractual fields.
            for path, value in nested_values(raw):
                vals = value if isinstance(value, list) else [value]
                for item in vals:
                    if isinstance(item, (str, int, float)) and str(item).strip():
                        key = (source_key, path, str(item).strip())
                        candidate_counts[key] += 1
                        candidate_example.setdefault(key, str(raw.get("title") or record.source_title))
                        candidate_record_ids[key].add(record.id)
                        if record.master_opportunity_id in master_by_id:
                            candidate_masters[key].add(record.master_opportunity_id)
                        if path.split(".")[-1].casefold() == "investment_model":
                            source_model_raw[source_key] += 1

            model_projection = fields.get("investment_model") or {}
            model_review = fields.get("investment_model_evidence") or {}
            for item, kind in ((model_projection, "investment_model"), (model_review, "investment_model_evidence")):
                if not isinstance(item, dict):
                    continue
                raw_value = item.get("raw")
                meaningful = raw_value not in (None, "", [], {})
                canonical_label = item.get("canonical_label")
                canonical_id_value = item.get("canonical_id")
                # The engine writes empty field objects for every record. Only
                # count a source projection when it carries actual model evidence.
                if meaningful:
                    identity = str(raw_value).strip()
                    key = (source_key, f"standardized.fields.{kind}", identity)
                    candidate_counts[key] += 1
                    candidate_example.setdefault(key, str(raw.get("title") or record.source_title))
                    candidate_record_ids[key].add(record.id)
                    if record.master_opportunity_id in master_by_id:
                        candidate_masters[key].add(record.master_opportunity_id)
                    model_projection_records[source_key].add(record.id)
                elif canonical_id_value == "investment_model:missing" or (not canonical_id_value and not canonical_label):
                    model_missing_projection_records[source_key].add(record.id)
                status = str(item.get("mapping_status") or "").upper()
                if item.get("canonical_id") and not str(item["canonical_id"]).startswith("unmapped:") and meaningful:
                    source_model_canonical[source_key] += 1
                if meaningful and (status == "UNMAPPED" or str(item.get("canonical_id") or "").startswith("unmapped:")):
                    source_model_unmapped[source_key] += 1
                if meaningful and status == "REVIEW_REQUIRED":
                    source_model_review[source_key] += 1
                if meaningful and status in {"DIMENSION_REDIRECT", "WRONG_DIMENSION"}:
                    source_model_wrong_dimension[source_key] += 1

            haystack = "\n".join(strings(raw))
            for term in SEARCH_TERMS:
                match = term_pattern(term).search(haystack)
                if match:
                    keyword_counts[(source_key, term)] += 1
                    if record.master_opportunity_id in master_by_id:
                        keyword_masters[(source_key, term)].add(record.master_opportunity_id)
                    start, end = max(0, match.start() - 110), min(len(haystack), match.end() + 180)
                    keyword_examples[(source_key, term)].append({
                        "record_id": record.id,
                        "master_id": record.master_opportunity_id,
                        "snippet": re.sub(r"\s+", " ", haystack[start:end]),
                    })

        # A Master-level Investment Model is not present in the pre-migration schema.
        master_values = Counter(getattr(master, "investment_model", None) for master in masters)
        taxonomy_rows = db.scalars(select(TaxonomyMapping)).all()
        current_model_taxonomy_rows = [
            row for row in taxonomy_rows
            if "investment_model" in (row.mapping_rule or "").casefold()
            or (row.source_value or "").casefold() in {"ppp", "eomt", "boot", "dbfom", "romt", "lease"}
        ]

    candidate_rows = []
    for key, count in sorted(candidate_counts.items()):
        source_key, field, value = key
        candidate_rows.append({
            "source_key": source_key,
            "source": OFFICIAL_SOURCES.get(source_key, source_key),
            "source_field": field,
            "raw_or_projected_value": value,
            "source_record_count": count,
            "source_record_ids": ",".join(str(value) for value in sorted(candidate_record_ids[key])),
            "master_count": len(candidate_masters[key]),
            "master_ids": ",".join(str(value) for value in sorted(candidate_masters[key])),
            "example_title": candidate_example[key],
        })
    with (OUT / "source-candidates.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(candidate_rows[0]) if candidate_rows else ["source_key"])
        writer.writeheader()
        writer.writerows(candidate_rows)

    coverage = []
    for source_key, source_name in OFFICIAL_SOURCES.items():
        rows = records_by_source[source_key]
        model_present = len({
            record.id for record in rows
            if isinstance(record.raw_data_json, dict)
            and any(path.split(".")[-1].casefold() == "investment_model"
                    and value not in (None, "", [], {})
                    for path, value in nested_values(record.raw_data_json))
        })
        coverage.append({
            "source_key": source_key, "source": source_name, "records": len(rows),
            "raw_model_present": model_present,
            "standardized_model_projection_records": len(model_projection_records[source_key]),
            "canonical_model_projection_records": source_model_canonical[source_key],
            "missing_model_projection_records": len(model_missing_projection_records[source_key]),
            "unmapped_model_projection_records": source_model_unmapped[source_key],
            "wrong_dimension_model_projection_records": source_model_wrong_dimension[source_key],
            "review_required_model_projection_records": source_model_review[source_key],
        })
    with (OUT / "source-coverage-before.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(coverage[0]))
        writer.writeheader()
        writer.writerows(coverage)

    terms = [{
        "source_key": source, "term": term, "records_with_term": count,
        "unique_linked_masters": len(keyword_masters[(source, term)]),
        "record_ids": ",".join(str(item["record_id"]) for item in keyword_examples[(source, term)]),
        "master_ids": ",".join(str(item["master_id"]) for item in keyword_examples[(source, term)] if item["master_id"] in master_by_id),
        "evidence_snippets": " || ".join(item["snippet"] for item in keyword_examples[(source, term)][:5]),
    } for (source, term), count in sorted(keyword_counts.items())]
    with (OUT / "keyword-occurrences.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_key", "term", "records_with_term", "unique_linked_masters", "record_ids", "master_ids", "evidence_snippets"])
        writer.writeheader()
        writer.writerows(terms)

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "standardization_engine_version_before": STANDARDIZATION_VERSION,
        "total_eligible_masters": len(masters),
        "source_opportunity_records": len(records),
        "master_investment_model_column_present": hasattr(Opportunity, "investment_model"),
        "master_investment_model_values_before": {str(key): count for key, count in master_values.items()},
        "canonical_investment_model_registry_in_taxonomy_mappings": len(current_model_taxonomy_rows),
        "current_source_model_field_record_counts": dict(source_model_raw),
        "standardized_investment_model_projection_records": sum(map(len, model_projection_records.values())),
        "candidate_value_rows": len(candidate_rows),
        "candidate_values_csv": "source-candidates.csv",
        "term_occurrences_csv": "keyword-occurrences.csv",
        "source_coverage_csv": "source-coverage-before.csv",
        "official_source_record_counts": [
            {"source_key": key, "source": OFFICIAL_SOURCES[key], "records": source_totals[key]}
            for key in OFFICIAL_SOURCES
        ],
        "detected_candidate_fields": [
            {"source_key": source, "field": field, "value": value, "records": count,
             "master_count": len(candidate_masters[(source, field, value)])}
            for (source, field, value), count in sorted(candidate_counts.items())
        ],
        "keyword_occurrences": terms,
        "decision": "Read-only baseline; no rows, payloads, identities, links, or service state changed.",
    }
    (OUT / "baseline-audit.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "generated_at_utc": summary["generated_at_utc"],
        "masters": len(masters), "source_records": len(records),
        "candidate_value_rows": len(candidate_rows),
        "raw_model_records": dict(source_model_raw),
        "projected_model_records": sum(map(len, model_projection_records.values())),
        "model_taxonomy_rows": len(current_model_taxonomy_rows),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
