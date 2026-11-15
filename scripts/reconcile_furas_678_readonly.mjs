#!/usr/bin/env node
/**
 * Reproduce a read-only, record-level classification from the retained
 * 2026-11-05 Furas capture and adjudication. This script performs no network,
 * database, Docker, or source-sync operations.
 */
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(scriptDir, '..');
const evidenceDir = path.join(root, 'docs/validation/deployment/nationwide-source-expansion');
const outputDir = path.join(evidenceDir, 'furas-identity-reconciliation-20261110');
const manifestPath = path.join(evidenceDir, 'FURAS-NATIONAL-DURABLE-CAPTURE-MANIFEST-20261105.json');
const adjudicationPath = path.join(evidenceDir, 'FURAS-678-IDENTITY-ADJUDICATION-20261105.json');
const repeatPath = path.join(evidenceDir, 'FURAS-NATIONAL-REPEAT-DRY-RUN-20261105.json');

const sha256 = (text) => crypto.createHash('sha256').update(text, 'utf8').digest('hex');
const canonical = (value) => {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  }
  return value;
};
const hashJson = (value) => sha256(JSON.stringify(canonical(value)));
const fail = (message) => { throw new Error(message); };

function validateManifest(manifest) {
  if (manifest.schema !== 'furas-national-durable-capture-v1') fail('Unexpected capture manifest schema');
  const c = manifest.capture ?? {};
  const records = manifest.records ?? [];
  const pages = manifest.pages ?? [];
  const requests = manifest.requests ?? [];
  if (c.production_writes !== false || c.read_only_official_public_source !== true || c.pagination_complete !== true) {
    fail('Capture does not attest complete read-only public collection');
  }
  if (records.length !== 6548 || c.source_total_reported !== records.length || c.unique_records !== records.length) {
    fail('Capture record count is not 6,548 or does not reconcile');
  }
  const byProvider = new Map();
  const objectIds = new Set();
  const index = [];
  for (const row of records) {
    const id = String(row.provider_id_adapter_key ?? '');
    if (!id || id !== String(row.provider_id_raw) || byProvider.has(id)) fail(`Duplicate/mismatched provider ID: ${id}`);
    if (row.objectid_raw == null || objectIds.has(String(row.objectid_raw))) fail(`Missing/duplicate OBJECTID for ${id}`);
    const raw = row.raw_payload ?? {};
    const computed = hashJson({ attributes: raw.attributes, geometry: raw.geometry ?? null });
    if (computed !== row.raw_record_sha256) fail(`Raw payload hash mismatch: ${id}`);
    byProvider.set(id, row);
    objectIds.add(String(row.objectid_raw));
    index.push({ provider_id_raw: row.provider_id_raw, objectid_raw: row.objectid_raw, raw_record_sha256: row.raw_record_sha256 });
  }
  const pageNumbers = new Set();
  const pagedProviderIds = [];
  const pagedObjectIds = [];
  for (const page of pages) {
    if (!Number.isInteger(page.page_number) || pageNumbers.has(page.page_number)) fail('Duplicate or invalid page number');
    pageNumbers.add(page.page_number);
    const ids = (page.provider_ids ?? []).map(String);
    const oids = (page.object_ids ?? []).map(String);
    if (ids.length !== page.record_count || oids.length !== ids.length) fail(`Page membership mismatch: ${page.page_number}`);
    const expectedOids = new Set(ids.map((id) => String(byProvider.get(id)?.objectid_raw ?? '')));
    if (expectedOids.has('') || expectedOids.size !== oids.length || oids.some((id) => !expectedOids.has(id))) {
      fail(`Page provider/ObjectID mismatch: ${page.page_number}`);
    }
    pagedProviderIds.push(...ids);
    pagedObjectIds.push(...oids);
  }
  if (pages.length !== 66 || pagedProviderIds.length !== records.length || new Set(pagedProviderIds).size !== records.length) {
    fail('Pages do not cover every provider record exactly once');
  }
  if (requests.length !== 70 || requests.some((r, i) => r.request_number !== i + 1 || !/^[a-f0-9]{64}$/i.test(r.response_sha256 ?? ''))) {
    fail('Request provenance is incomplete or unordered');
  }
  if (c.membership_sha256_sorted_provider_ids !== hashJson([...byProvider.keys()].sort())) fail('Provider membership hash mismatch');
  if (c.membership_sha256_sorted_objectids !== hashJson([...objectIds].sort())) fail('OBJECTID membership hash mismatch');
  if (c.ordered_capture_index_sha256 !== hashJson(index)) fail('Ordered capture-index hash mismatch');
  return { byProvider, records: records.length, pages: pages.length, requests: requests.length };
}

function classify(record, captured) {
  const providerId = String(record.provider_id);
  const captureRecord = captured.get(providerId);
  if (!captureRecord) fail(`Adjudicated ID is absent from durable capture: ${providerId}`);
  const captureHash = captureRecord.raw_record_sha256;
  const evidenceHash = (record.evidence_references ?? []).find((e) => e.kind === 'official_durable_capture_manifest')?.record_sha256;
  if (!evidenceHash || evidenceHash !== captureHash) fail(`Adjudication/capture hash mismatch: ${providerId}`);

  const candidate = (record.potential_existing_source_evidence ?? [])[0] ?? null;
  const alias = record.alias_proof ?? null;
  const cross = record.cross_source_evidence ?? null;
  const changed = (candidate?.compared_fields_changed ?? []).slice().sort();
  let classification, confidence, support, uncertainty, nextAction, sourceEligibility, masterEligibility;

  if (alias) {
    const official = alias.official_investsaudi_cross_reference ?? {};
    const oldIds = (alias.historical_observations ?? []).map((o) => String(o.provider_id_raw));
    if (record.identity_classification !== 'VERIFIED_EXISTING_SOURCE_IDENTITY' ||
        !official.official_reference_match || !official.official_furas_link_matches_provider_id ||
        alias.raw_geometry_equal !== true || alias.master_current !== true ||
        alias.approval_applied !== false || !oldIds.includes(String(alias.existing_furas_provider_key)) ||
        !['LAST_EDITED_DATE', 'OPPORTUNITYID'].every((x) => (alias.raw_attribute_differences ?? []).includes(x)) ||
        (alias.raw_attribute_differences ?? []).some((x) => !['LAST_EDITED_DATE', 'OPPORTUNITYID'].includes(x))) {
      fail(`Alias evidence gate failed for ${providerId}`);
    }
    classification = 'CONFIRMED_MATCH_EVIDENCE';
    confidence = 'HIGH — official cross-reference plus historical Furas lineage';
    support = `Exact official InvestSaudi opportunityNumber and Furas URL; same one-to-one Furas OBJECTID, geometry and stable attributes; old provider key retained in source observations; existing Master ${alias.historical_master_opportunity_id} is current.`;
    uncertainty = 'Alias/crosswalk is a proposal only; geography and canonical lifecycle remain unverified.';
    nextAction = 'Route mapping to identity governance for explicit approval; do not apply in this phase.';
    sourceEligibility = `Existing Furas SourceOpportunity ${alias.existing_furas_source_opportunity_id}; provider-key alias proposed, not applied.`;
    masterEligibility = `Existing linked Master ${alias.historical_master_opportunity_id}; no new Master.`;
  } else if (candidate && changed.length === 1 && changed[0] === 'OPPORTUNITYID') {
    classification = 'POSSIBLE_EXISTING_FURAS_IDENTITY_MANUAL_REVIEW';
    confidence = 'CANDIDATE ONLY — OBJECTID and exact title';
    support = `Same Furas OBJECTID and exact title as SourceOpportunity ${candidate.source_opportunity_id}; changed field: OPPORTUNITYID.`;
    uncertainty = 'No independent official migration/alias proof; OBJECTID reuse and identity continuity are not established.';
    nextAction = 'Seek provider migration history or authoritative cross-reference; preserve both keys and existing link meanwhile.';
    sourceEligibility = `Possible existing Furas SourceOpportunity ${candidate.source_opportunity_id}; alias not confirmed.`;
    masterEligibility = 'NOT ESTABLISHED; do not link or create a Master from this candidate alone.';
  } else if (candidate) {
    classification = 'CONFLICTING_SOURCE_ATTRIBUTES_MANUAL_REVIEW';
    confidence = 'LOW — candidate has changed identity-adjacent raw attributes';
    support = `Same OBJECTID candidate SourceOpportunity ${candidate.source_opportunity_id}; changed fields: ${changed.join(', ')}.`;
    uncertainty = 'Raw description and/or date-field changes may be a revision, reuse, or a different opportunity; date semantics are unverified.';
    nextAction = 'Compare archived official detail versions and provider history; reject no identity and apply no alias until resolved.';
    sourceEligibility = `Possible existing Furas SourceOpportunity ${candidate.source_opportunity_id}; attribute conflict unresolved.`;
    masterEligibility = 'NOT ESTABLISHED; preserve source and Master identities.';
  } else if (cross && cross.official_reference_match && cross.official_furas_link_matches_provider_id) {
    classification = 'OFFICIAL_CROSS_SOURCE_REFERENCE_MASTER_UNRESOLVED';
    confidence = 'HIGH for publication cross-reference; INSUFFICIENT for canonical Master';
    support = `InvestSaudi SourceOpportunity ${cross.source_opportunity_id} has exact official opportunity number and Furas detail URL for this provider ID.`;
    uncertainty = 'No one-to-one historical Furas SourceOpportunity or linked current Master was established.';
    nextAction = 'Review the two source records and identify/approve a canonical Master relationship separately.';
    sourceEligibility = 'No current Furas provider-key match; official cross-publication reference exists.';
    masterEligibility = 'NOT ESTABLISHED; InvestSaudi source row has no linked Master.';
  } else {
    classification = 'INSUFFICIENT_EVIDENCE_POTENTIAL_NEW_FURAS_SOURCE';
    confidence = 'INSUFFICIENT — no exact current Furas or cross-source identity candidate';
    support = 'Provider ID is absent from the current Furas exact-key set; no same-OBJECTID Furas row or exact cross-source provider token is retained.';
    uncertainty = 'Could be new to Furas, an identity change with a changed OBJECTID, or a cross-source duplicate not represented by an exact token; no broad identity proof is available.';
    nextAction = 'Keep source-only/review-required; perform governed cross-source identity and eligibility review before linking or promoting.';
    sourceEligibility = 'Potentially new Furas SourceOpportunity key only; not authorization to create or ingest.';
    masterEligibility = 'NOT ESTABLISHED; no new Master candidate is confirmed.';
  }

  const raw = captureRecord.raw_payload ?? {};
  const attrs = raw.attributes ?? {};
  const current = record.source_current_historical_evidence ?? {};
  const geo = current.raw_geography ?? {};
  const masterId = alias?.historical_master_opportunity_id ?? record.potential_existing_master_opportunity_id ?? null;
  const invest = cross ?? alias?.official_investsaudi_cross_reference ?? null;
  return {
    provider_id: providerId,
    primary_classification: classification,
    confidence,
    proposed_identity: {
      existing_furas_source_opportunity_id: alias?.existing_furas_source_opportunity_id ?? candidate?.source_opportunity_id ?? null,
      existing_furas_provider_key: alias?.existing_furas_provider_key ?? candidate?.provider_key ?? null,
      current_master_opportunity_id: masterId,
      cross_source: invest ? {
        source_key: invest.source_key,
        source_opportunity_id: invest.source_opportunity_id,
        source_provider_key: invest.source_provider_key,
        official_opportunity_number: invest.official_opportunity_number,
        official_furas_link: invest.official_furas_link,
        linked_master_id: invest.linked_master_id,
      } : null,
    },
    supporting_evidence: support,
    remaining_uncertainty: uncertainty,
    recommended_next_action: nextAction,
    source_identity_eligibility: sourceEligibility,
    master_identity_eligibility: masterEligibility,
    geographic_eligibility: 'NOT ESTABLISHED — raw provider location/coordinates retained; canonical geography not assigned in this identity adjudication.',
    lifecycle_status: `Raw Furas status=${String(attrs.OPPORTUNITYACTIVESTATUS ?? current.status_raw ?? 'unknown')}; raw date fields retained; Furas date semantics are not validated as canonical lifecycle/deadline.`,
    secondary_review_reasons: [
      ...(candidate ? ['Potential existing source identity; no applied alias.'] : []),
      ...(changed.length > 1 ? [`Changed raw attributes: ${changed.join(', ')}`] : []),
      ...(cross ? ['Exact cross-source provider reference; canonical Master unresolved.'] : []),
      ...(!alias ? ['Master identity and geographic/lifecycle eligibility are separate and unresolved.'] : []),
    ],
    raw_evidence: {
      record_sha256: captureHash,
      objectid: attrs.OBJECTID ?? captureRecord.objectid_raw,
      title_raw: attrs.OPPORTUNITYDESCRIPTION ?? current.title_raw ?? null,
      official_furas_url: `https://furas.momah.gov.sa/index.php/ar/opportunity/${providerId}?type=Investment`,
      opportunity_type_raw: attrs.OPPORTUNITYTYPE ?? null,
      activity_raw: attrs.ACTIVITYTYPE ?? null,
      subactivity_raw: attrs.SUBACTIVITYTYPE ?? null,
      status_raw: attrs.OPPORTUNITYACTIVESTATUS ?? current.status_raw ?? null,
      dates_raw: Object.fromEntries(['STARTDATE', 'ENDDATE', 'LASTRFPSELLDATE', 'ENVELOPESOPENDATE', 'LASTBIDATE', 'CREATED_DATE', 'LAST_EDITED_DATE'].map((key) => [key, attrs[key] ?? null])),
      geography_raw: {
        city: attrs.CITYNAME ?? geo.city ?? null,
        city_id: attrs.CITY_ID ?? geo.city_id ?? null,
        region: attrs.REGIONNAME ?? geo.region ?? null,
        region_id: attrs.REGION_ID ?? geo.region_id ?? null,
        amana: attrs.AMANA ?? geo.amana ?? null,
        baladya: attrs.BALADYA ?? geo.baladya ?? null,
        geometry: raw.geometry ?? null,
      },
      changed_fields_vs_candidate: changed,
    },
  };
}

function csvCell(value) {
  const text = value == null ? '' : typeof value === 'string' ? value : JSON.stringify(value);
  return `"${text.replaceAll('"', '""')}"`;
}

const [manifest, adjudication, repeat] = await Promise.all([
  fs.readFile(manifestPath, 'utf8').then(JSON.parse),
  fs.readFile(adjudicationPath, 'utf8').then(JSON.parse),
  fs.readFile(repeatPath, 'utf8').then(JSON.parse),
]);
const capture = validateManifest(manifest);
const records = adjudication.records ?? [];
if (adjudication.schema !== 'furas-678-identity-adjudication-v2' || records.length !== 678) fail('Unexpected adjudication schema/count');
if (adjudication.population?.captured_provider_ids !== capture.records || adjudication.population?.exact_existing_furas_source_key_matches !== 5870 || adjudication.population?.unmatched_provider_ids !== records.length) fail('Adjudication baseline does not reconcile');
if (repeat.set_counts?.A_intersect_B !== 5870 || repeat.set_counts?.A_minus_B !== 678 || repeat.set_counts?.A_current_capture !== capture.records) fail('Saved repeat dry-run counts do not reconcile to 5,870/678/6,548');
const ids = records.map((r) => String(r.provider_id));
if (new Set(ids).size !== ids.length) fail('Duplicate provider IDs in adjudication records');
const rows = records.map((r) => classify(r, capture.byProvider));
const classCounts = Object.fromEntries([...new Set(rows.map((r) => r.primary_classification))].sort().map((name) => [name, rows.filter((r) => r.primary_classification === name).length]));
const expected = {
  CONFIRMED_MATCH_EVIDENCE: 75,
  POSSIBLE_EXISTING_FURAS_IDENTITY_MANUAL_REVIEW: 268,
  CONFLICTING_SOURCE_ATTRIBUTES_MANUAL_REVIEW: 3,
  OFFICIAL_CROSS_SOURCE_REFERENCE_MASTER_UNRESOLVED: 4,
  INSUFFICIENT_EVIDENCE_POTENTIAL_NEW_FURAS_SOURCE: 328,
};
if (JSON.stringify(classCounts) !== JSON.stringify(Object.fromEntries(Object.entries(expected).sort()))) fail(`Primary classifications do not reconcile: ${JSON.stringify(classCounts)}`);
if (rows.length !== 678 || Object.values(classCounts).reduce((a, b) => a + b, 0) !== 678) fail('Primary category total is not 678');

const aliasRows = rows.filter((r) => r.primary_classification === 'CONFIRMED_MATCH_EVIDENCE');
const summary = {
  schema: 'furas-national-identity-reconciliation-v1',
  generated_at: '2026-11-10',
  mode: 'READ_ONLY_REPRODUCTION_FROM_SAVED_EVIDENCE; no network or database access',
  baseline: {
    capture_manifest: path.relative(root, manifestPath).replaceAll('\\', '/'),
    capture_completed_at: manifest.capture.completed_at_utc,
    capture_sha256: sha256(await fs.readFile(manifestPath, 'utf8')),
    capture_records: capture.records,
    capture_pages: capture.pages,
    capture_request_evidence_records: capture.requests,
    exact_existing_furas_source_key_matches: 5870,
    unmatched_provider_ids: 678,
    adjudication_sha256: sha256(await fs.readFile(adjudicationPath, 'utf8')),
    old_641_capture_member_set: 'excluded; not mixed with the 6,548/678 baseline',
  },
  validations: {
    capture_payload_hashes_verified: capture.records,
    capture_page_membership_verified: capture.records,
    capture_pages_verified: capture.pages,
    capture_request_hash_fields_verified: capture.requests,
    adjudication_ids_unique: true,
    every_adjudication_id_in_capture: rows.length,
    every_adjudication_hash_matches_capture: rows.length,
    duplicate_classification_memberships: 0,
    unexplained_omissions: 0,
  },
  primary_classification_counts: classCounts,
  alias_review: {
    reviewed: aliasRows.length,
    confirmed_match_evidence: aliasRows.length,
    rejected: 0,
    conflicts: 0,
    manual_identity_reviews: 0,
    proposals_applied: 0,
    separate_governance_approval_required: true,
  },
  remaining_603: {
    potentially_new_furas_sourceopportunity_keys: classCounts.INSUFFICIENT_EVIDENCE_POTENTIAL_NEW_FURAS_SOURCE,
    possible_existing_furas_source_identity: classCounts.POSSIBLE_EXISTING_FURAS_IDENTITY_MANUAL_REVIEW,
    source_attribute_conflicts: classCounts.CONFLICTING_SOURCE_ATTRIBUTES_MANUAL_REVIEW,
    exact_cross_source_references_without_master: classCounts.OFFICIAL_CROSS_SOURCE_REFERENCE_MASTER_UNRESOLVED,
    existing_or_cross_source_possible_identity_total: classCounts.POSSIBLE_EXISTING_FURAS_IDENTITY_MANUAL_REVIEW + classCounts.OFFICIAL_CROSS_SOURCE_REFERENCE_MASTER_UNRESOLVED,
    potentially_existing_opportunities_total: classCounts.POSSIBLE_EXISTING_FURAS_IDENTITY_MANUAL_REVIEW + classCounts.OFFICIAL_CROSS_SOURCE_REFERENCE_MASTER_UNRESOLVED,
    insufficient_evidence_no_candidate_total: classCounts.INSUFFICIENT_EVIDENCE_POTENTIAL_NEW_FURAS_SOURCE,
    confirmed_identity_conflicts_total: 0,
    source_attribute_conflict_reviews_total: classCounts.CONFLICTING_SOURCE_ATTRIBUTES_MANUAL_REVIEW,
    unresolved_identity_total: 603,
    remaining_manual_reviews_for_activation: 603,
  },
  activation_assessment: {
    furas_identity_reconciliation_status: 'PARTIAL — all 678 are accounted for, but 603 lack an adjudicated identity and the 75 alias proposals are unapplied.',
    pilot_readiness: 'NO-GO',
    production_mutations: 0,
    source_sync_triggered: false,
    master_identity_changes: 0,
    source_identity_changes: 0,
    source_enumeration_and_removals_remain_disabled: true,
    runtime_flag_check_20261110: {
      read_only: true,
      services_checked: ['alahsa-local-api-1', 'alahsa-local-scheduler-1'],
      furas_national_enumeration: 'UNSET; resolves false under app.geography_flags.flag_enabled default',
      furas_national_removals: 'UNSET; resolves false under app.geography_flags.flag_enabled default',
      services_restarted: 0,
    },
  },
  records: rows,
};

await fs.mkdir(outputDir, { recursive: true });
await fs.writeFile(path.join(outputDir, 'FURAS-678-RECORD-LEVEL-RECONCILIATION-20261110.json'), `${JSON.stringify(summary, null, 2)}\n`, 'utf8');
const columns = [
  'provider_id', 'primary_classification', 'confidence', 'proposed_identity', 'supporting_evidence',
  'remaining_uncertainty', 'recommended_next_action', 'source_identity_eligibility',
  'master_identity_eligibility', 'geographic_eligibility', 'lifecycle_status',
  'secondary_review_reasons', 'raw_record_sha256', 'objectid', 'title_raw', 'official_furas_url',
  'opportunity_type_raw', 'activity_raw', 'subactivity_raw', 'status_raw', 'dates_raw',
  'geography_raw', 'changed_fields_vs_candidate',
];
const csv = [columns.map(csvCell).join(','), ...rows.map((r) => columns.map((key) => {
  if (key === 'proposed_identity') return csvCell(r.proposed_identity);
  if (key === 'raw_record_sha256' || key === 'objectid' || key === 'title_raw' || key === 'official_furas_url' || key === 'opportunity_type_raw' || key === 'activity_raw' || key === 'subactivity_raw' || key === 'status_raw' || key === 'dates_raw' || key === 'geography_raw' || key === 'changed_fields_vs_candidate') return csvCell(r.raw_evidence[key]);
  return csvCell(r[key]);
}).join(','))].join('\r\n');
await fs.writeFile(path.join(outputDir, 'FURAS-678-RECORD-LEVEL-RECONCILIATION-20261110.csv'), `\uFEFF${csv}\r\n`, 'utf8');

const report = `# Furas 6,548 Capture Identity Reconciliation — 2026-11-10\n\n`+
`## Decision\n\n`+
`**FURAS_PILOT_READINESS = NO-GO.** This read-only review accounts for all 678 unmatched IDs, with 75 high-evidence existing Furas identities proposed as aliases and 603 assigned non-overlapping review classes. The 75 proposals remain unapplied.\n\n`+
`## Baseline and integrity\n\n`+
`- Captured on 2026-11-05: **6,548** unique official provider IDs; exact SourceOpportunity key matches: **5,870**; unmatched: **678**. The capture manifest has ${capture.pages} complete pages, ${capture.requests} retained request evidence entries, complete pagination, unique provider IDs/OBJECTIDs, and verified per-record raw payload hashes and page membership.\n`+
`- All 678 adjudication IDs are unique, present in the durable capture, and have a matching record SHA-256. There are no omissions or overlaps. The earlier 6,511/641 membership set was not mixed into these results.\n\n`+
`## Mutually exclusive classification of 678\n\n| Primary class | Count | Meaning |\n|---|---:|---|\n`+
`| CONFIRMED_MATCH_EVIDENCE | 75 | Official InvestSaudi reference/link plus one-to-one historical Furas lineage; existing current Master identified; alias proposal only. |\n`+
`| POSSIBLE_EXISTING_FURAS_IDENTITY_MANUAL_REVIEW | 268 | Same Furas OBJECTID and exact title, but only OPPORTUNITYID differs and there is no independent alias/migration proof. |\n`+
`| CONFLICTING_SOURCE_ATTRIBUTES_MANUAL_REVIEW | 3 | Same-OBJECTID candidates with changed raw description or date-related attributes; not accepted as aliases. |\n`+
`| OFFICIAL_CROSS_SOURCE_REFERENCE_MASTER_UNRESOLVED | 4 | Exact official InvestSaudi opportunity number and Furas URL; no linked Master or verified historical Furas source identity. |\n`+
`| INSUFFICIENT_EVIDENCE_POTENTIAL_NEW_FURAS_SOURCE | 328 | No exact current Furas key/OBJECTID candidate or exact cross-source token; a new Furas source key is possible, but Master identity is not established. |\n`+
`| **Total** | **678** | **75 + 268 + 3 + 4 + 328; no duplicate classification.** |\n\n`+
`The 603 remaining IDs reconcile as **328 potential new Furas SourceOpportunity keys + 268 possible existing Furas identities + 3 attribute-conflict reviews + 4 cross-source references without a Master = 603**. All 603 remain unresolved for activation, including the 328 potential source-only candidates. None is a confirmed new Master.\n\n`+
`## Alias evidence review\n\n`+
`The 75 alias proofs each require exact official InvestSaudi opportunityNumber and direct Furas link to the captured provider ID, one-to-one current Furas OBJECTID, equal geometry, stable raw attributes equal except OPPORTUNITYID/LAST_EDITED_DATE, historical observations retaining the prior provider key, and an existing unmerged/current Master. Results: confirmed evidence 75; rejected 0; conflicting evidence 0; identity manual review 0 within this 75-candidate set. Alias proposals applied: 0. Separate identity-governance approval remains required.\n\n`+
`The separate 271 same-OBJECTID/title candidates were not elevated to alias proof: 268 lack independent official migration evidence and 3 have conflicting source attributes. Exact title/OBJECTID is not sufficient.\n\n`+
`## Separate eligibility decisions\n\n`+
`- **Source identity:** 75 existing identities with unapplied alias proposals; 268 possible existing; 3 conflicting; 4 cross-source-only; 328 potentially new Furas keys only. No source identity was changed.\n`+
`- **Master identity:** Existing current Master evidence is present for the 75 only. The other 603 have no approved Master identity; no new Master is confirmed.\n`+
`- **Geography:** Raw provider location/geometry retained, but canonical geographic eligibility was not established in the identity adjudication.\n`+
`- **Lifecycle:** Raw status/date values retained. Furas date semantics remain unverified for canonical deadline, publication date, expiry, or cancellation.\n\n`+
`## Identity rules and live activation boundary\n\n`+
`Furas SourceOpportunity identity uses the official OPPORTUNITYID (falling back to OBJECTID only if OPPORTUNITYID is absent); the current SourceOpportunity uniqueness key is (source_id, source_opportunity_id), while MasterOpportunity is a separate entity and one Master can retain multiple source rows. Same-source fuzzy resolution is prohibited. The 75 crosswalks are proposals; no merge or link is applied. Source owner and publication platform remain separate projections. Snapshot absence is not treated as DELETED_FROM_SOURCE or CANCELLED.\n\n`+
`A read-only environment check on 2026-11-10 found both Furas flags unset in API and scheduler containers. The application flag helper defaults unset values to false, so national enumeration and national removal reconciliation resolve false. No services were restarted.\n\n`+
`## Safety and activation blockers\n\n`+
`No production row, identity, link, or Master was changed; no sync/ingestion, schedule, removal, or database operation was run. Docker was used only for read-only environment inspection of two Furas flags; no service restart or container mutation occurred. The current national capture commit path calls _safe_record with allow_master_creation=false, but that guard only prevents new Master creation when no Master is resolved; exact existing-key rows can still follow the existing-Master update path. Therefore this assessment does not establish a non-mutating production pilot boundary.\n\n`+
`Blockers: (1) 603 unresolved identities; (2) 75 provider-key aliases need governed approval and a tested reversible crosswalk; (3) 4 cross-source references lack a canonical Master; (4) 3 attribute-conflict records; (5) geography and lifecycle remain separately unresolved; (6) no reviewed proof that national ingestion can run with every production SourceOpportunity/Master mutation constrained to an approved allowlist. Furas national enumeration/removals remain disabled.\n\n`+
`## Artifacts and reproduction\n\n`+
`Run \`node scripts/reconcile_furas_678_readonly.mjs\` to revalidate the saved manifest, every raw record checksum/page membership, all 678 adjudication hashes, and regenerate the JSON/CSV below. The script has no network, database, Docker, or source-sync code.\n\n`+
`- \`FURAS-678-RECORD-LEVEL-RECONCILIATION-20261110.json\` — detailed record-level findings and evidence fields.\n`+
`- \`FURAS-678-RECORD-LEVEL-RECONCILIATION-20261110.csv\` — review queue with provider ID, proposed identity, class, support, confidence, uncertainty, next action, and raw evidence.\n\n`+
`**Next action:** identity-governance approval and a separately tested, read-only/source-only allowlisted pilot design; do not activate Furas national scheduling or removals.\n`;
await fs.writeFile(path.join(outputDir, 'FURAS-NATIONAL-IDENTITY-RECONCILIATION-20261110.md'), report, 'utf8');
console.log(JSON.stringify({ outputDir, capture, classCounts, total: rows.length, mutations: 0 }, null, 2));
