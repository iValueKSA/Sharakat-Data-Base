# إعادة تحقق تشغيلية: نموذج الاستثمار

**وقت التحقق:** 2026-10-19 07:56:33 UTC  
**النطاق:** تحقق قبول للبعد الحالي، دون مزامنة أو كتابة لقاعدة بيانات المنصة.

## النتيجة

قيم نموذج الاستثمار المنشورة ما زالت متصالحة مع القائمة ولوحة البيانات والتصدير:

| الهوية المعيارية | الاسم | عداد المرشح | نتائج API | CSV | XLSX |
|---|---|---:|---:|---:|---:|
| `investment_model:lease` | التأجير | 4 | 4 | 4 | 4 |
| `investment_model:eomt` | التجهيز والتشغيل والصيانة والنقل | 1 | 1 | 1 | 1 |
| `investment_model:missing` | غير محدد | 286 | 286 | 286 | 286 |

إجمالي Masters المؤهلة 291؛ التغطية المعيارية 5، وغير المحدد 286، ومراجعتا نموذج الاستثمار تظلان ضمن غير المحدد. اختبار المتصفح أكد RTL وعدم وجود تمرير أفقي عند 1920×1080، وظهور اسم التأجير المعياري في التفاصيل، وعمل إعادة الضبط.

اللقطة ونتيجة التحقق الآلي محفوظتان في `screenshots/investment-model-lease-filter.png` و`screenshots/investment-model-ui-verification.json`.

## تحقق الشيفرة الحالية

أُجري الاختبار الكامل على ملفات المشروع للقراءة فقط، باستخدام صورة التطبيق لبيئة الاعتماديات وبقاعدة SQLite مؤقتة داخل الحاوية:

```text
137 passed, 1 existing Starlette/httpx deprecation warning
```

أُصلحت أثناء ذلك مطابقة تصدير XLSX لعمود «نوع الأصل أو الموقع» المضاف محليًا: نطاق الجدول والطباعة أصبح `A:X`، وعرض العمود ومحاذاته محددان. حُدثت توقعات الاختبار لإصدار المحرك 16 وعدد أعمدة التصدير 24.

## مانع بوابة الاكتمال

الشيفرة الحالية في مساحة المشروع تستخدم `STANDARDIZATION_VERSION = 16`. لكن الفحص المباشر للحاويات القائمة أظهر أن API وWorker العاملين يستوردان `STANDARDIZATION_VERSION = 12`. اختبارات الشيفرة الحالية وتحقيق API/UI القراءة فقط نجحت، لكن عامل الاستيعاب المنشور لا يستخدم إصدار الشيفرة الحالي. لذلك لا يمكن تأكيد شرط التطبيق المستقبلي على المحرك الحالي المنشور أو إعلان بوابة القبول النهائية حتى تتطابق خدمة API وWorker مع نسخة المشروع.

لم تُبنَ أو تُستبدل أي حاوية في هذا التحقق؛ ملف الطلب المرفق يطلب عدم إعادة بناء النظام. ولم تُنفذ مزامنة أو تغييرات في الأعمال أو مصادرها.

```ini
INVESTMENT_MODEL_IS_SINGLE_VALUED = TRUE
TOTAL_ELIGIBLE_MASTERS = 291
MASTERS_WITH_CANONICAL_INVESTMENT_MODEL = 5
MASTERS_WITH_UNSPECIFIED_INVESTMENT_MODEL = 286
MASTERS_REQUIRING_INVESTMENT_MODEL_REVIEW = 2
SUM_OF_CANONICAL_INVESTMENT_MODEL_BUCKETS = 291
INVESTMENT_MODEL_OPTION_COUNTS_MATCH_QUERY_COUNTS = TRUE
FULL_REGRESSION_SUITE = PASSED
BROWSER_UI_VERIFICATION = PASSED
WORKSPACE_STANDARDIZATION_ENGINE_VERSION = 16
RUNNING_API_STANDARDIZATION_ENGINE_VERSION = 12
RUNNING_WORKER_STANDARDIZATION_ENGINE_VERSION = 12
INVESTMENT_MODEL_TAXONOMY_DEEP_REVIEW_COMPLETE = FALSE
INVESTMENT_MODEL_TAXONOMY_DEEP_REVIEW_NOT_COMPLETE = TRUE
```
