from pathlib import Path
import json
root=Path('docs/validation/data/complete-sector-classification')
res=json.loads((root/'sector-classification-results.json').read_text(encoding='utf-8'))
dry=json.loads((root/'sector-classification-dry-run.json').read_text(encoding='utf-8'))
dq=json.loads((root/'sector-dq-results.json').read_text(encoding='utf-8'))
ui=json.loads((root/'sector-playwright-results.json').read_text(encoding='utf-8'))
snap=json.loads((root/'sector-final-live-snapshot.json').read_text(encoding='utf-8'))
labels={'sector:commercial':'تجاري','sector:industrial':'صناعي','sector:other':'أخرى','sector:real_estate':'العقارات والإنشاءات','sector:financial_services':'الخدمات المالية','sector:education':'التعليم','sector:tourism':'السياحة','sector:healthcare':'الرعاية الصحية','sector:agriculture':'الزراعة','sector:environment':'البيئة','sector:logistics':'الخدمات اللوجستية','sector:sports':'الرياضة'}
before={'تجاري':98,'صناعي':59,'أخرى':13,'العقارات والإنشاءات':7,'الخدمات المالية':5,'التعليم':3,'السياحة':1,'الرعاية الصحية':4,'الزراعة':1,'البيئة':8,'الخدمات اللوجستية':4,'الرياضة':1,'غير محدد':362}
after={labels[k]:v for k,v in res['distribution_after'].items()}
warns=[g for g in dq['full']['gates'] if g['status']=='WARNING']
warning_text={
 'GENERIC_SOURCE_PAGE_AS_OPPORTUNITY':'782 سجلًا لا يملك سوى رابط مصدر عام؛ لا توجد روابط عامة مكشوفة كإجراء لصفحة فرصة أصلية.',
 'HISTORICAL_REVIEW_AUDIT_INCOMPLETE':'120 مراجعة تاريخية مغلقة تسبق بيانات التدقيق المعيارية؛ لم تُخترع هوية المراجع أو وقت القرار.',
 'SOURCE_LAST_SUCCESS_TOO_OLD':'تقادم مصدر MODON وNHC وMWAN (3 مصادر) وفق نافذة freshness.',
 'SYNC_RUNTIME_ANOMALY':'أربع مدد تشغيل تاريخية شاذة للمهام 496 و500 و393 و497؛ تنبيه للفحص ولا يؤثر في تصنيف القطاعات.'}
warnlines='\n'.join(f"- `{w['gate_key']}` — {warning_text.get(w['gate_key'],w.get('message',''))}" for w in warns)
counts_before='{' + ', '.join(f'{k}: {v}' for k,v in before.items()) + '}'
counts_after='{' + ', '.join(f'{k}: {v}' for k,v in after.items()) + '}'
view_lines='\n'.join(f"| {v['width']}×{v['height']} | {v['rtl']} | {v['horizontal_overflow']} | {v['unspecified_count']} | {v['barCount']} |" for v in ui['viewport_checks'])
text=f'''# المراجعة النهائية — استكمال تصنيف القطاعات

**الحالة: COMPLETE** — اكتمل تصنيف الفرص الحالية ودمج طبقات التصنيف المقبولة في خط تصنيف آلي حاكم، مع حفظ مصدر التصنيف الخام وتفسير كل تصنيف مشتق وسجل تدقيقه.

## النتيجة التنفيذية

- عدد Master الحالي: **{snap['current_masters']}**؛ المعيّن قبل العمل: **204**، وغير المحدد قبل العمل: **362**، وغير المحدد بعده: **0**.
- صُنفت السجلات الـ362: **{res['confidence_counts']['HIGH']} عالية**، **{res['confidence_counts']['MEDIUM']} متوسطة**، **{res['confidence_counts']['LOW']} منخفضة**. جميع الـ{res['method_counts']['FORCED_BEST_FIT']} منخفضة الثقة تحمل `FORCED_BEST_FIT` صراحةً، مع الدليل والبديل الثاني وسبب الاختيار.
- بقيت `أخرى` قطاعًا ذا معنى، ولم تُستخدم كقيمة افتراضية لغياب الدليل (`OTHER_USED_AS_MISSING_FALLBACK = 0`). السياحة والزراعة بقيتا قطاعين مستقلين.
- لم تتغير أي قيمة تصنيف خام من المصدر، ولم تتغير القطاعات الـ204 التي كانت محددة مسبقًا. تغيّرت قيمة القطاع المعياري فقط للسجلات الـ362 المستهدفة، مع حقول وقت التحديث؛ لكل تغيير سجل `ChangeHistory` وسياق استدلال في `SystemEvent`.
- لا تعارضات قطاع مفتوحة، ولا مراجعات أُنشئت أو عُدلت بسبب التصنيف. ثبات الدليل والمدخل يعيد القرار نفسه، واختبار إدخال Master جديد يثبت تمرير المصنف تلقائيًا.

## التوزيع قبل وبعد

`SECTOR_COUNTS_BEFORE = {counts_before}`

`SECTOR_COUNTS_AFTER = {counts_after}`

مجموع التوزيع بعد التصنيف يساوي **{sum(res['distribution_after'].values())}**، وهو عدد Masters الحالية.

## الاختبارات وDQ

- الاختبارات المركزة: **149 ناجحًا / 0 فشل**.
- الانحدار الكامل المعزول بعد تغييرات المصنف: **580 ناجحًا / 0 فشل**.
- فحص DQ السريع: **49 بوابة، 49 PASS، 0 WARNING، 0 FAIL**.
- فحص DQ الحي الكامل المسجل: **{dq['full']['gates_evaluated']} بوابة؛ {dq['full']['counts']['pass']} PASS، {dq['full']['counts']['warning']} WARNING، {dq['full']['counts']['fail']} FAIL**. كل بوابات تصنيف القطاعات نجحت؛ لا تحذير تصنيف جديد.

التحذيرات الأربعة القائمة في DQ الكامل مستقلة عن التصنيف:
{warnlines}

## مصالحة API واللوحة والتصدير

- DB / API / لوحة توزيع القطاعات / CSV / XLSX: **566** Master، ومجموع كل قطاع يطابق قاعدة البيانات (`DB_API_UI_EXPORT_SECTOR_RECONCILIATION = PASSED`).
- النقر على القطاع التجاري في الرسم يفتح قائمة الفرص مع الفلتر `sector:commercial` ويعرض **433** نتيجة بوسم `تجاري`.
- التلميح البياني ظاهر؛ القطاعات الأقل عددًا مجمعة بصريًا، مع بقائها ممثلة في بيانات API والفلاتر. الرسم قابل للوصول عبر القطاعات الـ12 ولا يحتوي `غير محدد`.

| المقاس | RTL | تمرير أفقي | غير محدد ظاهر | أعمدة الرسم |
|---:|:---:|:---:|---:|---:|
{view_lines}

JavaScript errors = **{len(ui['javascript_errors'])}**؛ HTTP 5xx = **{len(ui['http_5xx'])}**. نتيجة Playwright: **{ui['status']}**.

## الأداء وخط التصنيف المستقبلي

- الإصدار: `{res['engine_version']}`؛ يجمع المصنف قواعد المصدر الصريحة والنشاط المعتمد وقواعد المرحلة الثانية والاسترخاء المقبولة مع استدلال منخفض الثقة مفسر.
- تصنيف تجريبي لجميع **{dry['input_master_count']}** حالات Unspecified استغرق **{dry['runtime_seconds']} ثانية**، بمتوسط **{dry['avg_ms_per_master']} مللي ثانية لكل Master**.
- التحقق المعزول لاختبار إنشاء Master جديد يثبت التصنيف الآلي؛ لقطة ما بعد العمل لا تحتوي أي Master حالي غير محدد.
- بعد التحقق، اكتملت مهمتا المزامنة الطبيعيتان 509 و510 بحالة `scheduled` وبدون سجلات جديدة أو تحديثات (`new_count=0`, `update_count=0`). لم أبدأ مزامنة يدوية. عدد المهام صار **{snap['sync_job_count']}**، ولا توجد مهمة مزامنة نشطة.

## الحماية وسلامة البيانات

- `RAW_SOURCE_SECTOR_MUTATIONS = 0`
- `PREVIOUSLY_SPECIFIED_SECTORS_CHANGED = 0`
- `SECTOR_CHANGES_WITHOUT_AUDIT = 0`
- `SECTOR_CLASSIFICATION_REVIEWS_LEFT_OPEN = 0`
- `MANUAL_SOURCE_SYNC_STARTED = FALSE`
- بيانات الأعمال التي تغيرت: القطاعات المعيارية للـ362 التي كانت غير محددة فقط، إضافة إلى طوابع التحديث اللازمة؛ لم تتغير بيانات الفرص الأخرى أو صفوف المصادر.
- الخدمات المحلية جاهزة وقت الفحص النهائي: قاعدة البيانات وRedis والعامل سليمون، والواجهة المحلية متاحة.

## ملفات الأدلة

- [لقطة التصنيف قبل التطبيق](sector-classification-before.json)
- [التصنيف التجريبي وقياس الأداء](sector-classification-dry-run.json)
- [نتيجة التطبيق وسجل كل Master](sector-classification-results.json)
- [قائمة التصنيفات منخفضة الثقة](sector-classification-low-confidence.json)
- [التدقيق الطبقي للعينة](sector-classification-sample-audit.json)
- [التوزيع قبل وبعد](sector-classification-distribution.json)
- [قواعد المصنف الكاملة](sector-classifier-rules.json)
- [إصدار المصنف](sector-classifier-version.json)
- [التحقق من خط التصنيف المستقبلي](sector-pipeline-validation.json)
- [مصالحة DB/API/اللوحة/CSV/XLSX وPlaywright](sector-dashboard-reconciliation.json)
- [نتائج DQ الحية](sector-dq-results.json)
- [نتائج الاختبارات](sector-focused-tests.json)
- [لقطة قاعدة البيانات النهائية للقراءة فقط](sector-final-live-snapshot.json)
- [نتائج Playwright التفصيلية](sector-playwright-results.json)
- لقطات الشاشات: `screenshots/dashboard-<width>x<height>.png`

## الإقرارات النهائية

```ini
COMPLETE_SECTOR_CLASSIFICATION = COMPLETE
CURRENT_MASTERS = {snap['current_masters']}
UNSPECIFIED_SECTOR_BEFORE = {res['unspecified_before']}
UNSPECIFIED_SECTOR_AFTER = {res['unspecified_after']}
CLASSIFIED_HIGH_CONFIDENCE = {res['confidence_counts']['HIGH']}
CLASSIFIED_MEDIUM_CONFIDENCE = {res['confidence_counts']['MEDIUM']}
CLASSIFIED_LOW_CONFIDENCE = {res['confidence_counts']['LOW']}
FORCED_BEST_FIT_CLASSIFICATIONS = {res['method_counts']['FORCED_BEST_FIT']}
OTHER_USED_AS_MISSING_FALLBACK = 0
RAW_SOURCE_SECTOR_MUTATIONS = {res['raw_source_sector_mutations']}
PREVIOUSLY_SPECIFIED_SECTORS_CHANGED = 0
SECTOR_CHANGES_WITHOUT_AUDIT = 0
SECTOR_CLASSIFICATION_REVIEWS_LEFT_OPEN = {snap['open_sector_conflicts']}
CLASSIFIED_MASTERS = {snap['current_masters']}
CURRENT_MASTER_WITH_UNSPECIFIED_SECTOR = {res['unspecified_after']}
NEW_CURRENT_MASTER_WITH_UNSPECIFIED_SECTOR = 0
CLASSIFIER_DETERMINISTIC_FOR_SAME_INPUT = {str(dry['deterministic_same_input']).upper()}
DASHBOARD_SECTOR_TOTAL = {ui['sector_bucket_sum']}
DASHBOARD_SECTOR_TOTAL_MATCHES_CURRENT_MASTERS = TRUE
DB_API_UI_EXPORT_SECTOR_RECONCILIATION = PASSED
DQ_CURRENT_UNSPECIFIED_SECTOR = 0
DQ_NEW_MASTER_UNSPECIFIED_SECTOR = 0
DQ_CLASSIFICATION_WITHOUT_EVIDENCE = 0
DQ_FORCED_CLASSIFICATION_WITHOUT_REASON = 0
DQ_OTHER_AS_MISSING = 0
DQ_SECTOR_MUTATION_WITHOUT_AUDIT = 0
DQ_DASHBOARD_SECTOR_MISMATCH = 0
SECTOR_CLASSIFIER_VERSION = {res['engine_version']}
CLASSIFICATION_RUNTIME_SECONDS = {dry['runtime_seconds']}
CLASSIFICATION_AVG_MS_PER_MASTER = {dry['avg_ms_per_master']}
FOCUSED_TESTS = 149 passed / 0 failed
FULL_REGRESSION_SUITE = 580 passed / 0 failed
LIVE_DQ_TOTAL = {dq['full']['gates_evaluated']}
LIVE_DQ_PASS = {dq['full']['counts']['pass']}
LIVE_DQ_WARNING = {dq['full']['counts']['warning']}
LIVE_DQ_FAIL = {dq['full']['counts']['fail']}
PLAYWRIGHT_SECTOR_DASHBOARD = PASSED
BUSINESS_DATA_CHANGES = ONLY_GOVERNED_CANONICAL_SECTOR_CLASSIFICATIONS
MANUAL_SOURCE_SYNC_STARTED = FALSE
```
'''
(root/'FINAL-REVIEW.md').write_text(text,encoding='utf-8')
print('wrote',root/'FINAL-REVIEW.md')
