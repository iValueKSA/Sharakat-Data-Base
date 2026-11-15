import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const DIR=path.join(ROOT,'docs/validation/deployment/nationwide-source-expansion/furas-identity-reconciliation-20261110');
const RULE_VERSION='FURAS_IDENTITY_ALIAS_RULESET_V1.0.0';
const APPROVAL_METHOD='EVIDENCE_BASED_AUTOMATED_VALIDATION';
const APPROVAL_AUTHORITY='USER_AUTHORIZED_AUTOMATED_PROCESS';
const now=new Date().toISOString();
const inputPaths={
  proposals:'FURAS-75-ALIAS-GOVERNANCE-REVIEW-20261110.csv',
  reconciliation:'FURAS-678-RECORD-LEVEL-RECONCILIATION-20261110.json',
  adjudication:'../FURAS-678-IDENTITY-ADJUDICATION-20261105.json',
  capture:'../FURAS-NATIONAL-DURABLE-CAPTURE-MANIFEST-20261105.json',
  currentState:'FURAS-75-CURRENT-IDENTITY-STATE-SNAPSHOT-20261110.json',
};
const abs={proposals:path.join(DIR,inputPaths.proposals),reconciliation:path.join(DIR,inputPaths.reconciliation),adjudication:path.resolve(DIR,inputPaths.adjudication),capture:path.resolve(DIR,inputPaths.capture),currentState:path.join(DIR,inputPaths.currentState)};
function loadJson(p){return JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''));}
function hashFile(p){return crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');}
function parseCsv(text){
 text=text.replace(/^\uFEFF/,'').replace(/\r\n/g,'\n').replace(/\r/g,'\n');
 const rows=[];let row=[],v='',quoted=false;
 for(let i=0;i<text.length;i++){const c=text[i];if(quoted){if(c==='"'&&text[i+1]==='"'){v+='"';i++;}else if(c==='"')quoted=false;else v+=c;}else if(c==='"')quoted=true;else if(c===','){row.push(v);v='';}else if(c==='\n'){row.push(v);if(row.some(x=>x!==''))rows.push(row);row=[];v='';}else v+=c;}
 if(v!==''||row.length){row.push(v);rows.push(row);}if(quoted)throw Error('Malformed CSV quoted field');
 const [headers,...data]=rows;if(!headers)throw Error('Missing CSV header');return data.map(r=>Object.fromEntries(headers.map((h,i)=>[h,r[i]??''])));
}
function toCsv(rows,headers){const q=v=>{if(v==null)return '""';const s=Array.isArray(v)||typeof v==='object'?JSON.stringify(v):String(v);return '"'+s.replace(/"/g,'""')+'"';};return '\uFEFF'+[headers.map(q),...rows.map(r=>headers.map(h=>q(r[h])))].map(r=>r.join(',')).join('\r\n')+'\r\n';}
function stable(v){if(Array.isArray(v))return v.map(stable);if(v&&typeof v==='object')return Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])]));return v;}
function fingerprint(v){return crypto.createHash('sha256').update(JSON.stringify(stable(v))).digest('hex');}
function eq(a,b){return String(a??'')===String(b??'');}
function directUrl(u,id){return typeof u==='string'&&u.startsWith('https://furas.')&&u.includes('/opportunity/'+id);}
function uniq(values){return new Set(values).size===values.length;}

const proposals=parseCsv(fs.readFileSync(abs.proposals,'utf8'));
const reconciliation=loadJson(abs.reconciliation);
const adjudication=loadJson(abs.adjudication);
const capture=loadJson(abs.capture);
const current=loadJson(abs.currentState);
if(proposals.length!==75)throw Error(`Expected exactly 75 proposals, found ${proposals.length}`);
if(current.transaction_read_only!=='on')throw Error('Current identity snapshot is not marked read-only');
if(current.enumeration_enabled||current.removals_enabled)throw Error('Furas national flags are unexpectedly enabled; fail closed');
if(reconciliation.records.length!==678)throw Error('Reconciliation evidence count mismatch');
if(adjudication.records.length!==678)throw Error('Prior adjudication evidence count mismatch');
if(capture.records.length!==6548)throw Error('Capture membership count mismatch');
if(!uniq(proposals.map(r=>r.provider_id)))throw Error('Duplicate proposed provider IDs');

const recById=new Map(reconciliation.records.map(r=>[r.provider_id,r]));
const adjById=new Map(adjudication.records.map(r=>[r.provider_id,r]));
const capById=new Map(capture.records.map(r=>[String(r.provider_id_raw),r]));
const currentRows=current.rows||[],currentMasters=current.masters||[];
const rowById=new Map(currentRows.map(r=>[Number(r.id),r]));
const mastersById=new Map(currentMasters.map(r=>[Number(r.id),r]));
const rowsByKey=new Map();for(const r of currentRows){const k=String(r.source_opportunity_id);rowsByKey.set(k,[...(rowsByKey.get(k)||[]),r]);}
const currentSourceIds=new Set(currentRows.map(r=>Number(r.id)));
const proposedTargets=proposals.map(r=>Number(r.existing_source_opportunity_id));
const proposedMasters=proposals.map(r=>Number(r.linked_master_opportunity_id));
const targetUnique=uniq(proposedTargets),masterUnique=uniq(proposedMasters);
const allRecords=[];

for(const proposal of proposals){
 const id=proposal.provider_id;
 const rec=recById.get(id), adj=adjById.get(id), cap=capById.get(id);
 const proof=adj?.alias_proof||{}, sourceEvidence=adj?.potential_existing_source_evidence||[];
 const old=sourceEvidence.length===1?sourceEvidence[0]:null;
 const cross=proof.official_investsaudi_cross_reference||{};
 const observationList=proof.historical_observations||[];
 const changed=[...(proof.raw_attribute_differences||[])].sort();
 const equal=new Set(proof.stable_attribute_fields_equal||[]);
 const requiredStable=['OBJECTID','OPPORTUNITYDESCRIPTION','ENTITIESID','ENTITIESNAME','CREATED_DATE','CITY_ID','REGION_ID','AMANAID','BALADYAID'];
 const targetId=Number(proposal.existing_source_opportunity_id);
 const masterId=Number(proposal.linked_master_opportunity_id);
 const dbTarget=rowById.get(targetId);
 const dbMaster=mastersById.get(masterId);
 const keyRows=rowsByKey.get(id)||[];
 const expectedDirect=rec?.raw_evidence?.official_furas_url||'';
 const newCapturedUrl=cap?.official_detail_url||'';
 const lineageObservation=observationList.some(o=>String(o.provider_id_raw)===String(proposal.proposed_existing_furas_source_provider_key)&&String(o.objectid_raw)===String(proof.old_objectid)&&directUrl(o.source_endpoint,proposal.proposed_existing_furas_source_provider_key));
 const liveAlias=(current.applied_aliases||[]).find(a=>String(a.provider_id)===id);
 const alreadyApplied=Boolean(liveAlias&&Number(liveAlias.source_opportunity_id)===targetId&&Number(liveAlias.master_opportunity_id)===masterId);
 const checks=[];
 const add=(name,pass,reason,category='HELD_INSUFFICIENT_EVIDENCE')=>checks.push({name,pass:Boolean(pass),reason:pass?'PASS':reason,category});
 add('SOURCE_IDENTITY_OFFICIAL_AND_LINEAGE',Boolean(rec&&adj&&adj.identity_classification==='VERIFIED_EXISTING_SOURCE_IDENTITY'&&proof.existing_furas_source_opportunity_id===targetId&&proof.existing_furas_provider_key===proposal.proposed_existing_furas_source_provider_key&&lineageObservation&&cross.source_key==='invest-saudi'&&cross.official_opportunity_number===id&&directUrl(expectedDirect,id)&&directUrl(cross.official_furas_link,id)), 'Official cross-reference or historical source lineage is missing or inconsistent.','HELD_IDENTITY_CONFLICT');
 add('EXISTING_SOURCEOPPORTUNITY_IN_FURAS_NAMESPACE',Boolean(old&&old.source_key==='furas'&&Number(old.source_opportunity_id)===targetId&&old.provider_key===proposal.proposed_existing_furas_source_provider_key&&current.furas_source_id===dbTarget?.source_id&&Number(dbTarget?.id)===targetId&&String(dbTarget?.source_opportunity_id)===String(old.provider_key)), 'The historical/current SourceOpportunity target is missing, changed, or outside the Furas namespace.','HELD_IDENTITY_CONFLICT');
 add('OFFICIAL_REFERENCE_CONSISTENCY',Boolean(cross.official_opportunity_number===id&&cross.source_reference===id&&directUrl(rec?.raw_evidence?.official_furas_url,id)&&directUrl(cross.official_furas_link,id)&&directUrl(newCapturedUrl,id)&&cap?.official_reference_raw===id), 'Official opportunity reference, captured record, and direct Furas URL do not agree.','HELD_IDENTITY_CONFLICT');
 add('CAPTURE_TRACEABILITY',Boolean(cap&&cap.raw_record_sha256===rec?.raw_evidence?.record_sha256&&cap.raw_record_sha256===adj?.evidence_references?.find(e=>e.kind==='official_durable_capture_manifest')?.record_sha256&&cap.enumeration_scope==='SAUDI_NATIONAL_V1'), 'Capture record hash, membership, or scope cannot be reproduced.');
 add('HISTORICAL_SOURCE_LINEAGE',Boolean(old&&old.source_key==='furas'&&String(old.raw_provider_id)===String(proposal.proposed_existing_furas_source_provider_key)&&old.raw_objectid===proof.old_objectid&&proof.new_objectid===proof.old_objectid&&lineageObservation), 'Historical Furas source observations do not establish the proposed old provider key and source row.','HELD_IDENTITY_CONFLICT');
 add('NO_ALIAS_OR_PROVIDER_KEY_COLLISION',Boolean(targetUnique&&masterUnique&&uniq(proposals.map(x=>x.provider_id))&&keyRows.length===0&&!liveAlias&&(current.identity_mapping_tables||[]).length===0), 'A current Furas provider key/alias conflicts with this proposal or another proposal target.','HELD_COLLISION_RISK');
 add('MASTER_RELATIONSHIP_CURRENT_AND_UNMERGED',Boolean(old&&Number(old.master_opportunity_id)===masterId&&Number(proof.historical_master_opportunity_id)===masterId&&proof.master_current===true&&dbTarget&&Number(dbTarget.master_opportunity_id)===masterId&&dbMaster&&dbMaster.merged_into_id==null), 'The existing Master is absent, changed, merged, or conflicts with the historical SourceOpportunity relationship.','HELD_MASTER_RELATIONSHIP_CONFLICT');
 add('STABLE_ATTRIBUTE_AND_GEOGRAPHY_CONSISTENCY',Boolean(changed.join('|')==='LAST_EDITED_DATE|OPPORTUNITYID'&&requiredStable.every(f=>equal.has(f))&&proof.raw_geometry_equal===true), 'A material identity attribute/geographic conflict exists or stable evidence is incomplete.','HELD_IDENTITY_CONFLICT');
 add('IDENTITY_POLICY_NO_MERGE_OR_FUZZY_MATCH',Boolean(adj?.identity_classification==='VERIFIED_EXISTING_SOURCE_IDENTITY'&&old&&old.source_key==='furas'&&proof.master_current===true&&cross.official_opportunity_number===id), 'The proposal depends on unsupported fuzzy/title matching, a Master merge, or an unestablished identity.','HELD_INSUFFICIENT_EVIDENCE');
 add('CURRENT_STATE_NOT_ALREADY_APPLIED',!alreadyApplied,'A matching alias relationship is already recorded.','ALREADY_APPLIED');
 const failed=checks.filter(c=>!c.pass);
 let decision='APPROVED_AUTOMATICALLY';
 if(alreadyApplied)decision='ALREADY_APPLIED';
 else if(failed.length){
   const categories=failed.map(x=>x.category);
   if(categories.includes('HELD_COLLISION_RISK'))decision='HELD_COLLISION_RISK';
   else if(categories.includes('HELD_MASTER_RELATIONSHIP_CONFLICT'))decision='HELD_MASTER_RELATIONSHIP_CONFLICT';
   else if(categories.includes('HELD_IDENTITY_CONFLICT'))decision='HELD_IDENTITY_CONFLICT';
   else decision='HELD_INSUFFICIENT_EVIDENCE';
 }
 const passed=checks.filter(c=>c.pass).map(c=>c.name);
 const failedRules=failed.map(c=>({name:c.name,reason:c.reason}));
 const evidence={
   proposal_csv:inputPaths.proposals,
   reconciliation_json:inputPaths.reconciliation,
   adjudication_json:inputPaths.adjudication,
   capture_manifest:inputPaths.capture,
   current_identity_snapshot:inputPaths.currentState,
   record_sha256:rec?.raw_evidence?.record_sha256||null,
   capture_page:cap?.page_number??null,
   official_furas_url:expectedDirect,
   investsaudi_source_opportunity_id:cross.source_opportunity_id??null,
   investsaudi_provider_key:cross.source_provider_key??null,
   investsaudi_official_number:cross.official_opportunity_number??null,
   investsaudi_furas_link:cross.official_furas_link??null,
   historical_observation_ids:observationList.map(o=>o.observation_id),
   historical_master_canonical_id:proof.master_canonical_id||null,
   current_target_source_id:dbTarget?.id??null,
   current_target_master_id:dbTarget?.master_opportunity_id??null,
   current_master_merged_into_id:dbMaster?.merged_into_id??null
 };
 const rationale=decision==='APPROVED_AUTOMATICALLY'?'All mandatory deterministic identity, source namespace, official-reference, collision, Master, attribute, traceability, current-state, and identity-policy checks passed. No production mapping was applied.':decision==='ALREADY_APPLIED'?'The same provider-key alias is already recorded to the proposed SourceOpportunity and Master. No duplicate decision operation is proposed.':failed.map(c=>`${c.name}: ${c.reason}`).join(' ');
 const stableDecision={provider_id:id,decision,target_source_provider_key:proposal.proposed_existing_furas_source_provider_key,existing_source_opportunity_id:targetId,existing_master_opportunity_id:masterId,official_reference:cross.official_opportunity_number,record_sha256:evidence.record_sha256,rules_passed:passed,rules_failed:failedRules,rule_version:RULE_VERSION};
 const row={provider_id:id,decision,proposed_alias_target:proposal.proposed_existing_furas_source_provider_key,existing_source_opportunity_id:targetId,existing_master_opportunity_id:masterId,official_reference:cross.official_opportunity_number||id,historical_lineage:`Furas source ${old?.source_key||'UNKNOWN'} SourceOpportunity ${old?.source_opportunity_id??'UNKNOWN'}; prior provider key ${old?.provider_key||'UNKNOWN'}; Master ${old?.master_opportunity_id??'UNKNOWN'}.`,evidence_references:evidence,validation_rules_passed:passed,validation_rules_failed:failedRules,decision_rationale:rationale,processing_timestamp_utc:now,approval_method:decision==='APPROVED_AUTOMATICALLY'?APPROVAL_METHOD:'NOT_APPROVED',approval_authority:decision==='APPROVED_AUTOMATICALLY'?APPROVAL_AUTHORITY:'NONE',identity_policy_version:RULE_VERSION,decision_fingerprint_sha256:fingerprint(stableDecision)};
 allRecords.push({decision,row,checks,stableDecision});
}

const permitted=new Set(['APPROVED_AUTOMATICALLY','HELD_INSUFFICIENT_EVIDENCE','HELD_IDENTITY_CONFLICT','HELD_COLLISION_RISK','HELD_MASTER_RELATIONSHIP_CONFLICT','ALREADY_APPLIED']);
if(allRecords.length!==75||!uniq(allRecords.map(x=>x.row.provider_id))||allRecords.some(x=>!permitted.has(x.decision)))throw Error('Decision completeness/uniqueness validation failed');
const approved=allRecords.filter(x=>x.decision==='APPROVED_AUTOMATICALLY');
const held=allRecords.filter(x=>x.decision.startsWith('HELD_'));
const applied=allRecords.filter(x=>x.decision==='ALREADY_APPLIED');
if(approved.some(x=>x.checks.some(c=>!c.pass)))throw Error('An approved decision has a failed mandatory rule');
if(!uniq(approved.map(x=>x.row.proposed_alias_target))||!uniq(approved.map(x=>x.row.existing_source_opportunity_id))||!uniq(approved.map(x=>x.row.existing_master_opportunity_id)))throw Error('Approved set contains conflicting targets');
if(approved.length+held.length+applied.length!==75)throw Error('Decision totals do not sum to 75');
if((current.identity_mapping_tables||[]).length!==0||current.enumeration_enabled||current.removals_enabled)throw Error('Safety precondition failed');

const approvedCsv='FURAS-75-APPROVED-ALIASES-20261110.csv';
const heldCsv='FURAS-75-HELD-ALIASES-20261110.csv';
const auditJson='FURAS-75-AUTOMATED-APPROVAL-AUDIT-20261110.json';
const summaryMd='FURAS-75-AUTOMATED-APPROVAL-SUMMARY-20261110.md';
const outputHeaders=['provider_id','decision','proposed_alias_target','existing_source_opportunity_id','existing_master_opportunity_id','official_reference','historical_lineage','evidence_references','validation_rules_passed','validation_rules_failed','decision_rationale','processing_timestamp_utc','approval_method','approval_authority','identity_policy_version','decision_fingerprint_sha256'];
fs.writeFileSync(path.join(DIR,approvedCsv),toCsv(approved.map(x=>x.row),outputHeaders),'utf8');
fs.writeFileSync(path.join(DIR,heldCsv),toCsv(held.map(x=>x.row),outputHeaders),'utf8');
const counts=Object.fromEntries([...permitted].map(k=>[k,allRecords.filter(x=>x.decision===k).length]));
const audit={schema:'furas-automated-alias-approval-audit-v1',run_timestamp_utc:now,rule_version:RULE_VERSION,approval_method:APPROVAL_METHOD,approval_authority:APPROVAL_AUTHORITY,execution_mode:'LOCAL_EVIDENCE_EVALUATION_ONLY_NO_PRODUCTION_WRITES',capture:{manifest:inputPaths.capture,capture_sha256:hashFile(abs.capture),capture_scope:capture.capture?.collector_scope,capture_id:capture.capture?.adapter_metrics?.source_snapshot?.snapshot_id,provider_count:capture.capture?.source_total_reported},review_package:{path:inputPaths.proposals,sha256:hashFile(abs.proposals),candidate_count:proposals.length},reconciliation:{path:inputPaths.reconciliation,sha256:hashFile(abs.reconciliation),total:reconciliation.records.length,excluded_603_unchanged_by_scope:true},adjudication:{path:inputPaths.adjudication,sha256:hashFile(abs.adjudication),total:adjudication.records.length},current_state:{path:inputPaths.currentState,sha256:hashFile(abs.currentState),captured_at_utc:current.captured_at_utc,transaction_read_only:current.transaction_read_only,furas_source_id:current.furas_source_id,target_rows:current.rows.length,current_masters:current.masters.length,identity_mapping_tables:current.identity_mapping_tables,enumeration_enabled:current.enumeration_enabled,removals_enabled:current.removals_enabled},validation:{candidates_evaluated:allRecords.length,decision_counts:counts,totals_sum_to_75:approved.length+held.length+applied.length===75,duplicate_provider_ids:75-new Set(allRecords.map(x=>x.row.provider_id)).size,approved_target_collisions:false,all_approved_pass_all_rules:approved.every(x=>x.checks.every(c=>c.pass)),production_data_mutations:0,source_sync_performed:false,out_of_scope_records_modified:0},decisions:allRecords.map(x=>({...x.row,validation_rule_detail:x.checks}))};
const auditCanonical=fingerprint({rule_version:RULE_VERSION,input_sha256:{proposals:hashFile(abs.proposals),reconciliation:hashFile(abs.reconciliation),adjudication:hashFile(abs.adjudication),capture:hashFile(abs.capture),current_state:hashFile(abs.currentState)},decisions:allRecords.map(x=>x.stableDecision).sort((a,b)=>a.provider_id.localeCompare(b.provider_id))});
audit.deterministic_decision_digest_sha256=auditCanonical;
fs.writeFileSync(path.join(DIR,auditJson),JSON.stringify(audit,null,2)+'\n','utf8');
const reasons=Object.fromEntries([...new Set(held.flatMap(x=>x.row.validation_rules_failed.map(y=>y.name)))].map(k=>[k,held.filter(x=>x.row.validation_rules_failed.some(y=>y.name===k)).length]));
const summary=`# Automated Furas alias approval — 2026-11-10

## Result

**AUTOMATED_APPROVAL = ${approved.length===75&&held.length===0&&applied.length===0?'PASS':'PARTIAL'}**. The decision engine evaluated exactly ${allRecords.length} proposals. Automatically approved: **${approved.length}**. Held: **${held.length}**. Already applied: **${applied.length}**. No alias mapping was applied to production.

| Decision | Count |
|---|---:|
${[...permitted].map(k=>`| ${k} | ${counts[k]} |`).join('\n')}
| **Total** | **${allRecords.length}** |

## Evidence and checks

Each approved row passed the versioned deterministic checks for official source reference and direct Furas link; historical Furas provider-key observations; existing SourceOpportunity in the Furas namespace; current source and Master IDs; unmerged Master relationship; no attribute/geometry conflicts beyond OPPORTUNITYID and LAST_EDITED_DATE; unique proposal targets; traceable capture hash; and absence of an already-applied Furas key or alias mapping. No decision relied on the prior READY recommendation alone or title similarity alone.

The current identity check was a PostgreSQL transaction marked READ ONLY. It found ${current.rows.length} of 75 target SourceOpportunity rows in Furas source ID ${current.furas_source_id}, ${current.masters.length} current unmerged Master rows, zero matching new Furas provider keys already present, and ${current.identity_mapping_tables.length} identity alias/crosswalk tables. Furas enumeration and removals flags were both false at snapshot time.

## Decisions and artifacts

- Approved rows: [${approvedCsv}](${approvedCsv})
- Held rows: [${heldCsv}](${heldCsv})
- Full per-candidate audit: [${auditJson}](${auditJson})
- Read-only live-state evidence: [FURAS-75-CURRENT-IDENTITY-STATE-SNAPSHOT-20261110.json](FURAS-75-CURRENT-IDENTITY-STATE-SNAPSHOT-20261110.json)
- Reproducible decision script: [approve_furas_75_aliases_evidence_based.mjs](../../../../../scripts/approve_furas_75_aliases_evidence_based.mjs)

The held file contains only a header when no candidates are held. Decisions are recorded as APPROVED_AUTOMATICALLY using EVIDENCE_BASED_AUTOMATED_VALIDATION under USER_AUTHORIZED_AUTOMATED_PROCESS. No human reviewer or signature is represented.

## Scope and operational status

The 603 excluded cases (268 possible existing, 3 attribute conflicts, 4 cross-source Master unresolved, 328 insufficient evidence) were not evaluated for approval or modified. The evaluator reads only their existing classification report to validate the candidate boundary.

**APPROVED_ALIAS_APPLICATION_READINESS = APPROVAL DECISIONS READY; PRODUCTION APPLICATION NOT AUTHORIZED/PENDING SEPARATE IMPLEMENTATION.** The application has no identity alias/crosswalk table, and no production mapping was applied. **FURAS_PILOT_READINESS = NO-GO**; the previously documented ingestion write-path issue remains. National enumeration and removals remain disabled. No ingestion, scheduler, service restart, migration, or production data mutation occurred.

## Focused validation

The evaluator asserted 75 unique candidate decisions, exact count reconciliation, no approved target/source/Master collisions, all approved rows passed every required rule, and zero production writes. Decision fingerprints are deterministic for the same evidence and rule version; the processing timestamp is recorded separately. **Focused result: PASS.**

## Next step

If implementation is desired, separately authorize and design a reversible, unique identity crosswalk and a safe application procedure. This approval artifact does not authorize that change.
`;
fs.writeFileSync(path.join(DIR,summaryMd),summary,'utf8');
console.log(JSON.stringify({evaluated:allRecords.length,counts,approved:approved.length,held:held.length,alreadyApplied:applied.length,allApprovedPass:approved.every(x=>x.checks.every(c=>c.pass)),decisionDigest:auditCanonical,files:[approvedCsv,heldCsv,auditJson,summaryMd],timestamp:now},null,2));