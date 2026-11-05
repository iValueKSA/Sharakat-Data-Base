# مراجعة الحقول الكمية والتجارية — التقرير النهائي

**النتيجة:** `QUANTITATIVE_COMMERCIAL_FIELDS_DEEP_REVIEW = COMPLETE`  
**المشروع:** منصة فرص الاستثمار في الأحساء  
**اللقطة الثابتة:** 2026-10-20 07:26:41 UTC. فحص ما بعد التصحيح: 2026-10-20 07:57:58 UTC.  
**مصدر البيانات:** قاعدة PostgreSQL المحلية؛ لم تبدأ مزامنة يدوية.

## A. بنية الحقول

| الحقل | النموذج/الجدول | النوع/الفراغ | المعنى والوحدة | API والواجهة | التصدير |
|---|---|---|---|---|---|
| المساحة | `Opportunity.land_area_sqm` | `Float`, يقبل `NULL` | مساحة موقع/قطعة الفرصة كما أعلنها المصدر، بوحدة م² فقط؛ لا تمثل مساحة مبنى | `area` و`area_unit="m²"`؛ تظهر بجانب «المساحة» | `المساحة (م²)` |
| القيمة الاستثمارية | `Opportunity.investment_value` | `Float`, يقبل `NULL` | مبلغ الاستثمار للفرصة؛ لا يُعرض مبلغ معياري بلا دلالة مالية موثقة | `investment_value` و`currency` | المبلغ والعملة في عمودين مستقلين |
| مدة العقد | `Opportunity.contract_duration_years` | `Float`, يقبل `NULL` | مدة عقد صريحة، معيارها السنة؛ الأشهر الصريحة تحول إلى سنوات، ولا تُخمّن الأيام أو الأرقام المجردة | `duration` و`duration_unit="year"` | `مدة العقد (سنة)` |
| الرقم المرجعي | `Opportunity.reference_number` و`reference_number_normalized` | `String(200)`, يقبل `NULL` | رقم فرصة رسمي كما نشره المصدر | `reference`؛ ويعرض `sources[].source_external_id` منفصلًا | «الرقم المرجعي الرسمي» منفصل عن «معرّفات المصدر التقنية» |

الدليل الخام محفوظ في `SourceOpportunity.raw_data_json`، مع الإسقاط المعياري في `standardized_data_json`. سجل `SourceObservation.raw_data_json` وسجل `ChangeHistory` منفصلان. العملة أصبحت قابلة للفراغ ولا يوجد افتراض SAR عند غياب المبلغ. لم يُنشأ مفهوم `NOT_APPLICABLE` دون دليل؛ الفراغ يعني «غير منشور/غير محدد»، لا صفرًا.

## B. دلالات المصادر

| المصدر | سجلات المصدر / Masters المرتبطة | المساحة | القيمة | المدة | المرجع |
|---|---:|---|---|---|---|
| فرص / Furas | 177 / 177 | `TOTALSPACEINMETERS`؛ م² | لم يُستخدم سعر الكراسة أو الإيجار السنوي كقيمة استثمار | `DURATION` موجود في 103 سجلات، لكن الوحدة ومعنى مدة العقد غير موثقين؛ خام/مراجعة فقط | `OPPORTUNITYID` رسمي؛ `OBJECTID` معرّف تقني |
| منصة الأحساء | 103 / 103 | `details.المساحة` مع وحدة م² صريحة | لا مبلغ مرتبط | `details.مدة العقد`؛ 103 مدد عربية بوحدة سنة صريحة | لا مرجع رسمي منفصل في السجلات المرتبطة |
| هيئة تطوير الأحساء | 8 / 8 | — | — | — | — |
| Invest Saudi | 2,555 / 8 | 462 قيمة `siteArea` نصية بلا وحدة؛ لم تُسقط معياريًا | 462 قيمة خام `investmentSize` بلا عملة؛ لم تُسقط معياريًا | 462 قيمة `contractPeriod` صريحة بوحدة سنوات | 462 قيمة `opportunityNumber` رسمية؛ `id` التقني منفصل |
| جامعة الملك فيصل | 6 / 3 | — | — | — | — |
| مدن | 0 / 0 | لا سجلات حالية | لا سجلات حالية | لا سجلات حالية | لا سجلات حالية |
| المركز الوطني للتخصيص (NCP) | 45 / 1 | — | — | 9 نصوص بالمصدر تذكر مدة صريحة؛ Master 228 يذكر خمس سنوات | معرّف المصدر ليس رقم فرصة رسميًا |
| NHC | 0 / 0 | لا سجلات حالية | لا سجلات حالية | لا سجلات حالية | لا سجلات حالية |
| PIF | 0 / 0 | لا سجلات حالية | لا سجلات حالية | لا سجلات حالية | لا سجلات حالية |
| موان | 5 / 0 | — | — | — | — |

**المعنى الخاص بالمصادر:** لا تُعامل `siteArea` من Invest Saudi كمساحة م² لغياب الوحدة، ولا تُعامل `investmentSize` كمبلغ/عملة لغياب بيانات العملة والمعنى المالي. حقول Furas السعرية أو مدة `DURATION` لم تُحوّل إلى حقول معيارية مالية أو مدة عقد دون دليل.

## C. المساحة

المساحة المعيارية هي مساحة موقع/قطعة الفرصة المعلنة من المصدر بوحدة م²؛ لا نخلطها بمساحة المباني. قُبلت قيم الأحساء ذات وحدة م² الصريحة، وحقل Furas المسمى `TOTALSPACEINMETERS`. الأرقام المجردة من Invest Saudi بقيت خامًا.

- مؤكد: 273 Master؛ غير محدد: 18؛ للمراجعة: 1؛ المجموع: 292.
- لا قيم صفرية أو سالبة. تعارض وحدة: 0؛ تعارض متعدد المصادر: 1.
- Master 230: ظل الاختلاف المفتوح رقم 100 كما هو، المختار 160 م² من Furas مقابل `siteArea=64` من Invest Saudi بلا وحدة. لم أغيّر الاختيار أو أغلق التعارض.
- Master 102: القيمة المعيارية 2 م² مدعومة بحقل Furas؛ تساوي رقم Invest Saudi الخام لا يثبت وحدة الحقل الثاني.

## D. القيمة والعملة

المعنى المعياري هو مبلغ الاستثمار للفرصة، وليس إيجارًا سنويًا أو سعر كراسة. يجب دعم المبلغ والعملة معًا. كانت قيمة العملة الافتراضية SAR حتى مع عدم وجود مبلغ؛ أزال الترحيل `0023_quant_commercial` هذا الافتراض وجعل `currency` قابلة للفراغ.

- قيمة مؤكدة: 0؛ غير محددة: 290؛ للمراجعة: 2؛ المجموع: 292.
- المبلغ المعياري والعملة كلاهما فارغان لكل Masters الـ292. عدد تصاريف العملة المتعارضة: 0؛ تعارضات القيمة متعددة المصادر: 0.
- Masters 102 و230 لديهما `investmentSize="0"` خام من Invest Saudi دون عملة أو دلالة موثقة؛ بقيا للمراجعة، ولم يتحولا إلى صفر SAR.
- لا توجد فرصة بمبلغ معياري منشور في لقطة الإنتاج الحالية. مسار المبلغ الموجود اختُبر بتركيبة معزولة `1,250,000.5 USD` في API وCSV وXLSX. كما تحققت Playwright من عرض القيمة والعملة في التفاصيل عبر اعتراض استجابة اختبارية فقط؛ لم تُضف بيانات اختبار إلى قاعدة الإنتاج.

## E. مدة العقد

المعيار هو مدة عقد موصوفة صراحة؛ تحفظ السنوات كما وردت وتحول الأشهر الصريحة بقسمة 12. لا تُقبل قيمة مجردة أو مدة أيام على أنها سنوات. قيم Furas `DURATION` لا تحمل في طبقة المصدر وحدة موثقة؛ 48 منها `Investment` و55 `TemporaryRental`، فلا يُفترض أنها أشهر.

- مؤكدة: 106؛ غير محددة: 91؛ للمراجعة: 95؛ المجموع: 292.
- تعارض وحدة معلوم: 0؛ تعارض مدة متعددة المصادر: 0.
- من سجلات Furas الـ103 ذات `DURATION`، هناك 8 مدد أكدتها أدلة مستقلة: ستة من سجل الأحساء واثنتان من `contractPeriod` في Invest Saudi. بقيت 55 قيمة `TemporaryRental` و40 قيمة `Investment` بلا مدة عقد مستقلة في قائمة المراجعة.
- أزيلت 40 قيمة معيارية قديمة كانت ناتجة عن افتراض أن رقم Furas أشهر. وأضيفت خمس سنوات لـMaster 228 من عبارة NCP الصريحة «contract duration of 5 years»، مع سجل تغيير.
- حُدّث توثيق مراجعة التكرار القديم ليفصل مدة الأحساء الصريحة عن رقم Furas الخام؛ لم يُعد تقييم أي دمج.

## F. الرقم المرجعي

`reference_number` رقم عمل رسمي؛ `source_opportunity_id`/`source_external_id` هو هوية تقنية خاصة بالمصدر. الرقم الأصلي محفوظ في الحمولة الخام، ومعرّفات Invest Saudi التقنية باقية في سجلات المصدر.

- مرجع رسمي موجود: 177 Master؛ غير محدد: 115؛ مراجعة: 0؛ المجموع: 292.
- أرقام مكررة: 0؛ تصادمات تحتاج مراجعة: 0. الأصفار البادئة والشرطات باقية كنص.
- أزيلت الأرقام التقنية الستة من حقل المرجع المعياري للـMasters 218–223. كذلك صُفّرت 2,093 قيمة مرجعية في سجلات Invest Saudi لعائلات `opportunity` و`pif` و`regional` لأنها معرّفات API؛ بقيت المراجع الرسمية الـ462 من `project.modalData.opportunityNumber`.

## G. التعارضات وقوائم المراجعة

| البعد | قائمة المراجعة |
|---|---|
| المساحة | Master 230؛ التعارض المفتوح رقم 100 (160 مقابل 64 بلا وحدة مؤكدة للثانية) |
| القيمة | Masters 102 و230؛ `investmentSize=0` بلا عملة/دلالة مالية |
| المدة | 95 Master؛ 55 قيمة Furas `TemporaryRental` و40 قيمة `Investment` بلا وحدة أو تأكيد مستقل |
| المرجع | لا حالات ملتبسة؛ 115 Master بلا مرجع رسمي تبقى غير محددة |

لم تُحسم الحالات غير المؤكدة لتقليل قائمة المراجعة.

## H. التصحيحات وسلامة البيانات

- الترحيل `0023_quant_commercial`: أزال العملة الافتراضية SAR من 297 صفًا بلا مبلغ وجعل العمود nullable.
- المعيارية صارت الإصدار 21: وحدات المساحة الصريحة فقط؛ مدد السنوات/الأشهر الصريحة فقط؛ Furas `DURATION` خام/مراجعة؛ مرجع API في Invest Saudi لا يُستخدم كرقم رسمي؛ مستخرج NCP لا يقبل إلا عبارة مدة تعاقد صريحة.
- تغييرات Master المعيارية: مساحة 0، قيمة 0، مدة 41 (40 إزالة تخمين + إضافة واحدة مثبتة)، مرجع 6 (إزالة معرفات تقنية). تغييرات إسقاط المرجع في سجل المصدر: 2,093. أضيف 47 سجل تغيير.
- أُزيل SAR الافتراضي من 297 صفًا؛ لا تغيير في القيمة الاستثمارية المعيارية التي بقيت فارغة.
- الهوية: 297 Master و292 غير مدمج؛ بصمة الهوية المتوافقة قبل/بعد متطابقة. روابط Masters الـ2,899 طابقت جرد المصدر السابق سجلًا بسجل. بصمة الحمولة الخام قبل/بعد متطابقة. الملاحظات 11,124 قبل/بعد؛ لم يُكتب إليها.
- لا تغييرات غير مفسرة، ولا مزامنة يدوية. آخر مزامنة طبيعية قبل اللقطة هي المهمة 373 المجدولة؛ لم تقع مزامنة مجدولة بعد اللقطة الثابتة.

## I. API والواجهة والتصدير

- API أعاد 292 Master. خصائص `area_unit`, `duration_unit`, والعملة الفارغة متسقة مع قيمها؛ تفاصيل Masters 102 و218 و228 و230 تحققت.
- تفاصيل Master 228 تعرض «5 سنة»؛ Master 102 يعرض `2 m²` والمرجع `06-26-183737-46013`؛ Master 230 يعرض `160 م²` و`06-26-183737-49010`، مع بقاء التعارض للمراجعة. Master 218 يفرق بين المرجع غير المنشور والمعرّف التقني.
- CSV وXLSX يحتويان 292 صف بيانات و32 عمودًا: الوحدة ضمن اسم عمود المساحة/المدة، العملة مستقلة، المرجع الرسمي منفصل، والمعرفات التقنية مرة واحدة بلا بادئة مكررة.
- مرجع Master 230 في XLSX نص (`data_type=s`, تنسيق `@`)، مع الشرطات والأصفار البادئة. أكدت اختبارات API وCSV وXLSX مسار مبلغ USD الموجود على قاعدة SQLite اختبارية معزولة.
- Playwright على المنصة الحية تحقق من البحث والصفحات والتفاصيل وRTL وعدم التمرير الأفقي عند المقاسات الخمسة. لقطات الشاشة: [1920×1080](screenshots/opportunities-1920x1080.png)، [1440×900](screenshots/opportunities-1440x900.png)، [1366×768](screenshots/opportunities-1366x768.png)، [768×900](screenshots/opportunities-768x900.png)، [390×844](screenshots/opportunities-390x844.png). لا يوجد مبلغ استثماري منشور حيًا. اختُبر عرضه بمبلغ اختبار عبر API وCSV/XLSX وباستجابة متصفح اختبارية دون إدخاله في بيانات الإنتاج؛ انظر [لقطة المبلغ الاختباري](screenshots/master-102-investment-value-fixture-1440x900.png).

## J. الاختبارات وتوافق التشغيل

اجتازت مجموعة الاختبارات كاملة في إعادة التحقق الحالية **185 اختبارًا، 0 فشل**، على SQLite مؤقتة في حاوية مع ملفات المشروع للقراءة فقط؛ لم تتصل بقاعدة PostgreSQL الحية. يوجد تحذير توافق واحد من Starlette/httpx لا يفشل الاختبارات.

اجتازت مراجعات الانحدار المغلقة: القطاع، النشاط/النشاط الفرعي، نوع الفرصة، نموذج الاستثمار، نوع الأصل/المرفق، الموقع والأهلية الجغرافية، الحالة ودورة الحياة، المالك/الناشر/الجهة، المواعيد، روابط المصادر، وتخطيط لوحة المعلومات. لم أغيّر لوحة المعلومات.

إصدار محرك التوحيد في مساحة العمل وAPI والعامل هو 21؛ تطابق التشغيل ناجح. التطبيق المحلي ما زال جاهزًا ويعمل.

## K. بوابة القبول

```ini
QUANTITATIVE_COMMERCIAL_FIELDS_DEEP_REVIEW = COMPLETE
SNAPSHOT_TOTAL_MASTER_ROWS = 297
SNAPSHOT_NON_MERGED_MASTERS = 292
SNAPSHOT_SOURCE_OPPORTUNITIES = 2899
SNAPSHOT_OBSERVATIONS = 11137

AREA_SEMANTICS_EXPLICIT = TRUE
AREA_UNIT_MODEL_EXPLICIT = TRUE
AREA_CONFIRMED_MASTERS = 273
AREA_UNSPECIFIED_MASTERS = 18
AREA_REVIEW_REQUIRED_MASTERS = 1
AREA_RECONCILIATION_SUM = 292
AREA_RECONCILIATION = PASSED
AREA_UNIT_CONFLICTS = 0
AREA_MULTI_SOURCE_CONFLICTS = 1

INVESTMENT_VALUE_SEMANTICS_EXPLICIT = TRUE
CURRENCY_MODEL_EXPLICIT = TRUE
VALUE_CONFIRMED_MASTERS = 0
VALUE_UNSPECIFIED_MASTERS = 290
VALUE_REVIEW_REQUIRED_MASTERS = 2
VALUE_RECONCILIATION_SUM = 292
VALUE_RECONCILIATION = PASSED
VALUE_CURRENCY_CONFLICTS = 0
VALUE_MULTI_SOURCE_CONFLICTS = 0

CONTRACT_DURATION_SEMANTICS_EXPLICIT = TRUE
DURATION_UNIT_MODEL_EXPLICIT = TRUE
DURATION_CONFIRMED_MASTERS = 106
DURATION_UNSPECIFIED_MASTERS = 91
DURATION_REVIEW_REQUIRED_MASTERS = 95
DURATION_RECONCILIATION_SUM = 292
DURATION_RECONCILIATION = PASSED
DURATION_UNIT_CONFLICTS = 0
DURATION_MULTI_SOURCE_CONFLICTS = 0

REFERENCE_NUMBER_SEMANTICS_EXPLICIT = TRUE
REFERENCE_SEPARATED_FROM_SOURCE_EXTERNAL_ID = TRUE
REFERENCE_CONFIRMED_MASTERS = 177
REFERENCE_UNSPECIFIED_MASTERS = 115
REFERENCE_REVIEW_REQUIRED_MASTERS = 0
REFERENCE_RECONCILIATION_SUM = 292
REFERENCE_RECONCILIATION = PASSED
DUPLICATE_REFERENCE_NUMBERS = 0
REFERENCE_COLLISIONS_REQUIRING_REVIEW = 0

CROSS_FIELD_SEMANTIC_CONTAMINATION_FOUND = 46
CROSS_FIELD_SEMANTIC_CONTAMINATION_REMAINING = 0
OPPORTUNITIES_TABLE_AREA_RECONCILIATION = PASSED
DETAIL_PAGE_QUANTITATIVE_RECONCILIATION = PASSED
CSV_QUANTITATIVE_RECONCILIATION = PASSED
XLSX_QUANTITATIVE_RECONCILIATION = PASSED
XLSX_REFERENCE_FORMAT_PRESERVED = TRUE
API_QUANTITATIVE_FIELD_SEMANTICS = PASSED
BROWSER_QUANTITATIVE_VERIFICATION = PASSED

AREA_CORRECTIONS = 0
INVESTMENT_VALUE_CORRECTIONS = 0
CURRENCY_DEFAULT_CORRECTIONS = 297
DURATION_CORRECTIONS = 41
REFERENCE_CORRECTIONS = 6
INVESTSAUDI_SOURCE_REFERENCE_PROJECTIONS_CLEARED = 2093
UNEXPLAINED_BUSINESS_DATA_CHANGES = 0
MASTER_IDENTITIES_PRESERVED = TRUE
SOURCE_LINKS_PRESERVED = TRUE
RAW_PROVENANCE_PRESERVED = TRUE
OBSERVATION_HISTORY_PRESERVED = TRUE
MANUAL_SOURCE_SYNC_STARTED = FALSE

FULL_REGRESSION_SUITE = 185 passed / 0 failed
WORKSPACE_STANDARDIZATION_ENGINE_VERSION = 21
RUNNING_API_STANDARDIZATION_ENGINE_VERSION = 21
RUNNING_WORKER_STANDARDIZATION_ENGINE_VERSION = 21
RUNTIME_STANDARDIZATION_PARITY = PASSED

SECTOR_TAXONOMY_REGRESSION = PASSED
ACTIVITY_TAXONOMY_REGRESSION = PASSED
OPPORTUNITY_TYPE_TAXONOMY_REGRESSION = PASSED
INVESTMENT_MODEL_TAXONOMY_REGRESSION = PASSED
ASSET_FACILITY_TYPE_TAXONOMY_REGRESSION = PASSED
LOCATION_GEOGRAPHIC_ELIGIBILITY_REGRESSION = PASSED
STATUS_LIFECYCLE_REGRESSION = PASSED
OWNER_ENTITY_REGRESSION = PASSED
DEADLINE_TIMELINE_REGRESSION = PASSED
SOURCE_LINK_INTEGRITY_REGRESSION = PASSED
DASHBOARD_LAYOUT_REGRESSION = PASSED
```

`CROSS_FIELD_SEMANTIC_CONTAMINATION_FOUND=46` means 40 guessed Furas durations plus six technical API IDs previously projected as Master references. The 297 default-SAR placeholders are reported separately. The remaining unverified raw values are explicitly queued; none remain as guessed canonical values.

## الأدلة

- [تسوية الحقول والمعرفات](evidence/final-reconciliation.json)
- [قوائم المراجعة](evidence/review-queues.json)
- [ملخص دلالات المصادر العشرة](evidence/source-semantics.json)
- [جرد القيم التفصيلي](evidence/master-field-evidence.json) و[جرد سجلات المصدر](evidence/source-record-inventory.json)
- [بيان التصحيحات](evidence/correction-manifest.json)
- [تسوية سلامة الهوية والحمولات والملاحظات](evidence/integrity-reconciliation.json)
- [توافق API والعامل](evidence/runtime-parity.json)
- [نتيجة Playwright](playwright-results.json)، [تسوية CSV/XLSX الحية](exports/verification.json)، [سجل الاختبارات](full-regression-results.txt)


## إعادة تحقق الحالة الحالية — 2026-10-20

أُخذت لقطة قراءة فقط عند `2026-10-20T08:21:53Z`، وأُعيد فحص الحالة بعد التحقق عند `2026-10-20T08:24:30Z`. بقيت الأعداد المعيارية دون تغيير: 297 Master (292 غير مدمج، 5 مدمج)، 2,899 سجل مصدر، ومحرك توحيد 21. زادت الملاحظات من 11,124 في لقطة ما بعد التصحيح إلى 11,137 بعد المزامنتين المجدولتين 374 و375، وكلتاهما بدأتا 08:03:32Z: job 374 حدّث 43 سجل مصدر ولم ينشئ أو يدمج Masters؛ job 375 لم يحدّث أو ينشئ سجلات. أُضيفت الملاحظات 11125–11137. لم يبدأ أي تشغيل يدوي.

مقارنة بصمات السلامة قبل/بعد المزامنتين تؤكد تطابق هويات Masters وروابط سجلات المصدر والحمولات الخام وسجل تغييرات Masters والتعارضات المفتوحة. اختلفت بصمات سجل الملاحظات وعدده فقط بسبب الإضافات المجدولة الـ13. لم تُسجّل تغييرات في حقول Master خلال الفترة. بقيت المراجعات الكمية دون تغيير: المساحة 273 مؤكدة + 18 غير محددة + Master 230 للمراجعة؛ القيمة 0 مؤكدة + 290 غير محددة + Master 102 و230 للمراجعة؛ المدة 106 مؤكدة + 91 غير محددة + 95 للمراجعة؛ المرجع 177 مؤكدة + 115 غير محددة + 0 للمراجعة.

أُعيد تشغيل المجموعة كاملة في حاوية اختبار بقاعدة SQLite مؤقتة وملفات المشروع للقراءة فقط: **185 ناجحًا، 0 فشل**. اجتازت Playwright جميع تأكيدات API والتفاصيل والبحث والتنقل والتصدير، مع RTL وعدم التمرير الأفقي في 1920×1080 و1440×900 و1366×768 و768×900 و390×844، دون أخطاء صفحة. تحقّق مجددًا أن CSV وXLSX يحتويان 292 صف بيانات و32 عمودًا، وأن مرجع Master 230 في XLSX نص محفوظ مع الشرطات والأصفار البادئة. نسختا API والعامل تعملان بالمحرك 21، والخدمة جاهزة.

ملفات التحقق الحالي: [لقطة بداية التحقق](evidence/fresh-start-snapshot.json)، [لقطة نهاية التحقق](evidence/fresh-final-snapshot.json)، [بصمات سلامة التشغيل الحالية](evidence/fresh-runtime-safety-snapshot.json)، [نتائج Playwright](playwright-results.json)، [تسوية التصدير](exports/verification.json)، [سجل الاختبارات](full-regression-results.txt).
