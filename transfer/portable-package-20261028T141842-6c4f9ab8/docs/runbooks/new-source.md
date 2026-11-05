# Adding a source (future change)

Source integration is complete for the current ten enabled itemized sources. Waha remains registered as `PUBLIC_COVERAGE_LIMITED`, disabled for itemized sync, with zero fabricated opportunity rows. Any future source requires an approved **NEW SOURCE INTEGRATION** change request.

## Change levels and baseline comparison

The final baseline is `ALAHSA_PLATFORM_BASELINE_2026_10`; it supports future changes and is not a freeze. Classify work as a **CHANGE REQUEST**, **ENHANCEMENT**, **BUG FIX**, or **NEW SOURCE INTEGRATION**, and record the baseline impact before implementation.

- **Level 1 — UI / low risk:** presentation-only changes. Verify Arabic labels, RTL, keyboard use, and the five standard viewport sizes; preserve the API and data contracts.
- **Level 2 — business logic / source rules:** source parsing, eligibility, location, canonicalization, freshness, review policy, or exports. Preserve raw provenance; add focused fixture tests and run full isolated regression, then validate relevant live read-only DQ and reconciliations.
- **Level 3 — schema / identity / lifecycle / major integration:** migrations, IDs/merges/removal, authentication, durable job lifecycle, or source platform changes. Require an isolated migration and restore plan, full regression, explicit rollback and audit evidence, and staged validation before enabling any schedule.

## Source onboarding procedure

1. Verify the publisher is official, identify its public itemized surfaces, coverage boundary, terms, and expected update cadence. Keep technical health separate from public coverage.
2. Define deterministic IDs, pagination/completeness checks, raw payload retention, retry/failure semantics, Al-Ahsa/location evidence, investment eligibility, taxonomy mapping, and duplicate identity rules before coding.
3. Add a deterministic adapter with stored representative fixtures and failure/empty/partial-page cases. Do not add credentials, arbitrary user-supplied fetch URLs, or private endpoints.
4. Add source-specific freshness policy, schedule, coverage status/notes, operational alerts, and DQ gates. Preserve source-owner/publisher semantics and never fabricate opportunities for a scope-only source.
5. Run adapter and ingestion focused tests, the full isolated regression, schema/restore checks if applicable, security review for network/input boundaries, and API/UI/export/DQ reconciliation.
6. Validate in staging or a bounded read-only live check. Do not run manual production sync until an explicitly approved activation step; record the source matrix and baseline delta first.
7. Update architecture/coverage records, this runbook, the operational runbook, known limitations, and final handover checklist before enabling scheduled polling.
