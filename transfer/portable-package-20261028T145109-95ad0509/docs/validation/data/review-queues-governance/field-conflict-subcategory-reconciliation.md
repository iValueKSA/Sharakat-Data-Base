# مطابقة تفصيل تعارضات الحقول

**النوع:** تصحيح تقريري مركز؛ لم تُعد المراجعات الدلالية السابقة.
**اللقطة الثابتة المقبولة:** 10/20/2026 16:02:54 — 305 مراجعات مفتوحة، منها 177 FIELD_CONFLICT.
**اللقطة الحية بعد المزامنات المجدولة:** 10/20/2026 16:11:53 — 308 مراجعات مفتوحة، منها 180 FIELD_CONFLICT.

## سبب فجوة 16

المجموع السابق لأقسام الحقول كان 161. السجلات الـ16 الناقصة هي تعارضات حقل sector ذات conflict_type=FIELD_VALUE_CONFLICT. مفتاح السبب FIELD_CONFLICT:sector مشترك بين تصنيفين: 48 سجلًا من TAXONOMY_CONFLICT و16 من FIELD_VALUE_CONFLICT. كان التقرير السابق قد جمع إجمالي مفتاح السبب (64) مع التصنيف، ولم يفصل الـ16 بحسب نوع التعارض. السجلات الـ16 حالات مفتوحة صحيحة (A)، ولم تتغير.

## التقسيم المتنافي عند اللقطة الثابتة (177)

- AREA = 1
- DURATION = 93
- FULL_DESCRIPTION = 2
- INVESTMENT_VALUE = 2
- LOCATION_FIELD = 34
- NORMALIZED_TITLE = 16
- OWNER = 3
- SECTOR = 16
- SHORT_DESCRIPTION = 4
- TITLE_AR = 6

المجموع = **177**؛ المطابقة **PASSED**.

## آخر حالة حية

المزامنتان المجدولتان 389 و390 أنشأتا أربعة تعارضات حقل location_description بعد اللقطة الثابتة. كما جرى supersede للمراجعة المكررة 119 وربطها بالقضية 98 مع سجل تدقيق، دون تغيير بيانات العمل. لذلك أصبح العدد الحي النهائي 308، لا 305، وFIELD_CONFLICT أصبح 180.

التقسيم الحي: AREA=1, DURATION=93, FULL_DESCRIPTION=2, INVESTMENT_VALUE=2, LOCATION_FIELD=38, NORMALIZED_TITLE=16, OWNER=3, SECTOR=16, SHORT_DESCRIPTION=4, TITLE_AR=5.
المجموع = **180**؛ المطابقة **PASSED**. جمع الطوابير = 10 + 15 + 103 + 180 = **308**.

## تفاصيل السجلات الـ16

| Review ID | Master ID | SourceOpportunity ID | Reason key | Field | Status | Subcategory | Classification |
|---:|---:|---:|---|---|---|---|---|
| 233 | 163 | 2834 | `FIELD_CONFLICT:sector` | `sector` | OPEN | SECTOR | A: valid, reporting-only omission |
| 236 | 231 | 2866 | `FIELD_CONFLICT:sector` | `sector` | OPEN | SECTOR | A: valid, reporting-only omission |
| 239 | 248 | 2867 | `FIELD_CONFLICT:sector` | `sector` | OPEN | SECTOR | A: valid, reporting-only omission |
| 242 | 251 | 2868 | `FIELD_CONFLICT:sector` | `sector` | OPEN | SECTOR | A: valid, reporting-only omission |
| 245 | 258 | 2869 | `FIELD_CONFLICT:sector` | `sector` | OPEN | SECTOR | A: valid, reporting-only omission |
| 248 | 246 | 2870 | `FIELD_CONFLICT:sector` | `sector` | OPEN | SECTOR | A: valid, reporting-only omission |
| 251 | 242 | 2871 | `FIELD_CONFLICT:sector` | `sector` | OPEN | SECTOR | A: valid, reporting-only omission |
| 255 | 262 | 2875 | `FIELD_CONFLICT:sector` | `sector` | OPEN | SECTOR | A: valid, reporting-only omission |
| 261 | 260 | 2876 | `FIELD_CONFLICT:sector` | `sector` | OPEN | SECTOR | A: valid, reporting-only omission |
| 266 | 235 | 2878 | `FIELD_CONFLICT:sector` | `sector` | OPEN | SECTOR | A: valid, reporting-only omission |
| 269 | 234 | 2837 | `FIELD_CONFLICT:sector` | `sector` | OPEN | SECTOR | A: valid, reporting-only omission |
| 272 | 237 | 2853 | `FIELD_CONFLICT:sector` | `sector` | OPEN | SECTOR | A: valid, reporting-only omission |
| 275 | 239 | 2848 | `FIELD_CONFLICT:sector` | `sector` | OPEN | SECTOR | A: valid, reporting-only omission |
| 278 | 240 | 2844 | `FIELD_CONFLICT:sector` | `sector` | OPEN | SECTOR | A: valid, reporting-only omission |
| 281 | 241 | 2845 | `FIELD_CONFLICT:sector` | `sector` | OPEN | SECTOR | A: valid, reporting-only omission |
| 284 | 253 | 2862 | `FIELD_CONFLICT:sector` | `sector` | OPEN | SECTOR | A: valid, reporting-only omission |

لا تغييرات على الـ16: لا تعديل حالة، ولا قيمة Master، ولا سجل مصدر خام.

تفاصيل سجلات FIELD_CONFLICT الحية الـ180، ومعرّفاتها وحقولها ومصادرها، محفوظة في JSON المرفق.


إعادة المطابقة الحية عند 2026-10-20 16:14:19 (+03) أكدت بقاء الأعداد 308/180. أضافت المزامنة المجدولة لـFuras (المهمة 390) طبيعيًا 13 ملاحظة (11584→11597؛ IDs 11585–11597)؛ لم تبدأ مزامنة يدوية.
