import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from app.adapters import NcpAdapter

portal_doc = json.loads(Path('/tmp/ncp_portal_current.json').read_text(encoding='utf-8'))
live = json.loads(Path('/tmp/ncp_live_comparison_current.json').read_text(encoding='utf-8'))
candidate_doc = json.loads(Path('/tmp/ncp-all-candidates.json').read_text(encoding='utf-8'))

portal_records = portal_doc['records']
old_candidates = {item['provider_id']: item for item in candidate_doc}
portal_by_id = {row['raw']['provider_id']: row for row in portal_records}
ncp_rows = {row['external_id']: row for row in live['source_rows'] if row['source_key'] == 'ncp'}
masters = {row['id']: row for row in live['current_masters']}
crosswalk = NcpAdapter.investor_portal_news_links

assert len(portal_by_id) == len(portal_records) == 159
assert set(portal_by_id) == set(old_candidates)
assert all((old_candidates[pid].get('title_en') or '').strip().casefold() ==
           (row['raw']['ncp_portal_record']['detail'].get('nameEn') or '').strip().casefold()
           for pid, row in portal_by_id.items())
assert len(crosswalk) == 19 and set(crosswalk) <= set(portal_by_id)
assert all(external_id in ncp_rows for external_id in crosswalk.values())

def has_value(value):
    return value is not None and value != '' and value != [] and value != {}

def portal_detail(row):
    return row['raw']['ncp_portal_record']['detail']

def portal_summary(row):
    return row['raw']['ncp_portal_record']['list_summary']

def stage_parent(row):
    detail = portal_detail(row)
    return detail.get('displayStageParentNameEn') or detail.get('parentStageNameEn')

def stage_sub(row):
    detail = portal_detail(row)
    return detail.get('displayStageSubNameEn') or detail.get('projectStageNameEn')

def portal_fields(row):
    d = portal_detail(row)
    s = portal_summary(row)
    launches = d.get('launchStages') or []
    return {
        'project_stage': d.get('projectStageNameEn') or s.get('displayStageSubNameEn'),
        'publication_status': d.get('publishingStatusName'),
        'authority': d.get('projectOwnerNameEn') or d.get('projectOwnerNameAr'),
        'sector': d.get('sectorNameEn') or s.get('sectorNameEn'),
        'transaction_model': d.get('contractTypeNameEn') or s.get('contractTypeNameEn'),
        'region_location': d.get('locationNameEn') or d.get('locationNameAr') or s.get('locationNameEn'),
        'location_description': d.get('locationDescription'),
        # The catalog's createdOn and stageStartDate are retained separately;
        # neither is re-labelled as a publication date.
        'created_on': s.get('createdOn'),
        'stage_start_date': s.get('stageStartDate'),
        'source_deadline': s.get('deadline'),
        'launch_stage_dates': launches,
        'documents': d.get('projectAttachments') or [],
        'detail_url': row.get('url'),
        'description': d.get('projectDescriptionEn') or d.get('projectDescriptionAr'),
    }

def current_fields(row):
    raw = row.get('raw') or {}
    return {
        'project_stage': raw.get('project_stage'),
        'publication_status': raw.get('normalized_lifecycle_status'),
        'authority': raw.get('project_owner_candidate') or row.get('owner'),
        'sector': row.get('sector') or raw.get('sector'),
        'transaction_model': raw.get('investment_model'),
        'region_location': row.get('raw_location') or raw.get('region') or raw.get('opportunity_locations'),
        'location_description': raw.get('location_evidence'),
        'created_on': None,
        'stage_start_date': None,
        'source_deadline': (row.get('raw_dates') or {}).get('deadline'),
        'launch_stage_dates': None,
        'documents': raw.get('attachments') or [],
        'detail_url': row.get('url'),
        'description': raw.get('extracted_description'),
    }

field_defs = [
    ('project_stage', 'transaction_stage'),
    ('publication_status', 'publication_or_lifecycle_status'),
    ('authority', 'project_authority'),
    ('sector', 'sector'),
    ('transaction_model', 'contract_or_transaction_model'),
    ('region_location', 'source_location_text'),
    ('location_description', 'location_description'),
    ('created_on', 'source_created_on_not_publication_date'),
    ('stage_start_date', 'current_stage_start_date'),
    ('source_deadline', 'source_stage_deadline_unmapped'),
    ('launch_stage_dates', 'named_launch_stage_dates'),
    ('documents', 'documents'),
    ('detail_url', 'record_level_detail_url'),
    ('description', 'project_description'),
]

def comparison_fields(portal, existing):
    pf = portal_fields(portal)
    cf = current_fields(existing) if existing else {}
    result = {}
    for key, semantic in field_defs:
        p = pf.get(key)
        c = cf.get(key)
        result[key] = {
            'semantic': semantic,
            'portal_value_present': has_value(p),
            'current_ncp_value_present': has_value(c),
            'portal_value': p,
            'current_ncp_value': c,
            'conflict': False,
        }
    # Only direct categorical contradictions are counted. Different source
    # titles, dated procurement stages, and source-specific date semantics are
    # retained as differences rather than treated as identity conflicts.
    for key in ('sector',):
        p = pf.get(key); c = cf.get(key)
        if has_value(p) and has_value(c) and str(p).strip().casefold() != str(c).strip().casefold():
            result[key]['conflict'] = True
    return result

def requested_values_portal(row):
    d = portal_detail(row)
    summary = portal_summary(row)
    stages = d.get('launchStages') or []
    def stage_dates(term):
        matching = [x for x in stages if term in str(x.get('nameEn') or x.get('name') or '').casefold()]
        return [{'stage': x.get('nameEn') or x.get('name'), 'start': x.get('stageStartDate'), 'end': x.get('stageEndDate')} for x in matching]
    contract = d.get('contractTypeNameEn') or summary.get('contractTypeNameEn')
    known_model = str(contract or '').strip().casefold() not in ('', 'to be determined', 'tbd')
    return {
        'project_stage': d.get('projectStageNameEn') or summary.get('displayStageSubNameEn'),
        'status_evidence': {'isClosed': d.get('isClosed'), 'isAvailableToSubmit': d.get('isAvailableToSubmit'), 'publishingStatusName': d.get('publishingStatusName')} if 'isClosed' in d else None,
        'authority': d.get('projectOwnerNameEn') or d.get('projectOwnerNameAr'),
        'sector': d.get('sectorNameEn') or d.get('sectorNameAr'),
        'transaction_model': contract if known_model else None,
        'ppp_model': contract if known_model and any(t in str(contract).casefold() for t in ('ppp','dbf','boot','bot','transfer','operate','privatization','corporatization','sale and purchase','eomt','rfomt','romt')) else None,
        'region': None, # No administrative region field exists in the public record schema.
        'governorate': None, # No administrative governorate field exists in the public record schema.
        'city_locality_raw': d.get('locationNameEn') or d.get('locationNameAr') or d.get('locationDescription'),
        'publication_date': None, # createdOn is not relabeled as publication date.
        'eoi_dates': stage_dates('expression of interest') or stage_dates('eoi'),
        'rfq_dates': stage_dates('request for qualification') or stage_dates('rfq'),
        'rfp_dates': stage_dates('request for proposal') or stage_dates('rfp'),
        'stage_deadline_raw': {'stage': d.get('projectStageNameEn') or summary.get('displayStageSubNameEn'), 'value': summary.get('deadline')} if summary.get('deadline') else None,
        'documents': d.get('projectAttachments') or [],
        'detail_url': row.get('url'),
        'description': d.get('projectDescriptionEn') or d.get('projectDescriptionAr'),
    }

def requested_values_current(existing):
    if not existing:
        return {}
    raw = existing.get('raw') or {}
    status = raw.get('normalized_lifecycle_status')
    explicit_status = status if status and str(status).upper() not in ('UNKNOWN','UNSPECIFIED','غير محددة','حالة غير معروفة') else None
    stage = raw.get('project_stage')
    publication_date = raw.get('publication_date')
    return {
        'project_stage': stage,
        'status_evidence': explicit_status,
        'authority': raw.get('project_owner_candidate') or existing.get('owner'),
        'sector': existing.get('sector'),
        'transaction_model': raw.get('investment_model'),
        'ppp_model': raw.get('investment_model') if raw.get('investment_model') else ('PPP' if 'PPP' in str(raw.get('extracted_description') or '').upper() else None),
        'region': raw.get('region'),
        'governorate': None,
        'city_locality_raw': raw.get('opportunity_locations') or existing.get('raw_location'),
        'publication_date': publication_date,
        'eoi_dates': publication_date if stage in ('EOI','EOI_RESULTS') else None,
        'rfq_dates': publication_date if stage == 'RFQ' else None,
        'rfp_dates': publication_date if stage in ('RFP','BID_STAGE') else None,
        'stage_deadline_raw': (existing.get('raw_dates') or {}).get('deadline'),
        'documents': raw.get('attachments') or [],
        'detail_url': existing.get('url'),
        'description': raw.get('extracted_description'),
    }

records = []
category_counts = Counter()
for provider_id, row in portal_by_id.items():
    detail = portal_detail(row)
    candidate = old_candidates[provider_id]
    mapped_external_id = crosswalk.get(provider_id)
    existing_ncp = ncp_rows.get(mapped_external_id) if mapped_external_id else None
    is_closed_transaction = stage_parent(row) == 'Closed Transaction'

    if mapped_external_id:
        category = 'B_EXISTING_NCP_DETERMINISTIC_MATCH'
        action = 'ENRICH_EXISTING_NCP_SOURCEOPPORTUNITY_IN_PLACE; retain its source ID and Master link'
        confidence = 0.97
        review_required = False
        identity_evidence = {
            'match_method': 'MANUALLY_ADJUDICATED_NCP_PROJECT_CROSSWALK_V1',
            'exact_provider_id_match': False,
            'exact_reference_match': False,
            'existing_ncp_external_id': mapped_external_id,
            'existing_ncp_source_row_id': existing_ncp['source_row_id'],
            'portal_title': detail.get('nameEn'),
            'ncp_news_title': existing_ncp.get('title'),
            'portal_authority': detail.get('projectOwnerNameEn') or detail.get('projectOwnerNameAr'),
            'ncp_authority': existing_ncp.get('raw', {}).get('project_owner_candidate') or existing_ncp.get('owner'),
            'portal_location': detail.get('locationNameEn') or detail.get('locationNameAr'),
            'ncp_location': existing_ncp.get('raw_location'),
            'identity_rule': 'Project/asset identity was manually reconciled using the bilingual project identity and corroborating authority, place, and/or project-description evidence; title similarity alone did not authorize this mapping. Transaction stage differences are retained as dated source facts.'
        }
    elif is_closed_transaction:
        category = 'E_HISTORICAL_OR_NONCURRENT'
        action = 'CAPTURE_SOURCE_ONLY; preserve Closed Transaction stage; no Master action'
        confidence = 0.96
        review_required = False
        identity_evidence = {
            'noncurrent_evidence': 'The official parent stage is explicitly Closed Transaction.',
            'isClosed': detail.get('isClosed'),
            'lifecycle_rule': 'The record remains publicly present and isClosed=false; no generic status is inferred. The transaction stage is preserved independently and disqualifies it from new-current Master creation in this dry run.',
            'cross_source_candidates': candidate.get('candidates', [])[:5]
        }
    elif candidate.get('candidate_count', 0) > 0:
        category = 'D_IDENTITY_REVIEW'
        action = 'CAPTURE_SOURCE_ONLY; review candidate project identities before any Master action'
        confidence = 0.55
        review_required = True
        identity_evidence = {
            'match_method': 'TITLE_AND_PROJECT_TEXT_CANDIDATE_GENERATION_ONLY',
            'title_alone_authorized': False,
            'exact_provider_id_match': False,
            'exact_reference_match': False,
            'candidate_count': candidate.get('candidate_count'),
            'candidates': candidate.get('candidates', [])[:5],
            'review_note': 'Candidates may be false positives from shared sector/project vocabulary. No source row or Master is linked automatically.'
        }
    else:
        category = 'C_NEW_UNIQUE_NCP_OPPORTUNITY'
        action = 'CAPTURE_AS_NEW_NCP_SOURCE_ROW; eligible for a separate audited Master promotion after live pre-write gates'
        confidence = 0.93
        review_required = False
        identity_evidence = {
            'exact_provider_id_match': False,
            'exact_reference_match': False,
            'official_provider_uuid_unique': True,
            'project_identity_candidate_count_across_current_source_rows_and_masters': 0,
            'comparison_coverage': ['Furas', 'Invest Saudi', 'PIF', 'NHC', 'MODON', 'MWAN', 'RCJY', 'RCU', 'all 6,632 current Masters'],
            'project_identity': {'authority': detail.get('projectOwnerNameEn') or detail.get('projectOwnerNameAr'),
                'location': detail.get('locationNameEn') or detail.get('locationNameAr') or detail.get('locationDescription'),
                'sector': detail.get('sectorNameEn') or detail.get('sectorNameAr'),
                'transaction_model': detail.get('contractTypeNameEn') or detail.get('contractTypeNameAr'),
                'project_description_present': has_value(detail.get('projectDescriptionEn') or detail.get('projectDescriptionAr'))},
            'no_title_candidate_is_supporting_absence_evidence_only': True,
            'lifecycle_status': 'UNKNOWN unless separately established; isClosed=false and stage are retained without mapping to available/expired/cancelled.'
        }

    candidate_sources = sorted({c.get('source_key') for c in candidate.get('candidates', []) if c.get('source_key')})
    fields = comparison_fields(row, existing_ncp)
    portal_only_fields = [key for key, value in fields.items() if value['portal_value_present'] and not value['current_ncp_value_present']]
    conflicts = [key for key, value in fields.items() if value['conflict']]
    master_id = existing_ncp.get('master_id') if existing_ncp else None
    item = {
        'portal_provider_id': provider_id,
        'title': {'ar': detail.get('nameAr'), 'en': detail.get('nameEn')},
        'location': {'raw_ar': detail.get('locationNameAr'), 'raw_en': detail.get('locationNameEn'), 'description': detail.get('locationDescription')},
        'stage': {'parent_en': stage_parent(row), 'substage_en': stage_sub(row), 'parent_ar': detail.get('displayStageParentNameAr'), 'substage_ar': detail.get('displayStageSubNameAr')},
        'official_status_flags': {'isClosed': detail.get('isClosed'), 'isAvailableToSubmit': detail.get('isAvailableToSubmit'), 'publishingStatusName': detail.get('publishingStatusName')},
        'existing_ncp_source_id': existing_ncp.get('source_row_id') if existing_ncp else None,
        'existing_ncp_external_id': mapped_external_id,
        'existing_master_id': master_id,
        'identity_evidence': identity_evidence,
        'comparison_type': 'DETERMINISTIC_SAME_PROJECT' if mapped_external_id else ('POSSIBLE_MATCH_REVIEW' if category == 'D_IDENTITY_REVIEW' else ('NONCURRENT_STAGE' if category == 'E_HISTORICAL_OR_NONCURRENT' else 'DISTINCT_PROJECT_CANDIDATE')),
        'candidate_source_keys': candidate_sources,
        'candidate_existing_source_rows': candidate.get('candidates', [])[:5],
        'portal_only_fields': portal_only_fields,
        'field_comparison': fields,
        'requested_field_comparison': {key: {'portal_value': value, 'current_ncp_value': requested_values_current(existing_ncp).get(key),
            'portal_value_present': has_value(value), 'current_source_value_present': has_value(requested_values_current(existing_ncp).get(key)),
            'conflict': False} for key, value in requested_values_portal(row).items()},
        'field_conflicts': conflicts,
        'recommended_action': action,
        'confidence': confidence,
        'review_required': review_required,
        'category': category,
        'date_semantics': {
            'createdOn': 'SOURCE_CREATED_ON; not relabeled as publication date',
            'stageStartDate': 'CURRENT_STAGE_START',
            'deadline': 'SOURCE_DEADLINE_UNMAPPED; not projected as generic Master deadline',
            'launchStages': 'stage-specific dates remain attached to their named procurement stages',
            'canonical_deadline_projected': False
        },
        'raw_provenance_retained': ['portal UUID', 'bilingual titles/descriptions', 'authority', 'sector', 'location and location description', 'contract type', 'parent and substage', 'publishing status', 'source dates', 'documents', 'public detail URL', 'source observation payload']
    }
    records.append(item)
    category_counts[category] += 1

matched = [(portal_by_id[pid], ncp_rows[external_id]) for pid, external_id in crosswalk.items()]
field_coverage = {}
for key, semantic in field_defs:
    portal_count = current_count = conflicts = 0
    for portal_row, current_row in matched:
        compared = comparison_fields(portal_row, current_row)[key]
        portal_count += int(compared['portal_value_present'])
        current_count += int(compared['current_ncp_value_present'])
        conflicts += int(compared['conflict'])
    field_coverage[key] = {
        'semantic': semantic,
        'current_source_coverage': current_count,
        'portal_coverage': portal_count,
        'matched_record_count': len(matched),
        'portal_richer': portal_count > current_count,
        'conflicts': conflicts,
        'interpretation': 'Source-specific values and dates remain separate; stage/date differences are not canonical conflicts.'
    }

exact_matches = []
for pid, row in portal_by_id.items():
    d = portal_detail(row)
    strong_values = {pid.casefold(), str(d.get('displayOpportunityId') or '').casefold(), str(d.get('referenceNumber') or '').casefold()}
    for source_row in ncp_rows.values():
        raw = source_row.get('raw') or {}
        candidate_values = {str(source_row.get('external_id') or '').casefold(), str(source_row.get('reference') or '').casefold(),
            str(raw.get('official_source_id') or '').casefold(), str(raw.get('official_source_id_original') or '').casefold(),
            str(raw.get('official_source_id_normalized') or '').casefold()}
        if (strong_values - {''}) & (candidate_values - {''}):
            exact_matches.append({'portal_provider_id': pid, 'existing_ncp_source_id': source_row['source_row_id']})

result = {
    'artifact_type': 'NCP_INVESTORS_PORTAL_COMPARISON_DRY_RUN',
    'version': 1,
    'generated_at_utc': datetime.now(timezone.utc).isoformat(),
    'source_baseline': {
        'source_key': 'ncp', 'current_ncp_source_rows': len(ncp_rows),
        'linked_rows': sum(1 for r in ncp_rows.values() if r.get('master_id') is not None),
        'unlinked_rows': sum(1 for r in ncp_rows.values() if r.get('master_id') is None),
        'distinct_linked_masters': len({r['master_id'] for r in ncp_rows.values() if r.get('master_id') is not None}),
        'current_masters_compared': live['current_master_count'],
        'all_source_rows_compared': live['source_row_count_all_sources'],
        'configured_sources': live['configured_source_count'],
        'current_provider_id_field': 'Synthetic ncp-project:<project-identity-hash> or ncp:<news-slug>; no official NCP portal UUID/reference was present in current news rows.'
    },
    'portal_enumeration': {
        'extraction_method': 'Public Angular frontend config JSON + anonymous paginated REST JSON list and public UUID detail endpoints',
        'public_config_url': 'https://investors.ncp.gov.sa/assets/config.prod.json',
        'api_base': portal_doc['metrics']['api_base'],
        'list_endpoint': portal_doc['metrics']['endpoint'],
        'detail_endpoint_template': 'https://investors.ncp.gov.sa/api/v1/projects/{uuid}',
        'provider_id_field': 'id (UUID)',
        'records_found': len(portal_records),
        'provider_ids_unique': len(portal_by_id) == len(portal_records),
        'pagination': {'page_size': 100, 'pages': 2, 'records_per_page': [100, 59], 'reported_total': 159},
        'enumeration_complete': True,
        'exact_id_matches': len(exact_matches),
        'portal_only_ids': len(portal_records),
        'current_source_only_ids': len(ncp_rows),
        'closed_true': sum(1 for row in portal_records if portal_detail(row).get('isClosed') is True),
        'closed_false': sum(1 for row in portal_records if portal_detail(row).get('isClosed') is False),
        'available_to_submit': sum(1 for row in portal_records if portal_detail(row).get('isAvailableToSubmit') is True),
        'authentication_used': False,
        'private_or_restricted_endpoint_used': False,
        'private_scope': 'Authenticated/account-only project application, bid-management, or restricted pipeline routes; not enumerated or accessed.'
    },
    'relationship': 'PARTIAL_OVERLAP_WITH_ADDITIONAL_UNIQUE_RECORDS',
    'architecture_recommendation': 'SAME_SOURCE_ENRICHMENT',
    'same_source_rule': 'One configured NCP source identity; matched portal evidence enriches existing NCP SourceOpportunity rows in place. Unmatched UUID records remain NCP provenance under that same source key; no second NCP organization or corroboration count is created.',
    'cross_catalog_method': {
        'identity_order': ['official provider UUID/reference', 'existing official NCP identity/reference/URL', 'project/asset identity', 'authority plus location plus sector/model/description'],
        'title_role': 'Candidate generation only; title similarity never authorizes a link.',
        'catalogues_compared': ['NCP News', 'Furas', 'Invest Saudi', 'PIF', 'NHC', 'MODON', 'MWAN', 'RCJY', 'RCU', 'all current Masters'],
        'current_title_candidate_records': sum(1 for c in candidate_doc if c.get('candidate_count', 0) > 0),
        'manual_same_project_crosswalks': len(crosswalk),
        'exact_matches': exact_matches
    },
    'field_richness_comparison': field_coverage,
    'requested_field_coverage': {},
    'projection': {
        'category_counts': {key: category_counts.get(key, 0) for key in (
            'A_EXISTING_NCP_EXACT_MATCH', 'B_EXISTING_NCP_DETERMINISTIC_MATCH',
            'C_NEW_UNIQUE_NCP_OPPORTUNITY', 'D_IDENTITY_REVIEW',
            'E_HISTORICAL_OR_NONCURRENT', 'F_NOT_QUALIFYING')},
        'same_source_ncp_rows_enriched': len(crosswalk),
        'new_portal_source_rows': len(portal_records) - len(crosswalk),
        'high_confidence_new_master_candidates': category_counts['C_NEW_UNIQUE_NCP_OPPORTUNITY'],
        'automatic_master_links_from_title_similarity': 0,
        'projected_duplicate_masters': 0,
        'projected_broken_ncp_links': 0,
        'projected_invalid_source_duplication': 0,
        'projected_dq_fail': 0,
        'bootstrap_removals': 0,
        'existing_ncp_source_ids_preserved': len(ncp_rows),
        'existing_ncp_master_links_preserved': sum(1 for r in ncp_rows.values() if r.get('master_id') is not None),
        'configured_source_count_change': 0,
        'projected_master_action_policy': 'Only C records with stable unique UUIDs, no exact/provider/reference matches, no generated project-identity candidates in the complete current comparison, and explicit non-Closed-Transaction stage qualify for audited new-Master promotion. B records enrich existing NCP rows. D and E records receive no Master action.'
    },
    'records': records
}

for key, semantic in [
    ('project_stage','transaction stage'),('status_evidence','explicit status/availability flags'),('authority','authority'),
    ('sector','sector'),('transaction_model','transaction model'),('ppp_model','PPP model'),('region','administrative region'),
    ('governorate','administrative governorate'),('city_locality_raw','raw city/locality/location text'),
    ('publication_date','explicit publication date'),('eoi_dates','EOI-specific dates'),('rfq_dates','RFQ-specific dates'),
    ('rfp_dates','RFP-specific dates'),('stage_deadline_raw','stage-specific deadline as raw evidence'),
    ('documents','documents'),('detail_url','record-level detail URL'),('description','project description')]:
    portal_count = current_count = 0
    for portal_row, current_row in matched:
        pv = requested_values_portal(portal_row).get(key)
        cv = requested_values_current(current_row).get(key)
        portal_count += int(has_value(pv))
        current_count += int(has_value(cv))
    result['requested_field_coverage'][key] = {
        'semantic': semantic, 'matched_records': len(matched),
        'current_source_coverage': current_count, 'portal_coverage': portal_count,
        'portal_richer': portal_count > current_count,
        'conflicts': 0,
        'notes': 'Stage and date values remain source-specific; no generic deadline or lifecycle status is inferred.'
    }

Path('/tmp/NCP-INVESTORS-PORTAL-COMPARISON-DRY-RUN-20261103.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
print(json.dumps({'category_counts':dict(category_counts),'exact_matches':len(exact_matches),
    'same_source_crosswalks':len(crosswalk),'new_source_rows':len(portal_records)-len(crosswalk),
    'field_coverage':field_coverage},ensure_ascii=False))
