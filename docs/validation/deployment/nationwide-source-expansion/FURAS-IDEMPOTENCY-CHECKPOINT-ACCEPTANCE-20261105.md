# Furas Idempotency and Checkpoint Recovery Acceptance — 2026-11-05

**Generated at UTC:** 2026-11-05 08:27:51 UTC

## Isolated tests run

### Focused coverage

Command:

docker run --rm --mount "type=bind,source=C:\Sharakat Data Base,target=/workspace,readonly" -w /workspace -e PYTHONPATH=/workspace -e PYTHONDONTWRITEBYTECODE=1 -e DATABASE_URL=sqlite:////tmp/furas-identity-focused.db --entrypoint python alahsa-local-api -m pytest -p no:cacheprovider tests/test_furas_capture_manifest.py tests/test_adapters.py tests/test_nationwide_expansion_safety.py tests/test_ingestion.py tests/test_entity_resolution.py tests/test_autonomous_review_resolution.py tests/test_status_lifecycle.py tests/test_review_evidence.py -q

Result: **162 passed, 1 skipped, 0 failed**. The skip is the optional PostgreSQL advisory-lock concurrency test; no dedicated PostgreSQL test URL was supplied. It is not represented as a pass. The acceptance fixture's stop/resume behavior ran on isolated SQLite/HTTP fixtures.

### Fixed-fixture idempotency

- Same Furas provider ID 01-26-000077 ingested twice in a disposable SQLite database: one SourceOpportunity, one MasterOpportunity, one SourceObservation, raw attributes preserved.
- Two same-source similar-title fixture records with distinct official IDs 01-26-000101 and 01-26-000102 remained two SourceOpportunities and two Masters. No title-only merge occurred.
- Manifest tests preserve integer/string/null source values, verify checksums and page membership, reject tampered/incomplete captures, and ensure an existing manifest cannot be overwritten.
- Existing exact-reference, alias-safety, lifecycle and Furas adapter tests ran in the same focused command.

### Checkpoint interruption and resume

The new fixed-fixture test uses OBJECTIDs 1–121 and the adapter's 100-record page size. It commits page 1, injects a controlled interruption, resumes from that committed checkpoint, and compares the combined records in order—including raw attributes and geometry—with an uninterrupted run. Both have 121 unique provider IDs and complete pagination. The test passed.

### Full regression

The first full-suite attempt omitted pytest-asyncio; four async NCP tests failed to execute, while 699 tests passed and one skipped. This was a test-container setup error. The full suite was rerun after installing pytest-asyncio inside the disposable test container only:

**703 passed, 1 skipped, 0 failed** in 70.97 seconds. The skip is the PostgreSQL advisory-lock concurrency test noted above. Warnings were existing Starlette/httpx and Alembic deprecations; no test failure remained.

No test mutated production business data. No Master promotion, source-key mutation, source-link change, merge, lifecycle change, or removal was executed.
