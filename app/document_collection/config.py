"""Fail-closed feature switches for the document collection subsystem."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _enabled(name: str) -> bool:
    return os.getenv(name, "false").strip().casefold() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class CollectionFeatureFlags:
    engine: bool
    manual_collection: bool
    scheduled_collection: bool
    candidate_staging: bool
    automatic_approval: bool
    automatic_publication: bool

    @classmethod
    def from_environment(cls) -> "CollectionFeatureFlags":
        return cls(
            engine=_enabled("DOCUMENT_COLLECTION_ENGINE_ENABLED"),
            manual_collection=_enabled("DOCUMENT_COLLECTION_MANUAL_ENABLED"),
            scheduled_collection=_enabled("DOCUMENT_COLLECTION_SCHEDULED_ENABLED"),
            candidate_staging=_enabled("DOCUMENT_COLLECTION_STAGING_ENABLED"),
            automatic_approval=_enabled("DOCUMENT_COLLECTION_AUTO_APPROVAL_ENABLED"),
            automatic_publication=_enabled("DOCUMENT_COLLECTION_AUTO_PUBLICATION_ENABLED"),
        )

    def manual_tasks_allowed(self) -> bool:
        return self.engine and self.manual_collection and self.candidate_staging


def feature_flags() -> CollectionFeatureFlags:
    return CollectionFeatureFlags.from_environment()
