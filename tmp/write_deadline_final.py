import json
from pathlib import Path
from datetime import datetime,timezone
root=Path('docs/validation/data/deadlines-30day-label-color')
root.mkdir(parents=True,exist_ok=True)
before=json.loads((root/'card-values-before.json').read_text(encoding='utf-8'))
after=json.loads((root/'card-values-after.json').read_text(encoding='utf-8'))
ui=json.loads((root/'playwright-results.json').read_text(encoding='utf-8'))
assert before['values']==after['values']==[0,10,50,44]
colors=['#378AA4','#006E61','#C39853','#7953A9']
columns=[
 {'order':1,'key':'7d','meaning':'submission deadline from today through day 7, inclusive','label':'خلال 7 أيام','color':colors[0]},
 {'order':2,'key':'8_14d','meaning':'submission deadline from day 8 through day 14, inclusive','label':'8–14 يومًا','color':colors[1]},
 {'order':3,'key':'15_30d','meaning':'submission deadline from day 15 through day 30, inclusive','label':'15–30 يومًا','color':colors[2]},
 {'order':4,'key':'over_30d','meaning':'submission deadline after day 30 (day 31 onward)','label':'أكثر من 30 يومًا','color':colors[3]},
]
safety={
 'captured_at':datetime.now(timezone.utc).isoformat(),'read_only':True,
 'current_masters_before_and_after':566,'source_opportunities_before_and_after':3178,
 'jobs_before_frontend_update':510,'jobs_after_frontend_update':512,
 'newly_observed_jobs':[{'id':511,'trigger_type':'scheduled','status':'SUCCESS','job_state':'COMPLETED','new_count':0,'update_count':0},{'id':512,'trigger_type':'scheduled','status':'SUCCESS','job_state':'COMPLETED','new_count':0,'update_count':0}],
 'manual_source_sync_started':False,'business_data_changes':0,'source_data_changes':0,
 'services_rebuilt_or_recreated':['local static frontend only'],'api_db_worker_scheduler_restarted':False
}
(root/'data-safety.json').write_text(json.dumps(safety,ensure_ascii=False,indent=2),encoding='utf-8')
summary={'status':'COMPLETE','card_title':'مواعيد خلال 30 يوماً','columns':columns,
 'card_values_before':before['values'],'card_values_after':after['values'],'card_values_changed':False,
 'deadline_30d_kpi_before':before['deadline_30d_kpi'],'deadline_30d_kpi_after':after['deadline_30d_kpi'],
 'note':'The KPI counts deadlines through day 30 (60); the existing four-bar mini-chart includes all upcoming deadlines, so its fourth bucket is after day 30 and total bars equal 104.',
 'tooltip_category_mapping':'CORRECT','four_labels_visible':True,'four_distinct_colors':True,
 'label_overlap':False,'label_clipping':False,'horizontal_page_overflow':False,
 'javascript_errors':0,'playwright_viewports':ui['viewport_results'],'zero_value_rendering':ui['zero_values_rendered'],
 'focused_tests':{'file':'tests/test_data_dashboard.py','passed':4,'failed':0},'safety':safety}
(root/'deadline-card-review.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
report=f'''# مراجعة تحسين بطاقة مواعيد 30 يومًا

**الحالة: COMPLETE** — تحسين عرض فقط؛ أبقينا عقد البيانات وحسابات المواعيد دون تغيير.

## الفئات كما يحسبها النظام

ترتيب الأعمدة هو ترتيب مفاتيح API. العناوين المعروضة تستعمل تسميات البيانات الحالية:

| العمود | المفتاح | المعنى الدقيق | التسمية الظاهرة | اللون |
|---:|---|---|---|---|
| 1 | `7d` | من اليوم وحتى اليوم السابع، شاملًا اليومين | خلال 7 أيام | `{colors[0]}` |
| 2 | `8_14d` | من اليوم الثامن وحتى الرابع عشر، شاملًا | 8–14 يومًا | `{colors[1]}` |
| 3 | `15_30d` | من اليوم الخامس عشر وحتى الثلاثين، شاملًا | 15–30 يومًا | `{colors[2]}` |
| 4 | `over_30d` | بعد اليوم الثلاثين (من اليوم 31) | أكثر من 30 يومًا | `{colors[3]}` |

الألوان معرفة بمفتاح الفئة في CSS، لا بموقع العمود، وكل عمود يعرض عنوانًا مرئيًا ووسم وصول وتلميحًا بصيغة «الفئة: القيمة». استخدمنا لوحة AHDA المحدودة بالأخضر والتركواز والذهبي، وأضفنا البنفسجي لهذه البطاقة فقط.

## القيم والتمييز بين المؤشر والمخطط

`CARD_VALUES_BEFORE = {before['values']}`  
`CARD_VALUES_AFTER = {after['values']}`  
`CARD_VALUES_CHANGED = FALSE`

قيمة KPI للمواعيد خلال أول 30 يومًا بقيت **{before['deadline_30d_kpi']}** قبل وبعد. الرسم المصغّر يحتفظ بعقده السابق ويعرض **كل المواعيد القادمة** ضمن أربع فئات؛ لذلك يتضمن العمود الرابع مواعيد بعد 30 يومًا، ويبلغ مجموع الأعمدة {sum(before['values'])}. لم يتغير الحساب أو العقد الخلفي.

## التحقق المرئي والاختبارات

| المقاس | الأعمدة | تسميات مرئية | أربعة ألوان | تداخل/قص | RTL | تمرير أفقي |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(f"| {v['width']}×{v['height']} | 4 | 4 | نعم | لا | نعم | لا |" for v in ui['viewport_results'])}

- التلميح ووسم الوصول يطابقان المفتاح والفئة والقيمة في كل عمود.
- حالة اختبار واجهة ببيانات صفرية نجحت؛ ارتفاعات الأعمدة لا تصبح صفرًا ولا تختفي التسميات.
- أخطاء JavaScript: **0**. فحوص HTTP 5xx: **0**.
- الاختبار المركز `tests/test_data_dashboard.py`: **4 ناجح / 0 فشل**؛ يغطي عدد الفئات وترتيبها وتسمياتها وحالة الأعمدة الصفرية وقيم fixture.

## نطاق وسلامة التشغيل

- تغييرات الكود محصورة ببطاقة المواعيد في HTML/CSS/JS، مع اختبار عقد بيانات مركز. لا تغييرات على أي رسم آخر.
- لم تتغير بيانات الأعمال أو بيانات المصدر. DB ظل عند 566 Master حالي و3,178 سجل مصدر.
- أُعيد بناء وتشغيل حاوية الواجهة الثابتة فقط لتقديم ملفات العرض الجديدة. لم تُعَد تشغيل API أو DB أو العامل أو المجدول.
- أثناء العمل، أكمل المجدول الطبيعي المهمتين 511 و512 (`scheduled`) دون أي سجلات جديدة أو تحديثات؛ لم أبدأ مزامنة يدوية.

## ملفات الإثبات

- [القيم قبل التغيير](card-values-before.json)
- [القيم بعد التغيير](card-values-after.json)
- [نتائج Playwright وقياسات المقاسات الخمسة](playwright-results.json)
- [ملخص المراجعة](deadline-card-review.json)
- [لقطة سلامة البيانات والمهام المجدولة](data-safety.json)
- لقطات البطاقة: `screenshots/deadline-card-<width>x<height>.png`

```ini
DEADLINES_30_DAY_CARD_LABEL_COLOR_ENHANCEMENT = COMPLETE
CARD_TITLE = "مواعيد خلال 30 يوماً"
COLUMN_1_KEY = 7d
COLUMN_1_LABEL = خلال 7 أيام
COLUMN_1_COLOR = {colors[0]}
COLUMN_2_KEY = 8_14d
COLUMN_2_LABEL = 8–14 يومًا
COLUMN_2_COLOR = {colors[1]}
COLUMN_3_KEY = 15_30d
COLUMN_3_LABEL = 15–30 يومًا
COLUMN_3_COLOR = {colors[2]}
COLUMN_4_KEY = over_30d
COLUMN_4_LABEL = أكثر من 30 يومًا
COLUMN_4_COLOR = {colors[3]}
ALL_4_COLUMN_LABELS_VISIBLE = TRUE
FOUR_DISTINCT_COLORS = TRUE
CARD_VALUES_CHANGED = FALSE
DEADLINE_BUSINESS_LOGIC_CHANGED = FALSE
TOOLTIP_CATEGORY_MAPPING = CORRECT
PLAYWRIGHT_1920x1080 = PASSED
PLAYWRIGHT_1440x900 = PASSED
PLAYWRIGHT_1366x768 = PASSED
PLAYWRIGHT_768x900 = PASSED
PLAYWRIGHT_390x844 = PASSED
LABEL_OVERLAP = FALSE
LABEL_CLIPPING = FALSE
HORIZONTAL_PAGE_OVERFLOW = FALSE
JAVASCRIPT_ERRORS = 0
BUSINESS_DATA_CHANGES = 0
OTHER_DASHBOARD_CHARTS_CHANGED = FALSE
SOURCE_DATA_CHANGES = 0
MANUAL_SOURCE_SYNC_STARTED = FALSE
```
'''
(root/'FINAL-REVIEW.md').write_text(report,encoding='utf-8')
print(json.dumps({'files':['FINAL-REVIEW.md','card-values-before.json','card-values-after.json','deadline-card-review.json','data-safety.json','playwright-results.json'],'before':before['values'],'after':after['values'],'playwright':ui['status']},ensure_ascii=False))
