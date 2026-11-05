# NCP Investors Portal comparison and integration — 2026-11-03

## Result

**NCP_PREFLIGHT_REMEDIATION=COMPLETE**  
**NCP_PORTAL_INTEGRATION=COMPLETE**  
**NCP_ARCHITECTURE_DECISION=SAME_SOURCE_ENRICHMENT**

The portal is a partly overlapping NCP project catalog with additional unique public records. It is integrated under the existing `ncp` source key: 19 same-project portal records were retained as observations on existing NCP rows, 140 UUID-keyed portal rows were added, and 25 high-confidence unique records were promoted to audited Masters. The other 56 candidate overlaps remain source-only for identity review; 59 records at the official parent stage `Closed Transaction` remain source-only. No existing NCP source row or Master link was removed.

## Preflight and public/private boundary

The failing assertion was stale. It preserved the older assumption that the Investors Portal API was private. The current adapter first reads the portal's public runtime configuration, verifies the advertised HTTPS origin and `/api/v1` path, then anonymously enumerates public project pages and public UUID detail records. There is no login, token, authorization header, CAPTCHA bypass, or restricted endpoint request. The local workspace has no Git metadata, so the exact source-control commit that introduced the public enumerator cannot be recovered; the implementation's parser label is `2026.10.12-ncp-2`.

- **PUBLIC_NCP_SCOPE:** Public English and Arabic SharePoint News archives and public articles; public NCP discovery pages and sitemap; public Investors Portal catalog and public project details.
- **PRIVATE_NCP_SCOPE:** Account-only application submission, bid-management, and restricted pipeline data. Not accessed or probed.
- **PUBLIC_ENDPOINTS:** `https://ncp.gov.sa/en/MediaCenter/News/Pages/default.aspx`; `https://ncp.gov.sa/ar/MediaCenter/News/Pages/default.aspx`; `https://ncp.gov.sa/sitemap.xml`; `https://investors.ncp.gov.sa/home`; `https://investors.ncp.gov.sa/assets/config.prod.json`; `https://investors.ncp.gov.sa/api/v1/projects/pipeline?pageNumber=…&pageSize=…`; `https://investors.ncp.gov.sa/api/v1/projects/{uuid}`.
- **CURRENT_ADAPTER_SCOPE:** Public archive plus anonymously available public portal enumeration, under one NCP publisher identity. Stage, source dates, availability flags, and portal payload remain separate raw evidence.
- **NCP_PUBLIC_PRIVATE_SCOPE_INVARIANT:** PRESERVED. `test_ncp_public_archive_scope_is_separate_from_private_pipeline` passes and asserts public archive scope, public portal/config URLs, no login/auth/token routes, and no request authorization header.

The manual sync completed the English archive and all portal pages. The public Arabic archive's continuation page 12 returned a maintenance response without SharePoint list data; this was recorded as a public-surface limitation, not treated as an empty archive or as a portal failure. The English News archive is the adapter's canonical complete News scope.

## Regression before portal work

The stale assertion was replaced with meaningful current-scope checks, not removed. Pre-portal full regression was **684 passed, 1 skipped, 0 failed**. The adapter's current public behavior—not a private-access exception—was retained.

## Portal enumeration and identity comparison

The public Angular runtime config exposed an anonymous, paginated REST catalog. Enumeration used page size 100 and returned 100 + 59 records, matching the reported total of 159. All 159 UUIDs were unique, and all 159 public detail records were refreshed during the controlled sync. No credentials were used. All 159 records reported `isClosed=false`; none reported `isAvailableToSubmit=true`.

The pre-write baseline was 45 NCP SourceOpportunity rows: 2 linked rows to 1 distinct Master and 43 unlinked rows. Their provider identities were the existing synthetic News/project keys; none contained a portal UUID or official portal reference. Direct ID/URL identity comparison found **0** exact matches, **159** portal-only UUIDs, and **45** current-source-only records. Across NCP News, Furas, Invest Saudi, PIF, NHC, MODON, MWAN, RCJY, RCU, and all 6,632 current Masters, project-text/title matching produced candidates only; title similarity never authorized a link.

| Final comparison category | Count | Action |
|---|---:|---|
| A — exact existing NCP ID match | 0 | No exact IDs were present |
| B — deterministic same NCP project | 19 | Append portal observation to existing News row; preserve its row ID and link |
| C — new unique NCP opportunity | 25 | Insert source row and create an audited Master |
| D — identity review | 56 | Keep source-only; no Master/link action |
| E — historical/noncurrent | 59 | Keep source-only; preserve `Closed Transaction` stage independently |
| F — not qualifying | 0 | — |

**NCP_INVESTORS_PORTAL_RELATION_TO_EXISTING_NCP=PARTIAL_OVERLAP_WITH_ADDITIONAL_UNIQUE_RECORDS.** Stage `Closed Transaction` does not rewrite `isClosed=false` or map to `CANCELLED`/`EXPIRED`. The separate availability flag does not become lifecycle status.

### Field richness for the 19 same-project records

Coverage counts below are out of 19 matched projects. Conflicts were 0 in every comparison. Administrative region/governorate fields and an explicit publication date are absent from portal detail; raw location text is not promoted to canonical geography. `createdOn`, `stageStartDate`, and `deadline` retain their source semantics.

| Field | Current NCP | Portal | Portal richer |
|---|---:|---:|---|
| Project stage | 19 | 19 | No |
| Status / availability evidence | 3 | 19 | Yes |
| Authority | 7 | 17 | Yes |
| Sector | 0 | 19 | Yes |
| Transaction model | 19 | 19 | No |
| PPP model | 19 | 15 | No |
| Administrative region | 1 | 0 | No |
| Governorate | 0 | 0 | No |
| Raw city/locality/location text | 7 | 19 | Yes |
| Explicit publication date | 19 | 0 | No |
| EOI-specific dates | 12 | 12 | No |
| RFQ-specific dates | 5 | 12 | Yes |
| RFP-specific dates | 1 | 6 | Yes |
| Stage-specific deadline evidence | 3 | 18 | Yes |
| Documents | 0 | 0 | No |
| Record detail URL | 19 | 19 | No |
| Description | 19 | 19 | No |

All date values remain semantically named: publication date, EOI, RFQ, RFP, stage deadline, bid deadline, award, and financial close are not collapsed into one generic deadline. No generic deadline or lifecycle status was projected to a Master.

## Same-source integration and promotion

The existing source registry remains one NCP entry (`source_key=ncp`; configured sources stayed at 13). No second NCP organization was added and no independent-corroboration count was created. The controlled manual NCP sync was job **757**, status `SUCCESS`, trigger `manual`:

- 159 portal UUIDs and 159 immutable public portal observations captured.
- 19 portal observations attached to the 19 manually adjudicated same-project NCP rows.
- 140 new UUID-keyed NCP SourceOpportunity rows inserted.
- Adapter sync `update_count=1`; 19 is the count of same-project records enriched with portal provenance, not the generic row-update counter.
- 0 automatic Masters created during source capture; 0 bootstrap removals; 0 source rows removed.
- All 45 original NCP source row IDs, external IDs, and Master links were checked against the pre-sync snapshot and preserved (45/45).

The 25 category-C records were promoted in one audited transaction using the dry-run allowlist. Each keeps its UUID as `NCP-{uuid}`, its NCP source row, source field provenance, promotion `SystemEvent`, and the comparison evidence. All 25 have a matching Master and a governed sector-classification audit. Zero existing Master was linked by this transition; the 2 original NCP links to Master 228 remain intact. The 19 same-project News/portal pairs are the 19 duplicate Master actions prevented.

The first full DQ run after promotion exposed 4 sector gates because the portal's exact government macro-sector labels had not yet been mapped into the governed classifier. The data was not left in that state: exact NCP aliases were added for the five previously unmapped macro-sector labels, while the two portal labels already supported by the canonical taxonomy continued to use `الرياضة` and `التعليم`. The 25 explicit NCP sector values were then processed by the governed classifier and audited. Combined source categories remain distinct (`البيئة والمياه والزراعة`, `البلديات والإسكان`, `النقل والخدمات اللوجستية`, `الزكاة والضريبة والجمارك`, and `الحج والعمرة`). No sector gate was weakened. The final full DQ has zero failures.

No city, region, governorate, or coordinates were fabricated or assigned from authority headquarters. Master status remains unknown where the source does not explicitly establish lifecycle status. The portal's stage, availability flag, raw location, and transaction dates remain in source provenance.

## Backups and validation

Three PostgreSQL logical backups were restore-tested in isolated PostgreSQL 16 containers at their respective write boundaries:

| Boundary | Backup | SHA-256 | Restore test |
|---|---|---|---|
| Before the first NCP live write | `backups/ncp-preflight-20261103.dump` | `99A14A28FAB1ECD5FDB61684EFB4E6C9C3A096EBB3D13E7BE7F623AE0B3F7BAA` | Passed; preflight counts matched |
| After capture, before Master promotion | `backups/ncp-pre-master-promotion-20261103.dump` | `D77980B0B2EE21315AEB98C41BB3ADDF349DD615124A238AAAA80040A184AA67` | Passed |
| Before sector remediation | `backups/ncp-pre-sector-remediation-20261103.dump` | `F4749C371022DDA54301280D1CB47721541B76820C1635864DB0BB4CF592A57F` | Passed; 6,678 Master rows and 25 NCP portal Master links restored |

- Focused NCP adapter tests: **35 passed**.
- Final isolated full regression, including the original NCP test name: **685 passed, 1 skipped, 0 failed**. The one skip is the existing PostgreSQL advisory-lock test; the isolated regression run used SQLite and did not connect to the live database.
- Final persisted full DQ run `aafbd7c6e6284b379779f62ddbe81a86`: **127 PASS, 7 WARNING, 0 FAIL**. Warning gates: generic source-page actionability (712), open-review backlog (12), historical review audit completeness (120), stale source freshness (3), sync-runtime anomalies (6), source-absence classification (15 fully classified), and unknown area stored as zero (17). No DQ rule was weakened.
- API health/readiness: **200/200**. PostgreSQL and Redis were healthy; API readiness saw the worker heartbeat; Celery worker inspection returned `pong`; scheduler/Beat container was running; no active NCP job remained.
- Live source filters returned **NCP 26**, **RCU 6**, **RCJY 3** Masters. RCU Al-Madinah Region → Al Ula Governorate filters returned **6**. RCU remains 6 SourceOpportunity rows / 6 Masters; RCJY remains 3 / 3.
- Configured sources remained **13**. Manual NCP syncs: **1** (job 757). Other manual source syncs: **0**. No Furas, RCU, or RCJY manual sync occurred in this task.

## Final counts

- NCP SourceOpportunity rows: **185** (45 original + 140 portal rows); linked rows **27** (2 original + 25 new); distinct linked NCP Masters **26**.
- NCP portal observations: **159**; exact UUID matches **0**; deterministic same-project enrichments **19**.
- New Masters: **25**; existing Masters newly linked: **0**; duplicate Masters created: **0**; duplicate identity actions prevented: **19**.
- NCP rows removed: **0**; broken NCP links: **0**; original NCP IDs and links preserved: **45/45**.
- Whole database: **13 configured sources**, **9,439 SourceOpportunity rows**, **6,678 Master rows** (6,657 current, 21 merged).

Ta’adeen and Tourism were not started. Work stopped after NCP integration and validation.

## Artifacts

- [NCP comparison dry run](NCP-INVESTORS-PORTAL-COMPARISON-DRY-RUN-20261103.json)
- [NCP integration manifest](NCP-INVESTORS-PORTAL-INTEGRATION-MANIFEST-20261103.json)
- [NCP promotion utility](../../../../../scripts/promote_ncp_unique_masters.py)
