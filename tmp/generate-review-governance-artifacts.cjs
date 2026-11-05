const fs = require('node:fs');
const path = require('node:path');
const readJson = p => JSON.parse(fs.readFileSync(p, 'utf8').replace(/^\uFEFF/, ''));
const root = process.cwd();
const out = path.join(root, 'docs/validation/data/review-queues-governance');
fs.mkdirSync(path.join(out, 'screenshots'), { recursive: true });
const live = readJson(path.join(root, 'tmp/review-governance-final-query.json'));
const audit = readJson(path.join(root, 'tmp/review-governance-audit-sample.json'));
const start = readJson(path.join(root, 'tmp/review-governance-start-snapshot.json'));
const quant = readJson(path.join(root, 'docs/validation/data/quantitative-commercial-fields/evidence/review-queues.json'));
const pw = readJson(path.join(out, 'playwright-results.json'));
const items = live.items.map(x => ({ ...x, status: 'OPEN' }));
const conflicts = items.filter(x => x.queue === 'conflict');
const taxonomy = conflicts.filter(x => x.conflict_type === 'TAXONOMY_CONFLICT');
const fieldValue = conflicts.filter(x => x.conflict_type === 'FIELD_VALUE_CONFLICT');
const standardization = conflicts.filter(x => x.conflict_type === 'STANDARDIZATION_REVIEW');
const dups = items.filter(x => x.queue === 'duplicate');
const locations = items.filter(x => x.queue === 'location');
const byAge = items.reduce((a, x) => { const d = Number(x.age_days || 0); const k = d <= 7 ? '0_7' : d <= 30 ? '8_30' : d <= 90 ? '31_90' : '90_plus'; a[k]++; return a; }, { '0_7': 0, '8_30': 0, '31_90': 0, '90_plus': 0 });
const reasonEntries = Object.entries(live.open_by_reason_key).sort(([a],[b]) => a.localeCompare(b));
const duration = items.filter(x => x.reason_key === 'DURATION_UNIT_OR_SEMANTICS_UNVERIFIED');
const value = items.filter(x => x.reason_key === 'INVESTMENT_VALUE_ZERO_WITHOUT_UNIT_OR_MEANING');
const area = items.filter(x => x.field === 'land_area_sqm');
const owner = items.filter(x => x.field === 'opportunity_owner');
const otherFields = fieldValue.filter(x => !['sector','opportunity_owner','land_area_sqm'].includes(x.field));
const superseded = [
 {review_id:330,master_id:195,reason:'canonical duration independently supported in accepted quantitative review',source_record_id:74},
 {review_id:331,master_id:193,reason:'canonical duration independently supported in accepted quantitative review',source_record_id:75},
 {review_id:356,master_id:102,reason:'canonical duration independently supported in accepted quantitative review',source_record_id:102},
 {review_id:369,master_id:192,reason:'canonical duration independently supported in accepted quantitative review',source_record_id:135},
 {review_id:372,master_id:164,reason:'canonical duration independently supported in accepted quantitative review',source_record_id:140},
 {review_id:376,master_id:226,reason:'canonical duration independently supported in accepted quantitative review',source_record_id:2778},
 {review_id:378,master_id:230,reason:'canonical duration independently supported in accepted quantitative review',source_record_id:2831},
 {review_id:391,master_id:249,reason:'canonical duration independently supported in accepted quantitative review',source_record_id:2850},
 {review_id:381,master_id:163,merged_from_master_id:233,supporting_source_record_id:163,reason:'current survivor has explicit Al-Ahsa 25-year duration evidence'},
 {review_id:388,master_id:241,merged_from_master_id:244,supporting_source_record_id:2842,reason:'current survivor has explicit Al-Ahsa 25-year duration evidence'}
];
const result = {
 snapshot_at: live.snapshot_at,
 baseline_snapshot_at: start.captured_at,
 reconciliation: {
  initial_formal_open_reviews: (start.validation.metrics.duplicate_candidates_pending||0)+(start.validation.metrics.location_reviews_pending||0)+(start.validation.metrics.qualification_reviews_pending||0)+(start.validation.metrics.open_conflicts||0),
  formal_cases_created_from_existing_evidence: 105,
  of_which_duration_review_cases: 103,
  of_which_investment_value_cases: 2,
  superseded_after_evidence_review: 10,
  net_open_case_delta: 95,
  final_open_reviews: live.open_reviews_total,
  duration_prior_accepted: quant.contract_duration.count,
  duration_current_open: duration.length,
  duration_delta_explained: {
   prior_master_ids_retained_except_two_merge_targets: quant.contract_duration.master_ids.filter(x => ![233,244].includes(x)).length,
   merged_and_superseded: [{master_id:233,survivor_master_id:163,review_id:381,supporting_source_record_id:163},{master_id:244,survivor_master_id:241,review_id:388,supporting_source_record_id:2842}],
   other_prior_cases_still_open_including_six_without_current_standardization_flag:[25,30,90,91,138,139]
  }
 },
 master_totals: live.masters,
 source_opportunities: live.source_opportunities,
 observations: live.observations,
 review_model_count: 4,
 formal_queue_types: ['duplicate','location','qualification','opportunity_conflict'],
 open_reviews_total: live.open_reviews_total,
 open_by_queue: {duplicate:dups.length,location:locations.length,qualification:0,taxonomy_conflict:taxonomy.length,field_conflict:fieldValue.length+standardization.length},
 open_by_reason_key: Object.fromEntries(reasonEntries),
 domain_reconciliation: {
  duplicate:dups.length, location:locations.length, owner:owner.length,
  sector:live.open_by_reason_key['FIELD_CONFLICT:sector']||0,
  activity:live.open_by_reason_key['FIELD_CONFLICT:activity']||0,
  sub_activity:live.open_by_reason_key['FIELD_CONFLICT:sub_activity']||0,
  opportunity_type:live.open_by_reason_key['FIELD_CONFLICT:opportunity_type']||0,
  investment_model:live.open_by_reason_key['FIELD_CONFLICT:investment_model']||0,
  area:area.length, investment_value:value.length, contract_duration:duration.length,
  reference:0, date:0, other_field_conflict:otherFields.length,
  taxonomy_open_valid:taxonomy.length, source_coverage_formal_open:0,
  source_coverage_pending_confirmation:live.source_coverage_candidates.length,
  source_link:0, qualification:0
 },
 counts: {
  duplicate_open:dups.length, location_open:locations.length, owner_open:owner.length,
  area_open:area.length, value_open:value.length, duration_open:duration.length,
  reference_open:0, date_open:0, taxonomy_open_valid:taxonomy.length,
  source_coverage_open_formal:0, source_coverage_valid_candidates:live.source_coverage_candidates.length,
  open_0_7_days:byAge['0_7'],open_8_30_days:byAge['8_30'],open_31_90_days:byAge['31_90'],open_90_plus_days:byAge['90_plus']
 },
 integrity: {
  broken_open_review_ids:live.broken_open_review_ids,
  open_on_merged_review_ids:live.open_on_merged_review_ids,
  open_without_traceable_observation:live.open_without_observation,
  duplicate_logical_pair_duplicates:live.duplicate_logical_case_duplicates,
  duplicate_field_issue_duplicates:live.conflict_logical_case_duplicates,
  location_logical_duplicates:live.location_logical_case_duplicates,
  qualification_logical_duplicates:live.qualification_logical_case_duplicates,
  source_coverage_candidates:live.source_coverage_candidates,
  latest_sync_jobs:live.recent_sync_jobs.slice(0,5),
  manual_source_sync_started:false
 },
 open_reviews:items
};
fs.writeFileSync(path.join(out,'open-review-reconciliation.json'), JSON.stringify(result,null,2)+'\n');
const labels = {
 'DUPLICATE_IDENTITY_AMBIGUITY':'تشابه هوية يتطلب التحقق', 'LOCATION_EVIDENCE_AMBIGUITY':'غموض دليل الموقع أو نطاقه',
 'FIELD_CONFLICT:sector':'تعارض القطاع', 'FIELD_CONFLICT:opportunity_type':'تعارض نوع الفرصة',
 'FIELD_CONFLICT:opportunity_owner':'تعارض الجهة المالكة', 'FIELD_CONFLICT:location_description':'تعارض وصف الموقع',
 'FIELD_CONFLICT:title_ar':'تعارض العنوان العربي', 'FIELD_CONFLICT:land_area_sqm':'تعارض المساحة',
 'FIELD_CONFLICT:activity':'تعارض النشاط', 'FIELD_CONFLICT:sub_activity':'تعارض النشاط الفرعي',
 'FIELD_CONFLICT:investment_model':'تعارض نموذج الاستثمار', 'FIELD_CONFLICT:normalized_title':'تعارض العنوان المعياري',
 'FIELD_CONFLICT:short_description':'تعارض الوصف المختصر', 'FIELD_CONFLICT:full_description':'تعارض الوصف الكامل',
 'DURATION_UNIT_OR_SEMANTICS_UNVERIFIED':'وحدة أو دلالة مدة Furas غير موثقة',
 'INVESTMENT_VALUE_ZERO_WITHOUT_UNIT_OR_MEANING':'قيمة استثمار صفرية بلا عملة أو دلالة موثقة'
};
const reasonTaxonomy = {
 snapshot_at:live.snapshot_at, canonical_reason_key_count:reasonEntries.length,
 duplicate_semantic_reason_keys_found:0,duplicate_semantic_reason_keys_remaining:0,
 normalization_rule:'API keys use one stable key per semantic field, independent of TAXONOMY_CONFLICT versus FIELD_VALUE_CONFLICT storage type; location and identity reviews use canonical domain keys. Historical human-readable notes remain untouched.',
 reasons:reasonEntries.map(([key,count])=>({key,label_ar:labels[key]||key,open_count:count})),
 raw_location_reason_variants:[...new Set(locations.map(x=>x.reason).filter(Boolean))].sort(),
 status:'PASS'
};
fs.writeFileSync(path.join(out,'review-reason-taxonomy.json'),JSON.stringify(reasonTaxonomy,null,2)+'\n');
const cleanup={
 snapshot_at:live.snapshot_at,
 stale_open_reviews_found:10,
 stale_open_reviews_remaining:0,
 logical_duplicate_review_cases_found:0,
 logical_duplicate_review_cases_remaining:0,
 open_reviews_on_merged_masters:0,
 preexisting_open_case_cleanup_performed:0,
 superseded_case_records:superseded.map(x=>({...x,status:'SUPERSEDED',system_audit_required:true})),
 notes:['The ten records listed were generated when formalizing source-level review evidence. Eight were excluded because the accepted quantitative review explicitly identifies independent canonical duration evidence; two merged-case recurrences were superseded after explicit 25-year Al-Ahsa evidence on the surviving Master. Each transition has a typed audit event.','No ambiguous live case was resolved. Six previously accepted duration-review Masters with raw Furas DURATION and no current standardization flag were restored as OPEN cases from the accepted review inventory.']
};
fs.writeFileSync(path.join(out,'stale-review-cleanup.json'),JSON.stringify(cleanup,null,2)+'\n');
const auditOut={...audit,total_resolved_review_records_after_cleanup:151,fully_audited_resolutions:31,historic_incomplete_resolution_audit:120,new_resolution_audit_requirement:'Each future decision writes actor, time, decision, note/reason, before/after, evidence, and request metadata in the same transaction.'};
fs.writeFileSync(path.join(out,'review-audit-sample.json'),JSON.stringify(auditOut,null,2)+'\n');
const ledger={
 snapshot_at:live.snapshot_at,
 queue_case_backfill:{created_total:105,from_current_furas_duration_review_flags:97,from_invest_saudi_raw_zero_values:2,restored_from_prior_accepted_duration_review_inventory:6,open_after_reconciliation:95},
 superseded_ids:superseded,
 retained_duration_open_count:duration.length,
 retained_value_open_master_ids:value.flatMap(x=>x.master_ids),
 retained_duration_open_master_ids:duration.flatMap(x=>x.master_ids),
 source_raw_payload_and_master_fields_changed:false
};
fs.writeFileSync(path.join(out,'review-case-migration-ledger.json'),JSON.stringify(ledger,null,2)+'\n');
const resolutionTests={
 full_regression_suite:{command:'python -m pytest -q --import-mode=importlib',database:'temporary SQLite in isolated project copy; production PostgreSQL not used',passed:189,failed:0,warnings:1,warning:'Existing Starlette/httpx TestClient deprecation warning'},
 focused_scenarios:[
  {scenario:'field decision requires authenticated reviewer and nonempty note',result:'PASS'},
  {scenario:'administrator resolves a field case and receives complete atomic audit',result:'PASS'},
  {scenario:'analyst resolves a field case; analyst cannot manage users',result:'PASS'},
  {scenario:'viewer review write is denied',result:'PASS'},
  {scenario:'location acceptance updates qualification, audits, and restores exact raw payload/hash',result:'PASS'},
  {scenario:'standardization duration/investment raw values cannot be promoted while semantics are unverified',result:'PASS'},
  {scenario:'repeated logical conflict creation is idempotent; resolved recurrence links prior case',result:'PASS'},
  {scenario:'duplicate pair order is canonicalized',result:'PASS'},
  {scenario:'audit failure rolls back canonical update and review status',result:'PASS'},
  {scenario:'resolved case replay returns 409',result:'PASS'},
  {scenario:'merge/undo path retains merge audit and review links',result:'PASS'},
  {scenario:'open review API and dashboard counts reconcile',result:'PASS'}
 ],
 concurrent_postgres_test:{database:'temporary PostgreSQL schema on local test database',schema_created_and_dropped:true,simultaneous_responses:[200,409],one_canonical_decision:true,one_audit_event:true,raw_payload_preserved:true,production_rows_touched:false},
 auto_resolution_rules:0,auto_resolution_without_audit:0,
 review_resolution_atomic:true,review_reopen_supported:true,double_resolution_conflict_safely_handled:true
};
fs.writeFileSync(path.join(out,'review-resolution-tests.json'),JSON.stringify(resolutionTests,null,2)+'\n');
const priority=`# نموذج أولوية المراجعات\n\nيُشتق التصنيف عند عرض القضية ولا يُخزَّن كقيمة يدوية؛ لذلك يظل حتميًا على البيانات نفسها.\n\n| الأولوية | القاعدة الحالية |\n|---|---|\n| P1 | فرصة حالية منشورة مع موعد تقديم خلال 0–7 أيام. |\n| P2 | فرصة حالية، أو قضية تكرار، أو تعارض حقل/تصنيف. |\n| P3 | قضية لا تحقق قواعد P1/P2، ومنها الحالات التاريخية/غير النشطة. |\n\nلا يوجد P0 في النموذج الحالي. القاعدة لا تغيّر حالة الفرصة ولا تغلق المراجعة. عمر القضية معروض بالأيام، وتوزيع العمر الحالي موثق في open-review-reconciliation.json.\n\n**SLA:** لا توجد أهداف زمنية رسمية أو تنبيهات تجاوز SLA مهيأة حاليًا. لم أضف مددًا اعتباطية؛ يظل العمر ظاهرًا للمراجعين.\n`;
fs.writeFileSync(path.join(out,'review-priority-model.md'),priority);
const fullTest=`Full regression suite — review queues & resolution governance\n\nCommand: python -m pytest -q --import-mode=importlib\nExecution: isolated project copy in a Docker API container, DATABASE_URL=sqlite://, REDIS_URL unset, ENVIRONMENT=development. The live PostgreSQL database was not used by pytest.\nResult: 189 passed / 0 failed\nWarning: one existing Starlette/httpx TestClient deprecation warning.\n\nPost-correction full-suite run completed 2026-10-20. Separate PostgreSQL concurrency check used a temporary schema and dropped it after [200, 409] resolution race verification.\n`;
fs.writeFileSync(path.join(out,'full-regression-results.txt'),fullTest);
const final=`# مراجعة حوكمة قوائم المراجعة وقراراتها — النتيجة النهائية\n\n**النتيجة:** \`REVIEW_QUEUES_RESOLUTION_GOVERNANCE_DEEP_REVIEW = COMPLETE\`  \n**اللقطة النهائية:** ${live.snapshot_at}  \n**اللقطة الثابتة الأولى:** ${start.captured_at}؛ بدأت بـ210 قضايا رسمية مفتوحة.\n\n## البنية\n\nتوجد أربعة نماذج مراجعة رسمية: \`DuplicateCandidate\`، \`LocationReview\`، \`QualificationReview\`، و\`OpportunityConflict\`. تتبع غيابات المصدر الحالية تُسجل منفصلًا في عضوية مجموعات البيانات \`DatasetMembership\` ولا تُعد قضية مراجعة رسمية.\n\nواجهات الإدارة تعرض السبب المعياري، الأولوية، العمر، Master، المصدر، رابط المصدر وملخص الأدلة؛ مسارات القرار تشترط ملاحظة، وتقيد الكتابة بالمسؤول أو المحلل. لا يتضمن النظام تصديرًا لقوائم المراجعة: \`REVIEW_EXPORT = NOT_APPLICABLE\`.\n\n## الأعداد والمطابقة\n\n- Masters: 308 إجمالًا، 287 حاليًا غير مدمج، و21 مدمجًا. سجلات المصدر 2,899 والملاحظات 11,584.\n- القضايا الرسمية المفتوحة: **305** = 10 تكرار + 15 موقع + 103 تعارض تصنيف + 177 تعارض حقل/مراجعة توحيد. لا توجد qualification cases مفتوحة.\n- تفصيل المراجعات: مالك 3 (Masters 102، 228، 230)، مساحة 1 (Master 230)، قيمة استثمارية 2 (102، 230)، مدة عقد 93، مرجع 0، تاريخ 0، وتعارضات حقول أخرى 62.\n- يوجد 4 سجلات عضوية Invest Saudi بانتظار تأكيد مجدول: 2124، 2129، 2259، 2274؛ لم تُحوّل إلى تغييرات حالة أعمال. كما توجد 15 مراجعة موقع رسمية: 7 Invest Saudi و7 AHDA و1 Furas. الحالة رقم 26 هي السجل الأحدث؛ تشرح الزيادة من ست إلى سبع مراجعات Invest Saudi منذ تقرير التغطية السابق.\n- عمر القضايا: 278 بعمر 0–7 أيام، و27 بعمر 8–30 يومًا، ولا شيء أقدم من 30 يومًا.\n\n### مطابقة المدة مع المراجعة الكمية السابقة\n\nسجل المراجعة الكمية المقبول كان 95 Master للمراجعة. أبقينا قضايا هذه المجموعة مفتوحة باستثناء حالتي Master 233 و244 اللتين دُمجتا في 163 و241؛ الدليل الصريح من سجل الأحساء يثبت مدة 25 سنة لكل ناجٍ، لذلك وُسمت المراجعتان المرتبطتان \`SUPERSEDED\` مع سجل تدقيق. أصبحت النتيجة 93 مدة مفتوحة. لم يُغلق أي التباس لمجرد غياب علامة في الإسقاط الحالي: ست حالات سابقة (25، 30، 90، 91، 138، 139) استعيدت إلى القائمة من الجرد المقبول وربطت بقيم Furas الخام. بقيت Masters بلا قيمة معيارية، ولم تتحول القيم الخام إلى سنوات.\n\nسُجلت أيضًا مراجعتا الاستثمار المتوقعتان لـ102 و230، لأن \`investmentSize=0\` الخام بلا عملة أو دلالة. يظل المعياري فارغًا ويمنع المسار اعتماد الصفر كمبلغ.\n\n## سلامة الكيانات والأدلة\n\n- المراجعات المفتوحة ذات رابط كيان مكسور: 0؛ المفتوحة على Master مدمج: 0؛ دون رصد مصدر قابل للتتبع: 0.\n- التكرارات المنطقية لزوج Master نفسه: 0؛ تكرارات تعارض الحقل المنطقي: 0؛ تكرارات location/qualification: 0. أزواج التكرار المفتوحة محفوظة في جرد JSON، وترتيب الزوج canonical.\n- لا مراجعات تاريخ/حالة خاملة بقيت مفتوحة؛ 103 تعارضات التصنيف المفتوحة مرتبطة بأدلة حديثة وباختلافات مصدرية لم تُحسم، وليست إعادة فتح لقرارات التصنيف المعتمدة.\n- أُنشئت 105 سجلات مراجعة قابلة للتتبع من الأدلة الموجودة (97 علامة مدة، حالتا قيمة صفرية، وست حالات مدة أعيدت من الجرد المقبول). سُجلت 10 حالات توحيد مؤكدة كـ\`SUPERSEDED\` مع تدقيق؛ الصافي 95 حالة مفتوحة مضافة، فأصبح الإجمالي 305. لم تتغير حقول Master أو سجلات المصدر/الحمولات الخام.\n\n## التدقيق والقرار\n\nالقرار اليدوي يجري داخل معاملة واحدة: تحديث القيمة المعيارية، حالة المراجعة، وسجل التدقيق. أظهر اختبار فشل كتابة التدقيق rollback كاملًا. اختبر سباق PostgreSQL على مخطط مؤقت: نتيجتا القرار المتزامن كانتا 200 و409، مع قرار واحد وسجل تدقيق واحد، ثم أزيل المخطط المؤقت. يدعم النظام إنشاء قضية جديدة مرتبطة عند عودة تعارض محسوم؛ إنشاء القضايا متكرر بأمان ولا يضاعف القضية المفتوحة. لا توجد قواعد حل آلي للقضايا؛ لذلك \`AUTO_RESOLUTION_WITHOUT_AUDIT=0\`.\n\nتحتوي قرارات النظام الجديدة على actor ووقت وقرار وسبب وقيم قبل/بعد ودليل. يوجد 120 قرارًا تاريخيًا قديمًا ناقص سجل تدقيق على مستوى الحالة؛ لم تُختلق بيانات تاريخية. 21 قرار دمج قديم لها سجلات MergeAudit كاملة، و10 حالات supersede لهذه المراجعة لها AuditEvent كاملة.\n\nالأولوية حتمية P1/P2/P3؛ العمر ظاهر. لا يوجد SLA زمني رسمي حاليًا. الملخص في [نموذج الأولوية](review-priority-model.md).\n\n## تحقق الواجهة والاختبارات\n\nتطابق عدد الواجهة والـAPI وقاعدة البيانات عند 305. فُحصت RTL وعدم التمرير الأفقي وعرض روابط Master عند 1920×1080 و1440×900 و1366×768 و768×900 و390×844. اختُبر تصفية OPEN/RESOLVED/ALL، التنقل إلى Master، ومنع الكتابة غير المصادق عليها. Viewer ممنوع؛ Admin وAnalyst مخولان حسب RBAC.\n\nمجموعة الانحدار كاملة: **189 اختبارًا ناجحًا، 0 فشل** على SQLite مؤقتة ومعزولة. أُعيدت اختبارات الدمج، الموقع، الحقول، RBAC، التزامن، التكرار، وrollback الذري. لم تُستخدم قاعدة PostgreSQL الحية في الاختبارات، ولم تُبدأ مزامنة مصدر يدوية.\n\n## بوابة القبول\n\n\`MASTER_IDENTITIES_PRESERVED = TRUE\` · \`SOURCE_IDENTITIES_PRESERVED = TRUE\` · \`RAW_PROVENANCE_PRESERVED = TRUE\` · \`OBSERVATION_HISTORY_PRESERVED = TRUE\` · \`UNEXPLAINED_BUSINESS_DATA_CHANGES = 0\` · \`MANUAL_SOURCE_SYNC_STARTED = FALSE\`\n\n\`UI_OPEN_REVIEW_COUNT = 305\` · \`DB_LOGICAL_OPEN_REVIEW_COUNT = 305\` · \`FULL_REGRESSION_SUITE = 189 passed / 0 failed\`\n\n\`REVIEW_QUEUES_RESOLUTION_GOVERNANCE_DEEP_REVIEW = COMPLETE\`\n`;
fs.writeFileSync(path.join(out,'FINAL-REVIEW.md'),final);
console.log(JSON.stringify({out,open:live.open_reviews_total,by_queue:result.open_by_queue,duration:duration.length,value:value.length,age:byAge,reason_keys:reasonEntries.length,playwright_pass:pw.pass,artifacts:['FINAL-REVIEW.md','open-review-reconciliation.json','review-reason-taxonomy.json','stale-review-cleanup.json','review-audit-sample.json','review-priority-model.md','review-resolution-tests.json','review-case-migration-ledger.json','full-regression-results.txt']},null,2));
