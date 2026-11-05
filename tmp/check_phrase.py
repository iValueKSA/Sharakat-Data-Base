from app.standardization import comparison_key
for a,b in [('الإرشاد والتوجيه المهني','الخدمات الرقمية للإرشاد والتوجيه المهني'),('خدمات رقمية للإرشاد والتوجيه المهني','الخدمات الرقمية للإرشاد والتوجيه المهني'),('الأنشطة التجارية','إنشاء وتشغيل وصيانة مستودع - الأنشطة التجارية - مستودع')]:
 print(repr(comparison_key(a)),repr(comparison_key(b)),comparison_key(a) in comparison_key(b))
