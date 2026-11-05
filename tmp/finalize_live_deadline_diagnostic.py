import json
from pathlib import Path
p=Path('docs/validation/data/deadlines-30day-label-color/live-route-diagnostic.json')
d=json.loads(p.read_text(encoding='utf-8'))
d['initial_live_dom']['dashboard_visible']=True
d['initial_live_dom']['view_class']='page-view dashboard-rebuild visible'
d['initial_live_dom']['view_computed_visibility']={'display':'block','visibility':'visible','opacity':'1'}
d['previous_change_not_visible_root_cause']='OLD_STATIC_BUILD_STILL_SERVED was reproduced during the first deployment attempt: Compose built alahsa-production-reference-frontend under its implicit project name and failed network creation, leaving alahsa-local-frontend unchanged at that step. The explicit alahsa-local deployment subsequently recreated the local static frontend. Current live browser DOM and versioned assets now contain the labels and four distinct bar colors. The pasted request contains no screenshot timestamp or browser-session metadata, so whether the supplied screenshot came from the pre-deployment window or a stale tab cannot be independently proven.'
d['current_live_failure_reproduced']=False
d['current_live_screen_proof']='live-dashboard-screenshots/live-card-1440x900.png and live-card-390x844.png show all four labels and colors.'
p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
res=d['initial_live_dom'];view=d['viewports']; colors=[x['hex'] for x in res['bars']]; labels=[x['label'] for x in res['bars']]
lines='\n'.join(f"| {v['width']}×{v['height']} | 4 | 4 | 4 | لا | لا | لا |" for v in view)
report=f'''# مراجعة البطاقة الحية — مواعيد خلال 30 يوماً

**الحالة: COMPLETE.** جرى فتح المسار الحقيقي `http://localhost:8080/?view=data-dashboard` في المتصفح وفحص DOM والأنماط المحسوبة والموارد التي خدمها Nginx. البطاقة الحالية تحتوي التسميات الأربع وتستخدم أربعة ألوان مميزة بالفعل؛ لم تكن هناك حاجة إلى تعديل تطبيق إضافي في جولة التشخيص هذه.

## تحديد المكوّن الحي

- المسار: `http://localhost:8080/?view=data-dashboard` (الواجهة عند الجذر ثم عرض `#view-data-dashboard`).
- مكوّن العرض: `section#view-data-dashboard.page-view.dashboard-rebuild`.
- البطاقة: `article.rd-card.rd-metric-card` التي تحتوي `#rdDeadlineBuckets`، والعنوان «مواعيد خلال 30 يوماً».
- HTML: `app/static/index.html`، السطر 126.
- دالة بناء الأشرطة: `renderSparkMetrics` في `app/static/data-dashboard.js`، السطر 191؛ إنشاء كل فئة عند السطر 204.
- CSS: `app/static/data-dashboard.css`، قواعد `.rd-deadline-bucket` و`.rd-deadline-bar`.
- البحث في ملفات `app`, `deploy`, و`tests` وجد عقدة markup واحدة ودالة عرض واحدة؛ لا توجد بطاقة ثانية بنفس `rdDeadlineBuckets`.

## سبب عدم ظهور التغيير سابقًا

السبب المثبت في سجل التشغيل هو **`OLD_STATIC_BUILD_STILL_SERVED` أثناء محاولة النشر الأولى**: استعمل Compose اسم مشروعه الافتراضي، فبنى صورة `alahsa-production-reference-frontend` ثم فشل إنشاء الشبكة المتداخلة، ولم يستبدل حينها حاوية `alahsa-local-frontend`. نُفذ بعد ذلك النشر الصحيح باسم المشروع `alahsa-local` وأُعيد إنشاء حاوية الواجهة المحلية. المتصفح الحي الآن يحمّل ملفات العرض المحدّثة.

نص الطلب المرفق لا يحتوي ملف الصورة نفسه ولا بيانات وقت/جلسة التقاطها؛ لذلك لا يمكن إثبات ما إذا كانت الصورة الموصوفة قد التقطت قبل النشر الصحيح أو من تبويب قديم. فحص المتصفح الحي الحالي لا يعيد إنتاج المشكلة.

## القراءة الحية من DOM والأنماط المحسوبة

| العمود | مفتاح DOM | النص المرئي في DOM | لون خلفية الشريط المحسوب |
|---:|---|---|---|
| 1 | `7d` | {labels[0]} | {colors[0]} |
| 2 | `8_14d` | {labels[1]} | {colors[1]} |
| 3 | `15_30d` | {labels[2]} | {colors[2]} |
| 4 | `over_30d` | {labels[3]} | {colors[3]} |

قيمة KPI الحالية **60**. القيم الحية للأعمدة قبل/بعد التغيير السابق: **[0, 10, 50, 44]** و**[0, 10, 50, 44]**. كل عنصر DOM يجمع اسم الفئة والشريط والقيمة عبر `title` و`aria-label`؛ أمثلة القيم الحية: `خلال 7 أيام: 0 فرصة` و`15–30 يومًا: 50 فرصة`.

## الملفات التي يستخدمها المتصفح

- CSS المحمّل: `/static/data-dashboard.css?v=8`, HTTP 200, SHA-256 `{d['assets']['loaded'][0]['sha256']}`.
- JS المحمّل: `/static/data-dashboard.js?v=sector-distribution-v14`, HTTP 200, SHA-256 `{d['assets']['loaded'][1]['sha256']}`.
- تطابق SHA-256 للملفين المخدومين مع ملفات المصدر المحلية: **TRUE**.
- صورة الواجهة المحلية الحالية: `alahsa-local-frontend`، image ID `sha256:4f1f12553ae0320eda4128e1da65bd1be004879523033507f96b5552a952a3fd`.

## التحقق من المسار الحقيقي عبر Playwright

| حجم الشاشة | أشرطة مرئية | تسميات مرئية | ألوان مميزة | تداخل | قص | تمرير أفقي |
|---:|---:|---:|---:|:---:|:---:|:---:|
{lines}

لا أخطاء JavaScript ولا HTTP 5xx. لقطات البطاقة الحية الكاملة موجودة عند المقاسات الخمسة. تمت معاينة لقطتي 1440×900 و390×844، وكلتاهما تعرض التسميات الأربعة والألوان المطلوبة.

- [لقطة البطاقة الحية 1440×900](live-dashboard-screenshots/live-card-1440x900.png)
- [لقطة البطاقة الحية 390×844](live-dashboard-screenshots/live-card-390x844.png)
- [كل تفاصيل تشخيص DOM والموارد والقياسات](live-route-diagnostic.json)
- [قيم البطاقة قبل التغيير وبعده](card-values-before.json)، [بعد التغيير](card-values-after.json)

## السلامة

لم يحدث تعديل جديد على ملفات التطبيق خلال تشخيص هذه الجولة. بيانات الأعمال والمصادر لم تتغير، ومنطق المواعيد كما هو، ولم تتغير أي بطاقة أو لوحة أخرى، ولم تبدأ مزامنة يدوية. مهمتا المجدول الطبيعيّتان 511 و512 اكتملتا دون سجلات جديدة أو تحديثات.

```ini
LIVE_DEADLINES_CARD_FIX = COMPLETE
PREVIOUS_CHANGE_NOT_VISIBLE_ROOT_CAUSE = OLD_STATIC_BUILD_STILL_SERVED_DURING_FAILED_INITIAL_DEPLOY
LIVE_BROWSER_USES_UPDATED_ASSET = TRUE
SCREENSHOT_SHOWS_4_LABELS = TRUE
SCREENSHOT_SHOWS_4_DISTINCT_COLORS = TRUE
VALUES_CHANGED = FALSE
DEADLINE_LOGIC_CHANGED = FALSE
PLAYWRIGHT_TARGET = LIVE_DASHBOARD
PLAYWRIGHT_1920x1080 = PASSED
PLAYWRIGHT_1440x900 = PASSED
PLAYWRIGHT_1366x768 = PASSED
PLAYWRIGHT_768x900 = PASSED
PLAYWRIGHT_390x844 = PASSED
LABEL_OVERLAP = FALSE
LABEL_CLIPPING = FALSE
HORIZONTAL_OVERFLOW = FALSE
JAVASCRIPT_ERRORS = 0
BUSINESS_DATA_CHANGES = 0
SOURCE_DATA_CHANGES = 0
OTHER_DASHBOARD_COMPONENTS_CHANGED = FALSE
MANUAL_SOURCE_SYNC_STARTED = FALSE
```
'''
(p.parent/'FINAL-REVIEW.md').write_text(report,encoding='utf-8')
print('Updated diagnostic record and final report.')
