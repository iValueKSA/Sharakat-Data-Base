# مراجعة المصالحة الكاملة لبطاقة المواعيد

**الحالة: COMPLETE** — نُفذ التغيير في عرض Dashboard وواجهات القراءة والتصدير، مع الإبقاء على قواعد توثيق المواعيد الخام دون ترقية أي حقل غير موثوق.

## لقطة ما قبل التعديل

بتاريخ 2026-10-28:

- الفرص النشطة حسب مجموعة الحالات المعتمدة: **474**.
- توزيع البطاقة القديم: 0 خلال 7 أيام، 21 خلال 8–14 يومًا، 39 خلال 15–30 يومًا، و44 أكثر من 30 يومًا.
- مجموع الفئات الأربع: **104**؛ الفارق عن النشط: **370**.
- مجموعة الحالات النشطة المستخدمة بقيت كما هي: `متاحة`, `Announced`, `ANNOUNCED`, `PUBLISHED`, `AVAILABLE`, `ACTIVE`, `منشورة`.

## تفسير الفرص الـ370 المستبعدة

كل Masters الـ370 لا يملك قيمة `submission_deadline` موحدة موثوقة. ولكل منها سجل Furas ذي حقول تاريخ خام، لكن إسقاط المعيارية يضع `mapping_status=UNVERIFIED` و`review_flags=[UNVERIFIED_DATE_FIELD_SEMANTICS]` وفق القاعدة الحالية `furas_dates_raw_only_v1`. تظهر الحقول الخام مثل `STARTDATE` و`ENDDATE` و`LASTRFPSELLDATE`؛ دلالتها غير محسومة كموعد تقديم، لذلك لم تُحوّل إلى موعد نهائي. سجلان من هذه المجموعة مرتبطان أيضًا بـInvest Saudi بلا حقول تاريخ خام، مع بقاء سجل Furas غير الموثوق دليل التصنيف لكل Master.

| سبب الاستبعاد | العدد | التفسير |
|---|---:|---|
| `UNVERIFIED_SOURCE_DATE` | 370 | حقول مصدر خام موجودة لكن دلالتها غير موثقة كموعد تقديم؛ لا يوجد موعد موحد صالح للفئات المؤرخة. |
| `NO_DEADLINE_VALUE` | 0 | لا توجد حالات نشطة بلا موعد موحد وبلا دليل تاريخ خام في هذه اللقطة. |
| `DATE_EXISTS_BUT_NOT_DEADLINE` / `SEMANTICALLY_AMBIGUOUS_DATE` / `INVALID_OR_UNPARSEABLE_DATE` / غير ذلك | 0 | لا توجد حالات إضافية في مجموعة الاستبعاد الحالية. |

**مجموع أسباب الاستبعاد = 370**. ملف التفصيل يتضمن كل Master مستبعد، ومصادره، ومعرّف المصدر، والحقول الخام، وقيمة الموعد الموحد، وحالة الثقة وسبب الاستبعاد. كما يحتوي عينات ممثلة لكل فئة غير صفرية.

## تنفيذ البطاقة والمصالحة بعده

أُعيدت تسمية البطاقة إلى **«توزيع الفرص حسب الموعد»**، وأصبحت تعرض إجمالي النشط 474. الفئات الخمس تستخدم معيارًا موحدًا من جهة الخادم:

| الفئة | العدد | اللون |
|---|---:|---|
| خلال 7 أيام | 0 | `#378AA4` |
| 8–14 يومًا | 21 | `#006E61` |
| 15–30 يومًا | 39 | `#C39853` |
| أكثر من 30 يومًا | 44 | `#7953A9` |
| بدون موعد محدد | 370 | `#989899` |
| **المجموع / النشط** | **474** | — |

الفئات متنافية، واتحاد معرّفات Masters للفئات الخمس يساوي تمامًا معرّفات الفرص النشطة. لا يوجد Master في أكثر من فئة أو خارجها. الفرز الخامس هو `deadline_status=without_reliable_deadline`، ويستبعد المواعيد المستقبلية الموحدة الصالحة ضمن مجموعة الحالة النشطة؛ لا يعتمد على `deadline=NULL` وحده.

أعاد الـAPI 370 نتيجة للفرز الخامس. وتطابق العدد نفسه في CSV وXLSX (**370/370/370**). يدعم الـAPI الفئات الأربع المؤرخة بحدودها الحالية، وتطابقت نتائجها مع البطاقة.

## اختبارات الجودة والانحدار

- المجموعة المركزة: **15 ناجحًا، 0 فشل**.
- الانحدار الكامل المعزول على SQLite مؤقتة، مع تعطيل الشبكة: **599 ناجحًا، 0 فشل**.
- DQ للقراءة فقط: **133 بوابة؛ 128 PASS، 5 WARNING، 0 FAIL**.
- بوابات هذا التغيير الأربع كلها PASS بقيمة ملاحظة 0:
  - `ACTIVE_MASTER_NOT_IN_DEADLINE_DISTRIBUTION`
  - `ACTIVE_MASTER_IN_MULTIPLE_DEADLINE_BUCKETS`
  - `DEADLINE_CARD_TOTAL_MISMATCH`
  - `NO_DEADLINE_BUCKET_FILTER_MISMATCH`
- التحذيرات الخمسة الأخرى في DQ تتعلق بروابط المصدر العامة، وسجل تدقيق المراجعات التاريخية، وحداثة المصادر، وشذوذات زمن تشغيل تاريخية، وتصنيف غياب سجلات المصدر؛ لا يتعلق أي منها ببوابات توزيع المواعيد.

## الفحص المرئي الحي

اجتازت البطاقة المقاسات الخمسة: 1920×1080، 1440×900، 1366×768، 768×900، و390×844. أظهرت كل لقطة مجموعًا يساوي النشط، والملصقات الخمسة والألوان الخمسة. الاتجاه RTL صحيح، ولا تمرير أفقي، ولا أخطاء JavaScript، ولا استجابات HTTP غير متوقعة. سجل Playwright ثلاث استجابات 401 متوقعة لفحص جلسة الزائر على `/api/auth/me`؛ بقيت لوحة البيانات العامة والفرز يعملان دون خطأ HTTP.

النقر على «بدون موعد محدد» فتح قائمة الفرص النشطة، وأظهر `عرض 1–50 من 370 فرصة` مع مرشح `deadline_status=without_reliable_deadline`.

## سلامة البيانات والتشغيل

مقارنة بصمات القراءة قبل وبعد التحقق أثبتت:

- Masters: لا تغيير؛ 587 صفًا (566 حاليًا).
- SourceOpportunity: لا تغيير؛ 3,180 صفًا.
- قيم التواريخ الخام وبصمتها: لا تغيير.
- المهل الموحدة وبصمتها: لا تغيير.
- حالات وبيانات المراجعة وبصمتها: لا تغيير؛ 1,187 مراجعة.
- عمليات الدمج: لا تغيير؛ 21 سجل تدقيق دمج.
- مهام المزامنة: 568 قبلًا وبعدًا؛ لم تظهر مهمة جديدة أو نشطة أثناء نافذة التحقق.
- لم تبدأ مزامنة مصادر يدوية.

لم تتغير قواعد تفسير/تحقق التاريخ أو موثوقية Furas أو معنى تاريخ النشر والبدء أو دلالات انتهاء الفرصة. اقتصرت الإضافة على تقسيم العرض والـAPI والفلترة والتصدير لموعد موحد مستقبلي موثوق، ثم تجميع الباقي في الفئة المحايدة.

## الملفات

- `deadline-card-before.json`
- `deadline-missing-reason-breakdown.json`
- `deadline-card-after.json`
- `deadline-card-active-reconciliation.json`
- `deadline-card-drilldown-validation.json`
- `deadline-card-export-validation.json`
- `deadline-card-playwright.json`
- `deadline-card-live-dq.json`
- `deadline-card-regression-tests.json`
- `deadline-card-safety-before.json` و`deadline-card-safety-comparison.json`
- `screenshots/deadline-card-1920x1080.png`
- `screenshots/deadline-card-1366x768.png`
- `screenshots/deadline-card-390x844.png`

## الإقفال

```ini
ACTIVE_DEADLINE_CARD_FULL_RECONCILIATION = COMPLETE
ACTIVE_OPPORTUNITIES = 474
CURRENT_CARD_TOTAL = 104
ACTIVE_NOT_IN_CURRENT_CARD = 370
MISSING_REASON_COUNTS = UNVERIFIED_SOURCE_DATE: 370
DEADLINE_7D = 0
DEADLINE_8_14D = 21
DEADLINE_15_30D = 39
DEADLINE_OVER_30D = 44
DEADLINE_NO_SPECIFIED = 370
CARD_TOTAL_AFTER = 474
ALL_ACTIVE_MASTERS_IN_EXACTLY_ONE_BUCKET = TRUE
NO_MASTER_IN_MULTIPLE_DEADLINE_BUCKETS = TRUE
NO_DEADLINE_FILTER_API_UI_CSV_XLSX = 370 / 370 / 370 / 370
DEADLINE_BUSINESS_LOGIC_CHANGED = FALSE
MASTER_CHANGES = 0
SOURCE_OPPORTUNITY_CHANGES = 0
RAW_DATE_CHANGES = 0
CANONICAL_DEADLINE_CHANGES = 0
REVIEW_CHANGES = 0
MERGES = 0
MANUAL_SOURCE_SYNC_STARTED = FALSE
FOCUSED_TESTS = 15 passed / 0 failed
FULL_REGRESSION_SUITE = 599 passed / 0 failed
LIVE_DQ = 133 gates / 128 PASS / 5 WARNING / 0 FAIL
PLAYWRIGHT_VIEWPORTS = 5 passed / 0 failed
JAVASCRIPT_ERRORS = 0
UNEXPECTED_HTTP_ERRORS = 0
HORIZONTAL_OVERFLOW = FALSE
```
