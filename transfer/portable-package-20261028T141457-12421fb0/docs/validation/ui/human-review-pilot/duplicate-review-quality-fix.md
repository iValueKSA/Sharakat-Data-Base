# إقفال إصلاح جودة مراجعات التكرار

**النتيجة: مكتمل — 2026-10-25.** أضيف تفسير مرئي للفروق وسبب المراجعة البشرية، وتحققت الواجهة على سجلات حية للقراءة فقط. لم يتغير أي قرار مراجعة أو سجل فرصة، ولم يبدأ تحديث للمصادر.

## النتيجة المعتمدة للحالات

الأرقام أدناه هي خلاصة العمل المقبولة قبل هذه الخطوة؛ لم يُعد فتح تحليل التصنيف:

- المراجعات المفتوحة قبل/بعد: **10 / 10**.
- التكرارات الحتمية: **0**؛ الحالات المتقاربة ذات فروق حقيقية: **10**.
- الحالات الملتبسة: **7 من المصدر نفسه، و3 عابرة للمصادر**.
- الإيجابيات الكاذبة المثبتة: **0**؛ المحسومة آليًا: **0**؛ المراجعات غير الصالحة المغلقة: **0**.
- المتبقية للمراجع البشري: **10**؛ ولا توجد حالة متطابقة المظهر بلا شرح (**0**).
- اختلاف المعرّفات الرسمية يعطل الدمج الآلي، لكنه لا يثبت أن الفرصتين مختلفتان؛ قرار «نفس الفرصة» يبقى متاحًا للمحلل عندما يسنده الدليل.

فُحصت تفاصيل المقارنة الحية للحالات العشر عبر GET فقط: **10/10 مفتوحة، 10/10 لها فروق ذات معنى وسبب مراجعة ظاهر، و47 حقل مقارنة في كل سجل**. تشمل الحقول معرّفات المصدر ومعرّفات الفرص لدى المصدر، المالك والناشر ومنصة النشر، الموقع والإحداثيات، القطاع والنشاط والنشاط الفرعي، نوع الفرصة ونموذج الاستثمار ونوع الأصل/المرفق، المساحة والقيمة والعملة والمدة، التواريخ والحالة والوصف، وحقول الهوية الخام من المصدر.

## توضيح الواجهة والحوكمة

تعرض الواجهة «الاختلافات بين الفرصتين» أولًا، وتجمع الحقول المطابقة تحت «عرض الحقول المتطابقة». يظهر دائمًا سبب «لماذا تتطلب هذه الحالة مراجعة بشرية؟»، مع نص صريح يبيّن أن اختلاف المعرّف سبب لعدم الدمج الآلي وليس برهانًا على اختلاف الفرصتين.

تحافظ الواجهة على الاختيارات الثلاثة:

- «نفس الفرصة — دمج».
- «ليستا نفس الفرصة».
- «غير محسوم / إبقاء للمراجعة»؛ هذا الاختيار يمسح تحديد القرار محليًا ويترك الحالة مفتوحة بلا طلب كتابة.

تم فحص مراجعة من المصدر نفسه (32)، ومراجعة عابرة للمصادر (46)، وحالة تكرار من الطيار المجمد (34). اكتملت **15 حالة عرض** (3 مراجعات × 5 أحجام): 1920×1080، 1440×900، 1366×768، 768×900، 390×844. كانت لوحة الفروق وموسع الحقول المطابقة وسبب المراجعة والاختيارات ظاهرة؛ RTL صحيح، ولا تمرير أفقي، و**0 أخطاء JavaScript**. طلبات `recommendation-shown` الخلفية اعترضها الاختبار ولم تصل للخادم؛ لم يُرسل أي قرار.

`DUPLICATE_DIFFERENCE_PANEL = PASSED`  
`IDENTICAL_FIELDS_EXPANDER = PASSED`  
`HUMAN_REVIEW_REASON_VISIBLE = PASSED`  
`RTL = PASSED`  
`HORIZONTAL_OVERFLOW = FALSE`  
`JAVASCRIPT_ERRORS = 0`

## العينة المجمدة

ملف العينة ظل كما هو؛ بصمته SHA-256: `E72CB979EBD28E18F302FFA9C1453B2B290496679B83B8ED4CEF34AAC6815C8C`.

`PILOT_SAMPLE_SIZE = 40`  
`PILOT_DUPLICATE_CASES = 6`  
`PILOT_UNNECESSARY_DUPLICATE_REVIEWS = 0`  
`PILOT_CASES_REPLACED_WITH_AUDIT = 0`  
`SOURCE_RECHECK_IN_PILOT = 0`

ملاحظة تحقق: طلب GET لملخص `/api/admin/review-workbench/pilot` أعاد خطأ `detail=id`. لم تُغيّر هذه الحالة العينة أو تُعد توليدها؛ استند التحقق إلى ملف العينة المجمد، وملف الأثر السابق، وتطابق بصمة ملف الـcohort.

## الاختبارات وDQ

الاختبارات المركزة بعد إضافة السبب والاختيار غير المحسوم: **19 ناجحًا / 0 فشل**. الانحدار الكامل بعد التغييرات شُغّل داخل حاوية بلا شبكة وبقاعدة SQLite مؤقتة: **495 ناجحًا / 0 فشل** (33 تحذير إزالة إهمال من المكتبات؛ لم يُعطل أو يُخفف اختبار وظيفي).

DQ المركّز للقراءة فقط: **42 بوابة؛ 42 PASS، 0 WARNING، 0 FAIL**. DQ الحي الكامل، باستخدام `persist=False`: **103 بوابة؛ 98 PASS، 5 WARNING، 0 FAIL**. لا توجد بوابة DQ فاشلة؛ التحذيرات الخمسة القائمة خارج بوابات جودة مراجعة التكرار.

| بوابة DQ | القيمة المرصودة | الحالة |
|---|---:|---|
| DUPLICATE_REVIEW_WITH_NO_MEANINGFUL_DIFFERENCE | 0 | PASS |
| IDENTICAL_REVIEW_WITHOUT_BLOCKING_REASON | 0 | PASS |
| SAME_SOURCE_SAME_OFFICIAL_ID_MULTIPLE_CURRENT_RECORDS | 0 | PASS |
| DETERMINISTIC_DUPLICATE_LEFT_FOR_HUMAN_REVIEW | 0 | PASS |

## سلامة البيانات والخدمات

لقطة القراءة بعد التحقق: 547 فرصة، 3,138 سجل مصدر، 23,528 ملاحظة مصدر، 10 مراجعات تكرار معلقة، 21 سجل دمج تاريخي، و473 مهمة مزامنة بلا مهام نشطة. تطابق عداد المهام وحالات المراجعة وسجلات الدمج والفرص مع خط الأساس المتاح. لا توجد تغييرات أعمال أو مراجعات من هذا العمل. الخدمات سليمة؛ أُعيد إنشاء API والواجهة فقط لتطبيق تغييرات العرض، وبقيت PostgreSQL وRedis والعامل والجدول الدوري عاملة.

`LIVE_DUPLICATE_REVIEWS_RESOLVED = 0`  
`LIVE_MASTERS_MERGED = 0`  
`BUSINESS_DATA_CHANGES = 0`  
`MANUAL_SOURCE_SYNC_STARTED = FALSE`

## الإقرارات النهائية

```text
DUPLICATE_REVIEW_QUALITY_FIX = COMPLETE
OPEN_DUPLICATE_REVIEWS_BEFORE = 10
EXACT_DETERMINISTIC_DUPLICATES = 0
NEAR_DUPLICATES_WITH_REAL_DIFFERENCES = 10
SAME_SOURCE_AMBIGUOUS = 7
CROSS_SOURCE_AMBIGUOUS = 3
FALSE_POSITIVE_REVIEWS = 0
DETERMINISTIC_AUTO_RESOLVED = 0
INVALID_REVIEWS_CLOSED = 0
REMAINING_HUMAN_DUPLICATE_REVIEWS = 10
IDENTICAL_LOOKING_REVIEW_WITHOUT_EXPLANATION = 0
DETERMINISTIC_DUPLICATE_LEFT_FOR_HUMAN_REVIEW = 0
PILOT_DUPLICATE_CASES = 6
PILOT_UNNECESSARY_DUPLICATE_REVIEWS = 0
PILOT_CASES_REPLACED_WITH_AUDIT = 0
DQ_DUPLICATE_REVIEW_NO_DIFFERENCE = 0
DQ_IDENTICAL_REVIEW_NO_EXPLANATION = 0
DQ_SAME_SOURCE_IDENTITY_DUPLICATION = 0
DQ_DETERMINISTIC_DUPLICATE_LEFT_HUMAN = 0
AMBIGUOUS_DUPLICATES_AUTO_RESOLVED = 0
SAME_SOURCE_FUZZY_AUTO_MERGES = 0
FOCUSED_TESTS = 19 passed / 0 failed
FULL_REGRESSION_SUITE = 495 passed / 0 failed
PLAYWRIGHT_DUPLICATE_REVIEW_UI = PASSED
LIVE_DUPLICATE_REVIEWS_RESOLVED = 0
LIVE_MASTERS_MERGED = 0
BUSINESS_DATA_CHANGES = 0
MANUAL_SOURCE_SYNC_STARTED = FALSE
```

## أدلة التحقق

- `duplicate-review-difference-audit.json` — حقول المقارنة والفروق والأسباب للعشر مراجعات.
- `duplicate-review-dq-results.json` — نتائج DQ المركّز والكامل للقراءة فقط.
- `focused-test-results.json` و`full-regression-results.txt` — نتائج الاختبارين.
- `duplicate-review-playwright.json` — الحالات والأحجام الخمسة ونتائج الواجهة.
- `duplicate-review-pilot-final-validation.json` — حجم العينة وبصمتها وعدم وجود مراجعات مصدر.
- `screenshots/duplicate-review-<id>-<width>x<height>.png` — لقطات الحالات 32 و46 و34.
