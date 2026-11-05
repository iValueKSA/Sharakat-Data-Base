# إغلاق أسباب فشل DQ ومعالجتها

**النتيجة:** `FOCUSED_DQ_FAILURE_ROOT_CAUSE_REMEDIATION = COMPLETE`  
**التقاط الحالة الحية:** 2026-10-22 13:28:16 +03  
**النطاق:** تدقيق ومعالجة ثلاثة إخفاقات DQ مسجلة سابقًا فقط. لم تُعَد مراجعة استعادة الأدلة أو فرز الرصيد، ولم يُبنَ Workbench في هذه المهمة.

## الحالة المجمدة — قراءة فقط

| المؤشر | القيمة |
|---|---:|
| الفرص الرئيسية الحالية | 526 |
| كل Masters | 547 |
| Masters مدمجة | 21 |
| سجلات فرص المصادر | 3,138 |
| الملاحظات التاريخية | 16,460 |
| كل المراجعات | 742 |
| مفتوحة | 498 |
| محسومة | 233 |
| مستبدلة | 11 |
| مهام المزامنة | 434، أعلى معرّف 434 |

أعداد المراجعات تجمع كل الأنواع وحالاتها المتبادلة الاستبعاد. لم يكتب تشغيل DQ أي حدث (`persist=false`) واستخدم معاملة PostgreSQL للقراءة فقط.

## 1. بوابة القرار البشري بلا تدقيق

الـ141 سجلًا الأصلي صُنّفت جميعها من حقول المراجعات وسجل الدمج والمعلومات المحفوظة:

| الفئة | العدد | النتيجة |
|---|---:|---|
| A — قرار حالي بلا التدقيق المطلوب | 0 | لا عيب حالي مثبت |
| B — مرفوضة قبل التدقيق المُرقّم | 16 | وقت `reviewed_at` محفوظ، والمنفذ غير محفوظ |
| C — حسم آلي أُسيء تصنيفه كقرار بشري | 0 | لا سجل من هذه الفئة |
| D — تدقيق دمج موجود لكن البوابة القديمة لم تربطه | 21 | سجل `MergeAudit` مطابق بالزوج الدقيق؛ لا يوجد `AuditEvent` مراجعة مرتبط |
| E — بيانات تاريخية ناقصة | 104 | لا وقت حسم أو منفذ أو إجراء محفوظ |
| F — سبب آخر موضح | 0 | — |

كل الـ141 تشير إلى كيانات حالية صالحة. إجمالي القيود التاريخية غير المكتملة الذي يبقى تحذيرًا هو **120 = 16 + 104**. لم تُختلق أوقات أو منفذون أو أسباب أو أحداث تدقيق. الـ21 حالة دمج ليست قرارات بشرية بلا تدقيق؛ لها سجل دمج عكسي مستقل.

**حد الحوكمة:** لا يوجد Git history في مجلد المشروع، ولا تحتوي ترحيلات قاعدة البيانات على تاريخ سياسة إلزام تدقيق المراجعات. أقدم دليل محفوظ يحمل `review_audit_version` هو الحدث 69 في `2026-10-20T15:56:01+03:00`. أستخدمه حدًا محافظًا مشتقًا من البيانات؛ تاريخ بدء الإلزام الفعلي الدقيق `UNKNOWN`.

عُدلت بوابة DQ لتفشل إذا كانت مراجعة مغلقة بلا تدقيق قد أُنشئت عند/بعد هذا الحد حتى في الجداول القديمة التي لا تحفظ `resolved_at`. أما السجل الأقدم الذي يفتقر لوقت الحسم فيبقى ضمن تحذير تاريخي. الاختبار الجديد يثبت الفصل بين الحالتين.

## 2. الإجراءات الـ11 التي ظهرت غير صالحة

الأحداث 69–78 و81 كلها انتقالات `OPEN → SUPERSEDED` صادرة عن `review-governance-reconciliation` أو `field-conflict-reconciliation`. أنواعها `STANDARDIZATION_REVIEW_SUPERSEDED` و`MERGED_DURATION_REVIEW_SUPERSEDED` و`LOGICAL_DUPLICATE_SUPERSEDED`. كانت أسماء دورة حياة نظامية خارج قائمة أفعال الإنسان، والبوابة القديمة طبقت قائمة الإنسان عليها.

- عدد الأفعال الحالية غير الصالحة: **0**.
- الأسماء التاريخية التي ليست إجراءات بشرية: **11**.
- أسماء قديمة ثبت تكافؤها مع إجراء حالي: **0**.
- إجراءات تاريخية بشرية ثبت بطلانها: **0**.
- `KEEP_CURRENT_VALUE` والإجراءات الاعتباطية تظل مرفوضة ما لم توجد خريطة تكافؤ موثقة؛ لا توجد واحدة هنا.

## 3. تكرار Master 112 في القائمة

السبب هو **ترقيم صفحات غير مستقر**، لا تكرار هوية Master أو انفجار join. فحص النسخ البرمجية المؤرشفة يبين أن الترتيب القديم كان `last_updated_at DESC` وحده. Master 112 يقع ضمن مجموعة من **21 Master** تتشارك الطابع الزمني نفسه، ولذلك أمكن أن يتغير ترتيب الصفوف المتعادلة عند استعمال `offset`.

Master 112 نفسه له مصدر واحد، و9 ملاحظات، و0 مراجعات. القائمة تستخدم استعلام Master مع تحميل `selectin`، ومرشح المصدر يستخدم استعلامًا فرعيًا لمعرّفات Master؛ لا توجد علاقة متعددة الصفوف تضاعف النتيجة. الشيفرة الحالية كانت تتضمن مفتاح الترتيب الثابت `last_updated_at DESC, id DESC` قبل هذه المهمة. لم أغير استعلام القائمة.

تحقق القراءة الحية الحالي أعاد **526 صفًا و526 معرّف Master فريدًا**، بلا معرّفات مفقودة أو زائدة. أحجام الصفحات: 100، 100، 100، 100، 100، 26. القطاع والحالة والمصدر والموقع والبحث أعادت صفًا واحدًا لكل Master. CSV وXLSX يحتوي كل منهما 526 صف فرصة، والبوابة `API_DASHBOARD_EXPORT_RECONCILIATION` نجحت. اختبار SQLite جديد يغطي الطوابع المتساوية، وتعدد المصادر والملاحظات والمراجعات، والمرشحات، وإقصاء المدمج، والصفحات والتصدير.

## تشغيل DQ الكامل

```text
LIVE_DQ_TOTAL_GATES = 90
LIVE_DQ_PASS = 85
LIVE_DQ_WARNING = 5
LIVE_DQ_FAIL = 0
CURRENT_HUMAN_DECISION_WITHOUT_AUDIT = 0
CURRENT_DECISIONS_WITH_INVALID_ACTION = 0
CURRENT_LIST_DUPLICATE_MASTER_ROWS = 0
```

التحذيرات الخمسة مفسرة:

- `GENERIC_SOURCE_PAGE_AS_OPPORTUNITY_ACTION = 782`: صفحة مصدر عامة بدل رابط تفاصيل فردي؛ لا يُعرض الرابط العام كإجراء للفرصة.
- `OPEN_REVIEW_BACKLOG = 498`: رصيد مراجعات بشري مفتوح، وليس إخفاق تكامل.
- `HISTORICAL_REVIEW_AUDIT_INCOMPLETE = 120`: نقص تاريخي موثق أعلاه.
- `SOURCE_LAST_SUCCESS_TOO_OLD = 4`: بوابة واحدة مجمعة تشمل Invest Saudi وMODON وNHC وMWAN.
- `SYNC_RUNTIME_ANOMALY = 1`: المهمة 393؛ بقيت كما هي وتحذيرية.

## المزامنات المجدولة الطبيعية

لم تبدأ مزامنة يدوية. بين اللقطة السابقة عند المهمة 430 واللقطة الحالية نفذت الجدولة المهام التالية. `removed_records_count` إشارة إزالة من المصدر، وليس حذفًا صافيًا من جدول SourceOpportunity؛ بقي مجموع سجلات المصادر 3,138.

| المهمة | المصدر | النتيجة | Master جديد/محدّث | صافي سجلات المصدر | إشارة إزالة | ملاحظات جديدة | مراجعات جديدة |
|---:|---|---|---:|---:|---:|---:|---:|
| 431 | Furas | SUCCESS / scheduled | 0 | 0 | 35 | +35 | +1، مراجعة 709 حسمها النظام إلى `RESOLVED_CANONICAL` |
| 432 | منصة الأحساء | SUCCESS / scheduled | 0 | 0 | 19 | +19 | 0 |
| 433 | Furas | SUCCESS / scheduled | 0 | 0 | 35 | +35 | +1، مراجعة 710 حسمها النظام إلى `RESOLVED_CANONICAL` |
| 434 | منصة الأحساء | SUCCESS / scheduled | 0 | 0 | 19 | +19 | 0 |

ارتفع إجمالي الملاحظات من 16,352 إلى 16,460، وإجمالي المراجعات من 740 إلى 742، وبقيت المفتوحة 498. هذه تغييرات تشغيل مجدولة موثقة ومنفصلة عن إصلاح DQ؛ لم تتغير أعداد Masters أو سجلات المصدر الصافية.

## القرار والتأكيدات

- `HUMAN_DECISION_GATE_CORRECTLY_SCOPED = TRUE`
- `AUDIT_GOVERNANCE_EFFECTIVE_FROM = UNKNOWN` (أقدم دليل مُرقّم: 2026-10-20T15:56:01+03:00، النسخة 1)
- `CURRENT_HUMAN_DECISIONS_WITHOUT_AUDIT = 0`
- `HISTORICAL_INCOMPLETE_DECISION_AUDITS = 120`
- `AUDIT_LINKAGE_FALSE_NEGATIVES = 21` (سجلات MergeAudit المطابقة التي لم تربطها البوابة القديمة)
- `CURRENT_DECISIONS_WITH_INVALID_ACTION = 0`
- `LEGACY_ACTION_ALIASES_CONFIRMED = 0`
- `CURRENT_LIST_DUPLICATE_MASTER_ROWS_AFTER = 0`
- `PAGINATION_DUPLICATE_ROWS = 0`; `PAGINATION_MISSING_ROWS = 0`
- `CSV_DUPLICATE_MASTER_ROWS = 0`; `XLSX_DUPLICATE_MASTER_ROWS = 0`
- `REVIEW_AUDIT_MODEL_READY_FOR_WORKBENCH = TRUE`
- `REVIEW_ALLOWED_ACTION_MODEL_READY_FOR_WORKBENCH = TRUE`
- `CURRENT_MASTER_LIST_READY_FOR_WORKBENCH_LINKING = TRUE`
- `FABRICATED_HISTORICAL_AUDITS = 0`; `FABRICATED_HISTORICAL_ACTIONS = 0`; `FABRICATED_DECISION_REASONS = 0`
- `UNEXPLAINED_BUSINESS_DATA_CHANGES = 0`; `MANUAL_SOURCE_SYNC_STARTED = FALSE`
- `MASTER_IDENTITIES_PRESERVED = TRUE`; `SOURCE_IDENTITIES_PRESERVED = TRUE`; `RAW_PROVENANCE_PRESERVED = TRUE`; `OBSERVATION_HISTORY_PRESERVED = TRUE`; `MERGE_LINEAGE_PRESERVED = TRUE`
- `FOCUSED_TESTS = 84 passed / 0 failed`
- `FULL_REGRESSION_SUITE = 433 passed / 0 failed` (SQLite معزولة)
- `BROWSER_VERIFICATION = NOT_APPLICABLE` — تغيير DQ الخلفي لم يغيّر القائمة أو الواجهة الحالية.

## الأدلة

- [human-decision-audit-root-cause.json](human-decision-audit-root-cause.json)
- [historical-audit-classification.json](historical-audit-classification.json)
- [invalid-review-action-root-cause.json](invalid-review-action-root-cause.json)
- [legacy-action-mapping.json](legacy-action-mapping.json)
- [current-list-duplicate-root-cause.json](current-list-duplicate-root-cause.json)
- [current-list-reconciliation.json](current-list-reconciliation.json)
- [dq-failure-remediation.json](dq-failure-remediation.json)
- [dq-full-rerun.json](dq-full-rerun.json)
- [focused-test-results.json](focused-test-results.json)
- [playwright-results.json](playwright-results.json)

