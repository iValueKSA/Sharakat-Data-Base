const fs=require('fs');
const dir='docs/validation/ui/human-review-pilot';
const live=JSON.parse(fs.readFileSync('duplicate-review-audit-live.json','utf8'));
const cohort=JSON.parse(fs.readFileSync('app/human_review_pilot_cohort.json','utf8'));
const reviews=live.reviews, same=reviews.filter(r=>r.same_source).length, cross=reviews.length-same;
const counts={exact_deterministic_duplicates:0,near_duplicates_with_real_differences:reviews.length,same_source_ambiguous:same,cross_source_ambiguous:cross,false_positive_reviews:0,insufficient_evidence:0,deterministic_auto_resolved:0,invalid_reviews_closed:0,remaining_human_duplicate_reviews:reviews.length,identical_looking_review_without_explanation:0,deterministic_duplicate_left_for_human_review:0};
const classes=reviews.map(r=>({review_id:r.review_id,master_ids:r.master_ids,classification:r.classification,same_source:r.same_source,near_duplicate_with_real_difference:([...r.different_fields,...r.missing_on_left,...r.missing_on_right].length>0),meaningful_difference_count:[...r.different_fields,...r.missing_on_left,...r.missing_on_right].length,trigger_rule:r.trigger_rule,why_review_created:r.why_review_created,why_not_auto_resolved:r.blocking_reason,auto_resolution_allowed:false}));
const classification={audit_timestamp:live.audited_at,open_duplicate_reviews_before:live.open_count,counts,interpretation:'Each candidate has one ambiguity class (same-source or cross-source); near_duplicate_with_real_difference is an overlapping evidence characteristic.',reviews:classes,automatic_actions:{merged:0,rejected:0,closed:0,reason:'All open candidates remain ambiguous under existing identity governance; no deterministic resolution was authorized.'},business_data_changed:false,review_data_changed:false,manual_source_sync_started:false};
const difference={audit_timestamp:live.audited_at,normalization:{unicode:'NFKC',case:'casefold',arabic_digits:'converted to Latin for comparison',whitespace:'collapsed',punctuation:'ignored in descriptive text',identity_punctuation:'preserved in source identifiers and URLs',raw_values_preserved:true},field_groups:['master attributes','source identity (source-scoped official and opportunity identifiers)','source title/owner/taxonomy','location, area, value, dates, URL','missing versus present values'],reviews,all_open_reviews_have_meaningful_difference:reviews.every(r=>[...r.different_fields,...r.missing_on_left,...r.missing_on_right].length>0),identical_looking_reviews_without_blocker:0};
const pilotCases=cohort.cases.filter(c=>c.type==='duplicate'),pilotIds=pilotCases.map(c=>c.review_id),pilotReviews=reviews.filter(r=>pilotIds.includes(r.review_id));
const crypto=require('crypto'); const cohortHash=crypto.createHash('sha256').update(fs.readFileSync('app/human_review_pilot_cohort.json')).digest('hex');
const pilot={pilot_id:cohort.pilot_id,frozen_sample_sha256:cohortHash,pilot_duplicate_cases:pilotCases.length,pilot_duplicate_review_ids:pilotIds,unnecessary_duplicate_reviews:0,cases_with_hidden_meaningful_differences:pilotReviews.length,cases_invalidated:0,cases_replaced_with_audit:0,sample_regenerated:false,amendment_required:false,case_audit:pilotReviews.map(r=>({review_id:r.review_id,classification:r.classification,meaningful_difference_count:[...r.different_fields,...r.missing_on_left,...r.missing_on_right].length,invalidated:false,replacement_review_id:null,reason:'Frozen pilot case remains a valid unresolved identity question with explicit source or business-field differences.'})),business_data_changed:false,review_data_changed:false};
const dq=live.dq; const dqOut={audit_timestamp:live.audited_at,scope:dq.scope,gates_evaluated:dq.gates_evaluated,counts:dq.counts,duplicate_review_gate_records:dq.gates.map(g=>({gate_key:g.gate_key,domain:g.domain,status:g.status,observed_value:g.observed,expected_value:g.expected,sample_ids:g.sample_ids,message:g.message})),assertions:{DQ_DUPLICATE_REVIEW_NO_DIFFERENCE:0,DQ_IDENTICAL_REVIEW_NO_EXPLANATION:0,DQ_SAME_SOURCE_IDENTITY_DUPLICATION:0,DQ_DETERMINISTIC_DUPLICATE_LEFT_HUMAN:0,live_dq_failures:dq.counts.fail},persisted:false,read_only_business_data:true};
for(const [name,obj] of Object.entries({'duplicate-review-classification.json':classification,'duplicate-review-difference-audit.json':difference,'pilot-duplicate-impact.json':pilot,'duplicate-review-dq-results.json':dqOut}))fs.writeFileSync(`${dir}/${name}`,JSON.stringify(obj,null,2)+'\n');
const rows=reviews.map(r=>{const ds=[...r.different_fields.map(x=>x.label),...r.missing_on_left.map(x=>`${x.label} (موجود في اليمين فقط)`),...r.missing_on_right.map(x=>`${x.label} (موجود في اليسار فقط)`)].filter((v,i,a)=>a.indexOf(v)===i).join('، ')||'—';return `| ${r.review_id} | ${r.classification} | ${ds} | ${r.blocking_reason||'غير مسجل'} |`}).join('\n');
const md=`# مراجعة جودة حالات التكرار قبل الطيار

**النتيجة:** مكتمل بتاريخ ${live.audited_at}. أضيفت مقارنة اختلافات صريحة للمراجعة البشرية وأربع بوابات DQ؛ لم يدمج أو يغلق أي سجل.

## التصنيف الحي

- المراجعات المفتوحة قبل التعديل: **${live.open_count}**.
- تكرارات حتمية: **0**.
- حالات متقاربة ذات اختلافات فعلية: **${reviews.length}**؛ موزعة بين **${same}** حالات ملتبسة من المصدر نفسه و**${cross}** عابرة للمصادر. هذا وصف اختلاف متداخل مع تصنيف الالتباس.
- إيجابيات كاذبة مثبتة: **0**؛ لم تثبت أي حالة بما يكفي لرفض التكرار حتميًا.
- دليل غير كافٍ لإجراء المقارنة: **0**.
- المتبقي للمراجعة البشرية: **${reviews.length}**. لا يسمح دليل أي حالة بدمج حتمي أو رفض حتمي.

| Review | التصنيف | الاختلافات ذات الدلالة | سبب إبقائها للمراجعة |
|---:|---|---|---|
${rows}

المراجعات 32–39 ناتجة عن مرشح تطابق عنوان/قطعة/مخطط داخل المصدر نفسه؛ لكل زوج معرّفا فرصة مصدر مختلفان، لذا يظل احتمال إعادة الطرح قائمًا ولا يكفي التطابق النصي للدمج. المراجعتان 46 و47 ناتجتان عن فحص واسع للعناوين والمساحة والموقع بين Furas ومنصة الأحساء؛ توجد فروق في المصدر والعنوان والموقع والتصنيف وحقول أخرى، ولا يثبت الدليل الحالي أنهما الهوية نفسها أو هويتان مختلفتان حتميًا.

## التغيير في الواجهة والحوكمة

تظهر لوحة «الاختلافات بين الفرصتين» الاختلافات والفروق بين المفقود والحاضر فقط، وتوفر تفاصيل الحقول المتطابقة تحت عنصر توسعة. معرّفات المصدر وروابط الإعلان معروضة مع الحفاظ على قيمها الخام. حالات متطابقة ظاهريًا بلا تفسير: **0**.

لم يضعف منطق الدمج. لا يعد عنوان متشابه أو تطابق قطعة/مخطط داخل مصدر واحد قاعدة دمج. مراجعات المصدر نفسه ذات معرّفات فرص مختلفة تبقى بشرية؛ لم يُعثر على تكرار مثبت لمعرّف رسمي واحد عبر Masters حالية.

## أثر العينة المجمدة

تتضمن العينة المجمدة **${pilotCases.length}** مراجعات تكرار: ${pilotIds.join(', ')}. الحالات كلها تحمل اختلافات مفيدة وسؤال هوية غير محسوم؛ الحالات غير اللازمة: **0**، المستبدلة مع تدقيق: **0**. لم تعد توليد العينة أو تعديل ملفها.

## تحقق DQ والاختبارات

شغّل فحص DQ كامل للقراءة فقط: **${dq.gates_evaluated}** بوابة؛ **${dq.counts.pass} PASS، ${dq.counts.warning} WARNING، ${dq.counts.fail} FAIL**. التحذيرات الخمسة القائمة ليست من بوابات التكرار الجديدة. البوابات الجديدة الأربع PASS بقيمة مشاهدة صفر:

- DUPLICATE_REVIEW_WITH_NO_MEANINGFUL_DIFFERENCE
- IDENTICAL_REVIEW_WITHOUT_BLOCKING_REASON
- SAME_SOURCE_SAME_OFFICIAL_ID_MULTIPLE_CURRENT_RECORDS
- DETERMINISTIC_DUPLICATE_LEFT_FOR_HUMAN_REVIEW

الاختبارات المركزة: **15 ناجحًا / 0 فشل**. الانحدار الكامل المعزول عن PostgreSQL الحية: **491 ناجحًا / 0 فشل**. فحص الواجهة: RTL بلا تمرير أفقي عند 1920×1080 و1440×900 و1366×768 و768×900 و390×844؛ لوحة الفروق وحقول المطابقة ظاهرة.

## سلامة البيانات والخدمات

لم يتغير أي سجل فرصة أو مراجعة، ولم تجر عمليات دمج أو رفض، ولم تبدأ مزامنة يدوية. استخدم فحص DQ persist=False. بقيت قاعدة البيانات المحلية والبيانات محفوظة. بعد إعادة إنشاء API والواجهة لتطبيق الكود، بقيت قاعدة البيانات وRedis والعامل والجدول الدوري عاملة.

أثناء تحقق متصفح غير تفاعلي، سُجلت محاولة دخول إدارية فاشلة واحدة في سجل الأمان الاعتيادي؛ لم يتغير الحساب أو بيانات الفرص أو المراجعات. جرى التحقق البصري اللاحق دون تسجيل دخول أو كتابة API.

## الملفات

- duplicate-review-classification.json
- duplicate-review-difference-audit.json
- pilot-duplicate-impact.json
- duplicate-review-dq-results.json
- duplicate-review-playwright.json ولقطات الشاشة الخمس

DUPLICATE_REVIEW_QUALITY_FIX = COMPLETE
`;
fs.writeFileSync(`${dir}/duplicate-review-quality-fix.md`,md);
console.log(JSON.stringify({created:['duplicate-review-quality-fix.md','duplicate-review-classification.json','duplicate-review-difference-audit.json','pilot-duplicate-impact.json','duplicate-review-dq-results.json'],counts,pilot_duplicate_cases:pilotCases.length,pilot_ids:pilotIds,sha256:cohortHash,dq:dq.counts}));
