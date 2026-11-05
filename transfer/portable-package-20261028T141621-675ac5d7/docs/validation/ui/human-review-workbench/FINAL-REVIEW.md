# مساحة عمل قرار المراجعات البشرية — الإغلاق النهائي

**النتيجة:** `HUMAN_REVIEW_DECISION_WORKBENCH = COMPLETE`  
**تاريخ الإغلاق:** 2026-10-22  
**النطاق:** إكمال محدود لإعادة الفتح، والسجل الزمني الموحد، والتوصيات المفسرة وتدقيق التجاوز، والإجراءات الجماعية الحتمية، ثم استكمال أدلة القبول.

## الحالة الحية وسلامة البيانات

لقطة الطابور وDQ أُخذت من PostgreSQL الحية عبر جلسات معاملات `READ ONLY`. بعد التحقق من عدم وجود اختلافات في seed مصادر التشغيل، حُدّثت حاويتا API والواجهة فقط لتطبيق الكود الحالي؛ لم تُعد تشغيل PostgreSQL أو Redis أو العامل أو الجدولة. `/health/ready` بعد التحديث=200. الطابور الحالي **498** مراجعة مفتوحة. من بينها **9** حالات `SOURCE_RECHECK_REQUIRED` لا تسمح بالحسم النهائي، و**489** حالة تبقى ضمن مسار الحكم البشري. تفصيل disposition: 72 `HUMAN_REVIEW_REQUIRED`، و7 `EVIDENCE_RECOVERED_BUT_HUMAN_REVIEW_REQUIRED`، و410 `RETAIN_OPEN`، و9 تحقق مصدر.

توزيع الأولوية: P1=0، P2=428، P3=57، P4=13. التوزيع حسب النوع: تكرار=10، تعارض حقل=423، موقع=15، تعارض تصنيف=50.

لقطة الإغلاق المحدّثة بتاريخ 2026-10-22 15:03:41 (+03) أبقت الطابور عند 498/489/9، بينما ارتفع عدد مهام المزامنة من 436 إلى **441** بفعل خمسة تشغيلات مجدولة طبيعية (437–441). سجل 437 لموان FAILED؛ 438 لصندوق الاستثمارات العامة SUCCESS؛ 439 لاستثمر في السعودية SUCCESS؛ 440 لهيئة تطوير الأحساء SUCCESS؛ و441 لمدن FAILED. لكل مهمة `master_new_count=0` و`master_update_count=0`. سجلت المهمة 439 قيمة `removed_records_count=2423`، وهي قيمة تشغيل معلنة وليست فرقاً صافياً مثبتاً في جدول المصدر. لا تتوفر snapshots قبل/بعد لهذه المهام لحساب صافي فرق صفوف المصدر أو فرق observations أو reviews؛ لذلك تسجل هذه الفروق `null` في لقطة الحالة. جميع المهام الخمس `trigger_type=scheduled`؛ لم تبدأ مزامنة يدوية، ولا تُنسب إلى تنفيذ مساحة العمل. الخدمة وواجهة الجاهزية بقيتا تعملان (HTTP 200).

## تنفيذ الحواجز المتبقية

- إعادة الفتح خاضعة للصلاحية والحالة ورمز النسخة والسبب المعتمد. معاينة الفتح تعرض القرار السابق وما هو معروف فقط؛ بيانات التدقيق التاريخية الناقصة تظهر بوضوح دون اختلاق منفذ أو وقت أو سبب. عملية إعادة الفتح تحفظ القرار السابق وتضيف حدث تدقيق جديدًا، مع رفض الرمز الناقص/المتغير أو الحالة غير المناسبة.
- سجل المراجعة موحد ومقروء، بمعرّفات مستقرة وترتيب حتمي. السجلات التاريخية ذات الوقت غير المعروف موضوعة في مجموعة مميزة ولا تُمنح أوقاتًا مصطنعة.
- التوصيات حتمية ومحدودة بالقواعد المعتمدة، مع مستوى HIGH/MEDIUM/NONE وشرح وأدلة داعمة ومتعارضة وإصدار. الحالات الملتبسة وSOURCE_RECHECK تعيد NONE. لا توصية تحفظ قرارًا تلقائيًا؛ تُحفظ لقطة التوصية التي شاهدها المحلل وقت القرار.
- اتباع التوصية أو تجاوزها يظهر في التدقيق والسجل. التجاوز يتطلب سببًا معتمدًا.
- الدفعات مقتصرة على الحالات ذات التوقيع الحتمي الواحد. المعاينة تعرض المؤهل والمستبعد، والتوقيع المتغير أو العضو المتقادم يرفض المعاملة كاملة. لا دمج جماعي للتكرارات. لكل عنصر حدث تدقيق فردي، ويمنع معرّف العملية تكرار الإرسال من مضاعفة الالتزام.
- واجهة عربية RTL والأرقام الغربية محفوظة. اختبارات Playwright المعزولة غطت تدفقات المتابعة والتجاوز وإعادة الفتح والدفعة الصحيحة ورفض الدفعة المختلطة ورفض النسخة المتقادمة، في الأحجام الخمسة المطلوبة.

## نتائج التحقق

- الاختبارات المركزة لمساحة العمل: **45 ناجحًا / 0 فشل**.
- مجموعة الانحدار المعزولة كاملة: **438 ناجحًا / 0 فشل**.
- Playwright: **1920×1080، 1440×900، 1366×768، 768×900، 390×844**؛ RTL والأرقام الغربية ناجحان، لا تمرير أفقي، لا عناصر مقصوصة أو متداخلة، وأخطاء JavaScript=0.
- تدفقات المتصفح المعزولة الستة: متابعة التوصية، تجاوزها، إعادة الفتح مع حفظ القرار السابق ثم الحسم، الدفعة الحتمية، رفض الدفعة المختلطة، ورفض النسخة المتقادمة — كلها ناجحة. لا تغييرات على مراجعات PostgreSQL الحية من الاختبارات.
- زمن تفاصيل API: P95 **17 ms** من 30 طلب GET في بيئة API/SQLite اصطناعية معزولة؛ السابق 337 ms؛ التغير **−320 ms**. لا يوجد حد أداء متفق عليه.
- مصفوفة القبول: **89/89 PASS، 0 FAIL، 0 UNTESTED**، مع ربط كل سيناريو باختبار مركز أو تدفق Playwright أو بوابة DQ حية.

### DQ الحي الكامل

**92 بوابة: 87 PASS، 5 WARNING، 0 FAIL** في تقييم قراءة فقط أُخذ في 2026-10-22 15:03:41 (+03). جميع بوابات الحوكمة الحالية المطلوبة اجتازت بقيمة مرصودة صفر. التحذيرات الخمسة مفهومة ومحددة:

1. `GENERIC_SOURCE_PAGE_AS_OPPORTUNITY_ACTION`: 782 سجلًا لا يملك إلا صفحة مصدر رسمية عامة؛ عدد الروابط العامة المعروضة كإجراء أصلي للفرصة=0.
2. `OPEN_REVIEW_BACKLOG`: 498 مراجعة مفتوحة؛ رصيد يتطلب العمل ولا يمثل فشل سلامة.
3. `HISTORICAL_REVIEW_AUDIT_INCOMPLETE`: 120 تدقيقًا تاريخيًا ناقص البيانات؛ بقيت تحذيرًا موثقًا بلا اختلاق بيانات.
4. `SOURCE_LAST_SUCCESS_TOO_OLD`: حداثة أربعة مصادر (Invest Saudi وMODON وNHC وMWAN) ضمن بوابة مجمعة واحدة؛ لا إخفاقات حداثة.
5. `SYNC_RUNTIME_ANOMALY`: تحذير رصد معلوماتي لمهمة 393 المكتملة؛ لم تُغيّر المهمة.

بوابات الحوكمة الحية ذات الصلة، بما فيها القرار دون تدقيق، الإجراء غير الصالح، النسخة المتقادمة، نقص أدلة/شرح/لقطة التوصية، التجاوز دون سبب/تدقيق، إعادة الفتح دون تدقيق، قرار الدفعة غير الحتمي/دون تدقيق فردي، وتجاوز RBAC كلها `PASS` بقيمة مرصودة 0.

## التأكيدات النهائية

```text
HUMAN_REVIEW_DECISION_WORKBENCH = COMPLETE
OPEN_REVIEWS_CURRENT = 498
SYNC_JOBS_CURRENT = 441
HUMAN_REVIEW_REQUIRED_CURRENT = 489
SOURCE_RECHECK_REQUIRED_CURRENT = 9

REOPEN_UI_IMPLEMENTED = TRUE
REOPEN_BACKEND_VALIDATION = TRUE
REOPEN_REASON_REQUIRED = TRUE
VERSION_REQUIRED_FOR_REOPEN = TRUE
STALE_REOPEN_COMMIT = 0
NEW_REOPEN_WITHOUT_AUDIT = 0
PREVIOUS_RESOLUTION_PRESERVED_AFTER_REOPEN = TRUE
FABRICATED_LEGACY_REOPEN_METADATA = 0

UNIFIED_REVIEW_TIMELINE = TRUE
TIMELINE_STABLE_ORDERING = TRUE
FABRICATED_LEGACY_TIMELINE_DATA = 0

SYSTEM_RECOMMENDATION_AVAILABLE = TRUE
RECOMMENDATION_CONFIDENCE_LEVELS = HIGH/MEDIUM/NONE
AMBIGUOUS_CASES_FORCE_RECOMMENDATION = FALSE
RECOMMENDATIONS_WITHOUT_EXPLANATION = 0
RECOMMENDATIONS_WITHOUT_EVIDENCE = 0
RECOMMENDATION_CAN_AUTO_COMMIT = FALSE
RECOMMENDATION_SNAPSHOT_STORED_AT_DECISION = TRUE
RECOMMENDATION_OVERRIDE_REASON_REQUIRED = TRUE
RECOMMENDATION_OVERRIDES_WITHOUT_REASON = 0
RECOMMENDATION_OVERRIDES_WITHOUT_AUDIT = 0
SOURCE_RECHECK_DIRECT_RESOLUTION_ALLOWED = FALSE

BATCH_ACTIONS_IMPLEMENTED = TRUE
BATCH_ACTIONS_RESTRICTED_TO_DETERMINISTIC_CASES = TRUE
BATCH_DECISION_SIGNATURE_IMPLEMENTED = TRUE
BATCH_DUPLICATE_MASTER_MERGE_ENABLED = FALSE
MIXED_SIGNATURE_BATCH_REJECTED = TRUE
BATCH_PREVIEW_IMPLEMENTED = TRUE
BATCH_COMMIT_POLICY = atomic all-or-none commit; one audit per review; operation-ID idempotency
BATCH_RESOLVED_REVIEW_WITHOUT_INDIVIDUAL_AUDIT = 0
DUPLICATE_BATCH_SUBMIT_DOUBLE_COMMIT = FALSE

VERSION_TOKEN_REQUIRED = TRUE
MISSING_VERSION_REJECTED = TRUE
STALE_VERSION_DECISION_REJECTED = TRUE
CONCURRENT_REVIEW_LOST_UPDATE = FALSE
VIEWER_CAN_RESOLVE_REVIEW = FALSE
ANALYST_RESOLUTION_RBAC = PASSED
ADMIN_RESOLUTION_RBAC = PASSED

ACCEPTANCE_MATRIX_TOTAL_SCENARIOS = 89
ACCEPTANCE_MATRIX_PASS = 89
ACCEPTANCE_MATRIX_FAIL = 0
ACCEPTANCE_MATRIX_UNTESTED = 0

LIVE_DQ_TOTAL_GATES = 92
LIVE_DQ_PASS = 87
LIVE_DQ_WARNING = 5
LIVE_DQ_FAIL = 0
DQ_CURRENT_HUMAN_DECISION_WITHOUT_AUDIT = 0
DQ_CURRENT_INVALID_REVIEW_ACTION = 0
DQ_STALE_REVIEW_DECISION_COMMIT = 0
DQ_RECOMMENDATION_WITHOUT_EVIDENCE = 0
DQ_RECOMMENDATION_WITHOUT_EXPLANATION = 0
DQ_RECOMMENDATION_OVERRIDE_WITHOUT_REASON = 0
DQ_RECOMMENDATION_SNAPSHOT_MISSING = 0
DQ_REOPEN_WITHOUT_AUDIT = 0
DQ_NONDETERMINISTIC_BATCH_DECISION = 0
DQ_BATCH_WITHOUT_INDIVIDUAL_AUDIT = 0
DQ_REVIEW_RBAC_VIOLATION = 0

FOCUSED_WORKBENCH_TESTS = 45 passed / 0 failed
FULL_REGRESSION_SUITE = 438 passed / 0 failed
PREVIOUS_REVIEW_DETAIL_API_P95_MS = 337
CURRENT_REVIEW_DETAIL_API_P95_MS = 17
P95_DELTA_MS = -320

PLAYWRIGHT_1920x1080 = PASSED
PLAYWRIGHT_1440x900 = PASSED
PLAYWRIGHT_1366x768 = PASSED
PLAYWRIGHT_768x900 = PASSED
PLAYWRIGHT_390x844 = PASSED
PLAYWRIGHT_FOLLOW_RECOMMENDATION_FLOW = PASSED
PLAYWRIGHT_OVERRIDE_RECOMMENDATION_FLOW = PASSED
PLAYWRIGHT_REOPEN_FLOW = PASSED
PLAYWRIGHT_BATCH_FLOW = PASSED
PLAYWRIGHT_INVALID_BATCH_FLOW = PASSED
PLAYWRIGHT_STALE_VERSION_FLOW = PASSED
RTL = PASSED
WESTERN_DIGITS = PASSED
HORIZONTAL_PAGE_OVERFLOW = FALSE
JAVASCRIPT_CONSOLE_ERRORS = 0

LIVE_REVIEWS_RESOLVED_DURING_BUILD = 0
LIVE_REVIEWS_REOPENED_DURING_BUILD = 0
LIVE_BATCH_RESOLUTIONS_DURING_BUILD = 0
LIVE_BUSINESS_DATA_CHANGES_DURING_BUILD = 0 (implementation-attributable; scheduled source jobs above are reported separately)
MANUAL_SOURCE_SYNC_STARTED = FALSE
```

## ملفات الإغلاق

- [مصفوفة القبول](review-workbench-acceptance-matrix.json)
- [اختبارات إعادة الفتح](review-workbench-reopen-tests.json)
- [اختبارات السجل الزمني](review-workbench-timeline-tests.json)
- [اختبارات التوصية](review-workbench-recommendation-tests.json)
- [اختبارات التجاوز](review-workbench-override-tests.json)
- [اختبارات الدفعات](review-workbench-batch-tests.json)
- [تحقق الصلاحيات](review-workbench-rbac-validation.json)
- [اختبارات التزامن](review-workbench-concurrency-tests.json)
- [اختبارات التدقيق](review-workbench-audit-tests.json)
- [قياس الأداء](review-workbench-performance.json)
- [DQ الحي الكامل للقراءة فقط](review-workbench-dq-results.json)
- [نتائج Playwright واللقطات](review-workbench-playwright-results.json)
- [لقطات الأحجام الخمسة](screenshots/final-closeout/)




