# المراجعة النهائية — تجربة معايرة سير عمل المراجعة البشرية

**الحالة: غير مكتملة، بانتظار تنفيذ محلل بشري للقرارات الفعلية.**

## خط الأساس قبل الطيار

أُخذت لقطة قراءة فقط في `2026-10-25T07:21:15Z` بعد التحقق من بقاء الخدمات المحلية جاهزة. كان الطابور يحوي **498** مراجعة مفتوحة: **489** تتطلب مراجعة بشرية و**9** تتطلب تحققًا من المصدر. توزعت الأولوية إلى P1: 0، P2: 428، P3: 57، P4: 13. وتوزعت الأنواع إلى تعارضات حقول 423، تعارضات تصنيف 50، مواقع 15، وازدواجية 10. التفاصيل حسب النوع الفرعي والمصدر محفوظة في `pilot-preflight-snapshot.json`.

كان عدد مهام المزامنة **471**، ولم تكن هناك مهام نشطة ضمن أحدث 100 مهمة مفحوصة. قيمة `MANUAL_SOURCE_SYNC_STARTED` بقيت `FALSE`. لم تُشغّل مزامنة يدوية ولم يتغير أي سجل أعمال أو حالة مراجعة.

## العينة المجمدة

العينة الأصلية ذات 40 حالة محفوظة وبترتيبها ومعرّفاتها وتاريخ تجميدها `2026-10-22T14:59:51.961607+03:00`. المرحلة أ تضم 20 حالة والمرحلة ب 20 حالة. لا توجد حالات إعادة تحقق مصدر ضمن العينة. أُضيفت إلى بيانات العينة وCSV حقول وصف Master والتوصية المتاحة/الثقة من القراءة التمهيدية فقط؛ لم يُستبدل أي عنصر. عند التجميد: 6 ازدواجية، 5 موقع، 6 تصنيف، و23 تعارض حقل.

تُظهر القراءة التمهيدية أن الحالات الأربعين كانت متاحة ومفتوحة وقابلة للمراجعة، وأن التوصية غير متاحة (NONE) لكل الحالات الأربعين. لم يبدأ الطيار: `started=false`، وعدد أحداث الطيار صفر، ولا توجد نتائج أو ملاحظات محلل.

## سير العمل والتغييرات

أُضيف وضع Pilot خفيف داخل Workbench القائم للتنقل في العينة الثابتة، وعرض «الحالة X من 40»، وتسجيل نتائج المحلل وملاحظاته ومقاييس سير العمل دون جمع هوية المحلل أو إنشاء تقييم للأداء. لا يُجبر وضع الطيار على الحسم؛ «إبقاء الحالة مفتوحة» إجراء صالح، وإحالة المصدر تبقى مفتوحة. المرحلة ب محجوبة حتى تسجيل نتائج حالات المرحلة أ العشرين ومراجعتها.

عند بدء الطيار من المحلل، يسجل النظام لقطة جديدة للطابور والمهام حسب المصدر والنوع والأولوية، ثم يحسب الوظائف المجدولة بعد خط البداية بفروق `UNKNOWN` حيث لا تتوافر دلتا موثوقة. لم يُسجل حدث البدء خلال هذا التحقق. أُعيد بناء وتشغيل خدمتي API والواجهة فقط لإتاحة التغيير؛ بقيت قاعدة البيانات والعامل والمجدول وRedis دون إعادة تشغيل. جاهزية API عادت `ready` بعد النشر.

## التحقق التقني

- اختبارات Workbench المركزة: **47 ناجحة، 0 فشل**.
- مجموعة الانحدار الكاملة على SQLite مؤقتة معزولة: **476 ناجحة، 0 فشل**.
- Playwright: **PASSED** على 1920×1080 و1440×900 و1366×768 و768×900 و390×844؛ RTL سليم، ولا تمرير أفقي أو تداخل لأزرار وضع الطيار. لم يُضغط زر البدء ولم تُرسل نتائج.
- لقطة DQ المقبولة قبل الطيار تبقى **99 بوابة: 94 PASS، 5 WARNING، 0 FAIL**. لم يُعد تشغيل DQ لأن الطيار لم يجرِ أي قرار؛ لا توجد قراءة DQ لاحقة يمكن نسبتها إلى الطيار.
- لم تُجر مراجعات أو اختبارات مصدر جديدة، ولم يُفتح أي قرار عمل. مراجعات الطيار التي لم يقررها محلل تبقى كما هي.

## المرحلة أ والمرحلة ب

لم ينفذ محلل بشري أيًا من المرحلتين. لذلك تبقى نتائج الحل والإبقاء مفتوحة وإعادة التحقق وإعادة الفتح والدمج **0 نتيجة مسجلة**؛ وهذه أعداد أحداث مسجلة، وليست حكمًا على صحة قرارات غير موجودة. أعداد كفاية الدليل، وضوح سؤال القرار، ملاءمة الإجراءات، اتباع التوصية/تجاوزها، وزمن المعالجة غير مقاسة بعد وتبقى `null` في سجلاتها. لا توجد نتائج Phase A يمكن استخدامها لمعايرة بين المرحلتين، ولم تطبق تغييرات معايرة تالية للمرحلة أ.

لا تتوافر بعد مصالحة ما بعد الطيار أو فحوص التدقيق اللاحقة للقرار أو DQ التالي للطيار. الدلتا الطبيعية للمراجعات منذ بدء الطيار `UNKNOWN` لأن الطيار لم يبدأ، وأي تشغيل مجدول لاحق يجب أن يسجل بفروق غير معروفة بدل افتراض الصفر.

## جاهزية معالجة بقية الطابور

`NOT_READY_FOR_BULK_HUMAN_REVIEW`. لا يمكن تقييم جاهزية التوسع قبل إكمال المرحلتين الفعليتين، وقياس كفاية الأدلة والتغذية الراجعة والزمن، ثم نجاح مصالحة القرارات والتدقيق وفحص DQ بعد الطيار. هذا ليس فشلًا للطابور؛ إنه شرط إكمال لم يتحقق بعد.

## الإقرارات

```text
HUMAN_REVIEW_PILOT_WORKFLOW_CALIBRATION = NOT_COMPLETE
PILOT_BLOCKER = HUMAN_DECISIONS_NOT_YET_PERFORMED
PILOT_SAMPLE_SIZE = 40
PHASE_A_CASES = 20
PHASE_B_CASES = 20
SOURCE_RECHECK_REQUIRED_IN_PILOT = 0
CODE_AGENT_HUMAN_DECISIONS_MADE = 0
PILOT_REVIEWS_RESOLVED = 0 recorded
PILOT_REVIEWS_KEPT_OPEN = 0 recorded
PILOT_SOURCE_RECHECK_TRANSITIONS = 0 recorded
PILOT_REOPENED_REVIEWS = 0 recorded
PILOT_MERGES = 0 recorded
OPEN_REVIEWS_BEFORE_PILOT = 498 (preflight; start baseline will be recaptured)
OPEN_REVIEWS_AFTER_PILOT = NOT_AVAILABLE
NATURAL_SYNC_REVIEW_DELTA = UNKNOWN (pilot not started)
EVIDENCE_SUFFICIENT_COUNT = 0 collected
EVIDENCE_PARTIAL_COUNT = 0 collected
EVIDENCE_INSUFFICIENT_COUNT = 0 collected
RECOMMENDATIONS_SHOWN = 0 during pilot
RECOMMENDATIONS_FOLLOWED = 0
RECOMMENDATIONS_OVERRIDDEN = 0
RECOMMENDATION_ACCEPTANCE_RATE = NOT_AVAILABLE
COHORT_PREFLIGHT_RECOMMENDATIONS_AVAILABLE = 0
COHORT_PREFLIGHT_NONE_RECOMMENDATIONS = 40
NONE_BUT_HUMAN_RESOLVED = 0
NONE_AND_REMAINED_AMBIGUOUS = NOT_AVAILABLE
AVERAGE_HANDLING_TIME_SECONDS = NOT_AVAILABLE
MEDIAN_HANDLING_TIME_SECONDS = NOT_AVAILABLE
P90_HANDLING_TIME_SECONDS = NOT_AVAILABLE
DECISION_QUESTION_CLEAR = NOT_AVAILABLE
DECISION_QUESTION_UNCLEAR = NOT_AVAILABLE
ACTION_MODEL_GAPS = NOT_ASSESSED
NEXT_REVIEW_FLOW_FAILURES = NOT_ASSESSED
UNSAVED_CHANGES_LOST_DURING_PILOT = NOT_ASSESSED
PILOT_DECISIONS_WITHOUT_COMPLETE_AUDIT = 0 decisions to check
PILOT_BUSINESS_CHANGES_WITHOUT_REVIEW_LINK = 0 pilot changes
POST_DECISION_VALIDATION_FAILURES = NOT_RUN
P0_BLOCKERS_FOUND = 0 detected in technical checks
P1_HIGH_ISSUES_FOUND = 0 detected in technical checks
P2_MEDIUM_ISSUES_FOUND = NOT_ASSESSED
P3_LOW_ISSUES_FOUND = NOT_ASSESSED
P0_BLOCKERS_REMAINING = NOT_ASSESSED
P1_HIGH_ISSUES_REMAINING = NOT_ASSESSED
PHASE_A_MEDIAN_HANDLING_TIME_SECONDS = NOT_AVAILABLE
PHASE_B_MEDIAN_HANDLING_TIME_SECONDS = NOT_AVAILABLE
PHASE_A_EVIDENCE_SUFFICIENT_RATE = NOT_AVAILABLE
PHASE_B_EVIDENCE_SUFFICIENT_RATE = NOT_AVAILABLE
PHASE_A_RECOMMENDATION_OVERRIDE_RATE = NOT_AVAILABLE
PHASE_B_RECOMMENDATION_OVERRIDE_RATE = NOT_AVAILABLE
LIVE_DQ_TOTAL_GATES = NOT_RUN_AFTER_PILOT (accepted baseline 99)
LIVE_DQ_PASS = NOT_RUN_AFTER_PILOT (accepted baseline 94)
LIVE_DQ_WARNING = NOT_RUN_AFTER_PILOT (accepted baseline 5)
LIVE_DQ_FAIL = NOT_RUN_AFTER_PILOT (accepted baseline 0)
NEW_PILOT_CAUSED_DQ_FAILURES = NOT_ASSESSED (no pilot decisions; post-pilot DQ not run)
INVEST_SAUDI_FALSE_MASS_REMOVAL_REGRESSION = FALSE (no sync/review action)
MANUAL_SOURCE_SYNC_STARTED = FALSE
FOCUSED_TESTS = 47 passed / 0 failed
FULL_REGRESSION_SUITE = 476 passed / 0 failed
PLAYWRIGHT_RERUN = PASSED
READY_FOR_BULK_HUMAN_REVIEW = FALSE
```

## الملفات

العينة والنتائج: `pilot-sample.json`, `pilot-case-matrix.csv`, وملفات `pilot-*.json` بجوار هذا التقرير. سجل تجربة الواجهة والصور ضمن `playwright-results.json` و`screenshots/`.