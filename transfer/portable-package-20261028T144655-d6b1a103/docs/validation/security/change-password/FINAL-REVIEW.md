# مراجعة ميزة تغيير كلمة المرور

**الحالة: COMPLETE**. اكتملت الميزة والتحققات الأمنية والمرئية والانحدار، ثم أُغلق مانع حداثة MWAN المستقل. أعاد آخر فحص DQ حي كامل للقراءة فقط 129 بوابة: 125 `PASS` و4 `WARNING` و0 `FAIL`. تفاصيل المعالجة في [مراجعة MWAN TLS والحداثة](../data/mwan-tls-freshness-remediation/FINAL-REVIEW.md).

## التصميم المنفذ

- نموذج المستخدم: `app.models.User`، والهوية تؤخذ من الجلسة المصادق عليها فقط.
- التجزئة: دالتا `hash_password` و`verify_password` الحاليتان باستخدام scrypt؛ لا يوجد نظام تجزئة موازٍ.
- المصادقة: `POST /api/auth/login` و`GET /api/auth/me`، مع جلسات خادمية مبهمة في `user_sessions`.
- الكوكي: `alahsa_session`، HTTP-only وSameSite=Lax، وصلاحية 8 ساعات.
- التدقيق: خدمة `audit()` الحالية؛ سُجل `PASSWORD_CHANGED` أو `PASSWORD_CHANGE_FAILED` مع معرّف المستخدم والطلب وبيانات العميل، دون كلمة مرور أو تجزئة.
- الاستعادة الطارئة: بقي إجراء إعادة ضبط Admin المحلي المنفصل موثقًا في `docs/runbooks/local-windows.md`؛ لم يُحذف أو يُستعمل في هذا العمل.

واجهة **الحساب الشخصي → تغيير كلمة المرور** تستخدم حقول الحالية والجديدة والتأكيد، رسائل عربية، إظهار/إخفاء، تحققًا واجهيًا وخادميًا، وحالة حفظ تمنع الإرسال المكرر. السياسة متوافقة مع إنشاء المستخدم الحالي: 12–256 محرفًا؛ كما تُرفض كلمات المرور الشائعة والأنماط المتكررة/الترتيبية الواضحة دون قواعد تعقيد اعتباطية.

يقبل endpoint المستخدم النشط المصادق عليه ويغير كلمة مروره هو فقط. يرفض الحقول الإضافية التي يمكن أن تستهدف مستخدمًا آخر. بعد التحقق من الحالية، تُحدّث التجزئة وتُبطل الجلسات الأخرى ويُدوّر رمز الجلسة الحالية في معاملة واحدة. استُخدم محدد المحاولات Redis القائم بحد 8 محاولات خلال 300 ثانية مع نطاق endpoint والمستخدم. بقيت حماية CSRF الحالية: JSON، قائمة CORS ذات الأصول المحددة، وكوكي SameSite=Lax.

## نتائج التحقق

- الاختبارات المركزة: **5 ناجحة / 0 فشل**.
- الانحدار الكامل المعزول: **585 ناجحًا / 0 فشل**.
- Playwright على واجهة التشغيل الفعلية: قائمة الحساب والنموذج، رفض الحالية الخاطئة، منع عدم التطابق، تغيير فعلي ثم استعادة كلمة المرور السابقة، رفض القديمة وقبول الجديدة أثناء التغيير، والوصول إلى endpoint المسؤول. المقاسات الخمسة اجتازت RTL وظهور النموذج وعدم القص وعدم التمرير الأفقي.
- أخطاء JavaScript: **0**؛ HTTP 5xx: **0**. ظهر تحذيرا console من طلبَي HTTP 401 المتوقعين أثناء التحقق السلبي.
- فحص قاعدة الخدمة قبل وبعد: Master **587 → 587**؛ SourceOpportunity **3,178 → 3,178**؛ الملاحظات **26,894 → 26,894**؛ تعارضات المراجعة **1,114 → 1,114**؛ مراجعات الموقع **26 → 26**؛ مراجعات التأهيل **0 → 0**؛ سجلات الدمج **21 → 21**؛ المهام **538 → 538**، ولا مهام نشطة.
- فحص سجل التدقيق: حدثا `PASSWORD_CHANGED` وحدث `PASSWORD_CHANGE_FAILED` للتحقق الحي؛ بيانات الاعتماد والتجزئات غير موجودة في `before_json` أو `after_json` أو `request_metadata`.
- حساب `admin@local` بقي نشطًا وغير مقفل. استُعيدت كلمة المرور التي كانت سارية قبل اختبار Playwright، وتُركت جلسة الاختبار الحالية صالحة. لم تُكتب كلمة مرور الاختبار في التقرير أو السجل.
- الخدمات عادت إلى الجاهزية بعد بناء API والواجهة فقط. لم تُعد قاعدة البيانات أو Redis أو العامل أو المجدول.

## جودة البيانات الحية — الحالة السابقة قبل إغلاق مانع MWAN

أُجري تقييم كامل للقراءة فقط (`persist=false`): **129 بوابة؛ 125 PASS، 3 WARNING، 1 FAIL**. البوابة الفاشلة هي `SOURCE_LAST_SUCCESS_TOO_OLD` في `SOURCE_FRESHNESS`، والمصدر المتأثر `MWAN`. آخر مسح ناجح كان 2026-10-12، وتجاوز عمره حد الفشل البالغ 20,160 دقيقة. آخر محاولة فاشلة موثقة كانت Job 521 بتاريخ 2026-10-26، بسبب خطأ التحقق من شهادة TLS. هذا إخفاق تشغيل مصدر سابق ولا يتعلق بالمصادقة. لم أغير حداثة المصدر أو بياناته ولم أطلق مزامنة لمعالجته.

بعد إصلاح ثقة TLS الخاصة بمحول MWAN فقط، اكتمل Job 539 بنجاح وحدّث آخر تحقق كامل إلى 2026-10-27؛ أصبحت حداثة MWAN `FRESH` ولم يعد مصدرًا فاشلًا في بوابة الحداثة. التقييم الكامل اللاحق للقراءة فقط أعاد **129 بوابة؛ 125 PASS و4 WARNING و0 FAIL**. بقيت التحذيرات المقبولة منفصلة عن شرط الإقفال.

## الثوابت النهائية

```ini
IN_APP_CHANGE_PASSWORD = COMPLETE
CHANGE_PASSWORD_MENU_VISIBLE = TRUE
CURRENT_PASSWORD_REQUIRED = TRUE
CURRENT_PASSWORD_VERIFIED_SERVER_SIDE = TRUE
NEW_PASSWORD_CONFIRMATION_REQUIRED = TRUE
SAME_PASSWORD_REJECTED = TRUE
USER_CAN_CHANGE_ONLY_OWN_PASSWORD = TRUE
CROSS_USER_PASSWORD_CHANGE = FORBIDDEN
PLAINTEXT_PASSWORD_STORED = FALSE
PASSWORD_VALUE_IN_AUDIT = FALSE
OLD_CREDENTIAL_CANNOT_LOGIN = TRUE
NEW_CREDENTIAL_CAN_LOGIN = TRUE
PASSWORD_CHANGE_AUDIT_EVENT = TRUE
CHANGE_PASSWORD_ENDPOINT_RATE_LIMITED = TRUE
SESSION_FIXATION_AFTER_PASSWORD_CHANGE = FALSE
ADMIN_CHANGE_OWN_PASSWORD = PASSED
ANALYST_CHANGE_OWN_PASSWORD = PASSED
VIEWER_CHANGE_OWN_PASSWORD = PASSED
PLAYWRIGHT_1920x1080 = PASSED
PLAYWRIGHT_1440x900 = PASSED
PLAYWRIGHT_1366x768 = PASSED
PLAYWRIGHT_768x900 = PASSED
PLAYWRIGHT_390x844 = PASSED
RTL = PASSED
HORIZONTAL_OVERFLOW = FALSE
JAVASCRIPT_ERRORS = 0
FOCUSED_TESTS = 5 passed / 0 failed
FULL_REGRESSION_SUITE = 585 passed / 0 failed
LIVE_DQ_TOTAL = 129
LIVE_DQ_PASS = 125
LIVE_DQ_WARNING = 4
LIVE_DQ_FAIL = 0
MASTER_CHANGES = 0
SOURCE_OPPORTUNITY_CHANGES = 0
OBSERVATION_BUSINESS_CHANGES = 0
REVIEW_CHANGES = 0
MERGES = 0
MANUAL_SOURCE_SYNC_STARTED = FALSE
```
