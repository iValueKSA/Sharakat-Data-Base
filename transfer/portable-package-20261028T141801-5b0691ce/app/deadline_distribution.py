"""Shared, conservative classification for active deadline distribution.

Only an explicit, valid canonical submission_deadline can enter one of the
four dated buckets. Raw source dates and other date fields are intentionally
not promoted here.
"""
from __future__ import annotations

from datetime import date


ACTIVE_OPPORTUNITY_STATUSES = ("متاحة", "Announced", "ANNOUNCED", "PUBLISHED", "AVAILABLE", "ACTIVE", "منشورة")


DEADLINE_BUCKETS = (
    ("7d", "خلال 7 أيام", "#378AA4", 0, 7),
    ("8_14d", "8–14 يومًا", "#006E61", 8, 14),
    ("15_30d", "15–30 يومًا", "#C39853", 15, 30),
    ("over_30d", "أكثر من 30 يومًا", "#7953A9", 31, None),
    ("no_deadline", "بدون موعد محدد", "#989899", None, None),
)


def deadline_bucket_key(value: str | None, today: date) -> str:
    """Return a dated bucket only for a valid future canonical ISO deadline."""
    if not value:
        return "no_deadline"
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        return "no_deadline"
    if parsed.isoformat() != value or parsed < today:
        return "no_deadline"
    days = (parsed - today).days
    if days <= 7:
        return "7d"
    if days <= 14:
        return "8_14d"
    if days <= 30:
        return "15_30d"
    return "over_30d"


def classify_deadline_population(rows, today: date) -> dict[str, list[int]]:
    """Partition (master_id, canonical_deadline) pairs into disjoint buckets."""
    buckets = {key: [] for key, *_ in DEADLINE_BUCKETS}
    for master_id, deadline in rows:
        buckets[deadline_bucket_key(deadline, today)].append(int(master_id))
    return buckets
