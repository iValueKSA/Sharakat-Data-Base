"""AHDA-branded Excel presentation for the existing opportunity export."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from .source_links import resolve_preferred_source_link

from openpyxl import Workbook
from openpyxl.drawing.image import Image
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet


AHDA_TZ = ZoneInfo("Asia/Amman")
BRAND = {
    "depth": "124E5C",
    "bisht": "C39853",
    "sea": "378AA4",
    "lomy": "58A645",
    "oisis": "006E61",
    "jass": "D1CBBD",
    "red_rice": "AC1F25",
    "red_bread": "80192E",
    "tbina": "989899",
    "paper": "FFFFFF",
    "canvas": "F7F8F7",
    "green_tint": "E8F2E5",
    "red_tint": "F8E9E9",
    "gold_tint": "F5EFE4",
    "sea_tint": "E8F2F5",
    "neutral_tint": "F0EFEC",
}

HEADERS = [
    "اسم الفرصة", "الجهة المالكة", "القطاع", "النشاط", "النشاط الفرعي", "القطاع الفرعي", "نوع الفرصة",
    "المدينة", "الحي / الموقع", "المواقع التفصيلية", "مرحلة المشروع",
    "نموذج الاستثمار", "المساحة (م²)", "القيمة الاستثمارية", "العملة", "مدة العقد (سنة)",
    "تاريخ النشر", "آخر موعد للتقديم", "الحالة", "الرقم المرجعي الرسمي", "معرّفات المصدر التقنية",
    "المصدر الرئيسي", "عدد المصادر", "المصادر", "رابط الفرصة", "نوع الأصل أو الموقع",
    "الدولة", "المنطقة", "المحافظة", "المدينة / الموقع", "الحي", "حالة الموقع الجغرافي",
]

MAIN_WIDTHS = [42, 27, 20, 24, 22, 22, 22, 16, 24, 36, 20, 22, 17, 20, 12, 16, 16, 19, 17, 23, 34, 26, 14, 30, 34, 24, 24, 22, 20, 24, 24, 25]
TEXT_COLUMNS = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 14, 18, 19, 20, 21, 23, 24, 25, 26, 27, 28, 29, 30, 31}
DATE_COLUMNS = {16, 17}
NUMBER_FORMATS = {
    12: '#,##0.## "م²"',
    13: '#,##0.##',
    15: '#,##0.## "سنة"',
    22: "0",
}
LOGO_PATH = Path(__file__).parent / "static" / "brand" / "ahda-logo-primary-excel.png"


def export_timestamp() -> datetime:
    return datetime.now(AHDA_TZ)


def _excel_date(value):
    """Convert ISO date/date-time strings to native Excel date values."""
    if not isinstance(value, str) or not value.strip():
        return value
    raw = value.strip()
    try:
        if "T" in raw or " " in raw:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=None)
        return date.fromisoformat(raw)
    except ValueError:
        return value


def _is_web_url(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value.strip())
        return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False


def _add_logo(sheet: Worksheet, anchor: str) -> None:
    if not LOGO_PATH.exists():
        return
    logo = Image(str(LOGO_PATH))
    aspect_ratio = logo.height / logo.width
    logo.width = 150
    logo.height = round(150 * aspect_ratio)
    sheet.add_image(logo, anchor)


def _apply_style(cell, style) -> None:
    if isinstance(style, Font):
        cell.font = style
        return
    cell.font, cell.fill, cell.alignment = style[:3]
    if len(style) > 3:
        cell.border = style[3]


def _style_title_block(sheet: Worksheet, exported_at: datetime, count: int) -> None:
    _add_logo(sheet, "A1")
    sheet["E1"] = "تقرير الفرص الاستثمارية في الأحساء"
    _apply_style(sheet["E1"], TITLE_STYLE)
    sheet["E2"] = "هيئة تطوير الأحساء"
    _apply_style(sheet["E2"], SUBTITLE_STYLE)
    sheet["E3"] = "قاعدة الفرص الاستثمارية الموحدة — بيانات منشورة من المصادر الرسمية"
    _apply_style(sheet["E3"], DESCRIPTION_STYLE)
    sheet["E4"] = "تاريخ التصدير"
    _apply_style(sheet["E4"], META_LABEL_STYLE)
    sheet["F4"] = exported_at.replace(tzinfo=None)
    _apply_style(sheet["F4"], META_VALUE_STYLE)
    sheet["F4"].number_format = "dd/mm/yyyy hh:mm"
    sheet["H4"] = "عدد الفرص"
    _apply_style(sheet["H4"], META_LABEL_STYLE)
    sheet["I4"] = count
    _apply_style(sheet["I4"], META_VALUE_STYLE)
    sheet["I4"].number_format = "#,##0"
    sheet["K4"] = "النطاق"
    _apply_style(sheet["K4"], META_LABEL_STYLE)
    sheet["L4"] = "جميع الفرص الرئيسية غير المدمجة"
    _apply_style(sheet["L4"], META_VALUE_STYLE)
    sheet["L4"].alignment = Alignment(horizontal="right", vertical="center", wrap_text=True, readingOrder=2)
    for row, height in {1: 32, 2: 23, 3: 22, 4: 28, 5: 8}.items():
        sheet.row_dimensions[row].height = height
    for col in range(1, len(HEADERS) + 1):
        sheet.cell(5, col).border = GOLD_RULE


def _style_metadata_sheet(sheet: Worksheet, exported_at: datetime, count: int) -> None:
    sheet.sheet_view.rightToLeft = True
    sheet.sheet_view.showGridLines = False
    sheet.sheet_properties.tabColor = BRAND["bisht"]
    sheet.column_dimensions["A"].width = 32
    sheet.column_dimensions["B"].width = 78
    sheet.column_dimensions["C"].width = 24
    _add_logo(sheet, "A1")
    sheet["D1"] = "معلومات التقرير"
    sheet["D1"]._style = TITLE_STYLE
    sheet["D2"] = "هيئة تطوير الأحساء"
    sheet["D2"]._style = SUBTITLE_STYLE
    for row, height in {1: 34, 2: 24, 3: 12, 4: 8}.items():
        sheet.row_dimensions[row].height = height

    sections = [
        (5, "معلومات عامة"),
        (10, "عوامل التصفية المطبقة"),
        (14, "ملاحظات التقرير"),
    ]
    for row, title in sections:
        _apply_style(sheet.cell(row, 1, title), (SECTION_STYLE, PatternFill("solid", fgColor=BRAND["depth"]), Alignment(horizontal="right", vertical="center", readingOrder=2), Border(bottom=GOLD_MEDIUM)))
        sheet.row_dimensions[row].height = 24

    pairs = [
        (6, "اسم التقرير", "تقرير الفرص الاستثمارية في الأحساء"),
        (7, "تاريخ التصدير", exported_at.replace(tzinfo=None)),
        (8, "عدد الفرص", count),
        (9, "المستخدم", "غير معروض حفاظًا على الخصوصية"),
        (11, "النطاق", "جميع الفرص الرئيسية غير المدمجة"),
        (12, "عوامل تصفية البحث", "لا يمرر مسار التصدير الحالي مرشحات واجهة البحث"),
        (13, "الحالة / القطاع / المصدر / الموقع", "الكل"),
        (15, "تعريف العدد", "إجمالي الفرص هو عدد الفرص الرئيسية غير المدمجة في هذا الملف."),
        (16, "المصدر", "تم تجميع الفرص من مصادر رسمية؛ يُرجى فتح الرابط الرسمي للتحقق من أحدث تفاصيل كل فرصة."),
        (17, "تنبيه الخط", "يعتمد عرض Ahda Text على توفر الخط في الجهاز الذي يفتح المصنف؛ قد يستخدم Excel خطًا بديلًا عند غيابه."),
    ]
    for row, label, value in pairs:
        _apply_style(sheet.cell(row, 1, label), META_LABEL_STYLE)
        cell = sheet.cell(row, 2, value)
        _apply_style(cell, META_VALUE_STYLE)
        if row == 7:
            cell.number_format = "dd/mm/yyyy hh:mm"
        elif row == 8:
            cell.number_format = "#,##0"
        cell.alignment = Alignment(horizontal="right", vertical="center", wrap_text=True, readingOrder=2)
        sheet.row_dimensions[row].height = 30 if row in {12, 15, 16, 17} else 24
    sheet.freeze_panes = "A5"
    sheet.print_area = "A1:B17"
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 1
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_margins.left = 0.3
    sheet.page_margins.right = 0.3
    sheet.page_margins.top = 0.45
    sheet.page_margins.bottom = 0.45
    sheet.oddFooter.left.text = "هيئة تطوير الأحساء"
    sheet.oddFooter.right.text = "&P من &N"


def build_opportunities_workbook(
    opportunities: Iterable,
    source_fact_summary: Callable,
    spreadsheet_safe: Callable,
    exported_at: datetime | None = None,
    canonicalize: Callable | None = None,
    geography_for: Callable | None = None,
) -> Workbook:
    """Build a styled workbook with distinct Sector and Activity columns."""
    exported_at = exported_at or export_timestamp()
    records = list(opportunities)
    canonicalize = canonicalize or (lambda dimension, value: value)
    if geography_for is None:
        from .geography import resolve_master_geography
        geography_for = lambda opportunity: resolve_master_geography(getattr(opportunity, "city", None), getattr(opportunity, "district", None))
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "الفرص الاستثمارية"
    sheet.sheet_view.rightToLeft = True
    sheet.sheet_view.showGridLines = False
    sheet.sheet_properties.tabColor = BRAND["depth"]
    sheet.freeze_panes = "A7"
    sheet.sheet_view.zoomScale = 85
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.page_margins.left = 0.25
    sheet.page_margins.right = 0.25
    sheet.page_margins.top = 0.45
    sheet.page_margins.bottom = 0.45
    sheet.page_margins.header = 0.2
    sheet.page_margins.footer = 0.2
    sheet.oddFooter.left.text = "هيئة تطوير الأحساء"
    sheet.oddFooter.right.text = "صفحة &P من &N"
    sheet.print_title_rows = "6:6"

    for column, width in enumerate(MAIN_WIDTHS, start=1):
        sheet.column_dimensions[get_column_letter(column)].width = width
    _style_title_block(sheet, exported_at, len(records))

    for column, header in enumerate(HEADERS, start=1):
        cell = sheet.cell(6, column, header)
        _apply_style(cell, TABLE_HEADER_STYLE)
    sheet.row_dimensions[6].height = 30

    for row_index, opportunity in enumerate(records, start=7):
        details = source_fact_summary(opportunity)
        geography = geography_for(opportunity) or {}
        confirmed_location = bool(geography.get("confirmed"))
        values = [
            opportunity.title_ar,
            canonicalize("owner", opportunity.opportunity_owner),
            canonicalize("sector", opportunity.sector),
            canonicalize("activity", getattr(opportunity, "activity", None)),
            canonicalize("sub_activity", getattr(opportunity, "sub_activity", None)),
            opportunity.subsector,
            canonicalize("opportunity_type", opportunity.opportunity_type),
            canonicalize("location", opportunity.city) if confirmed_location else ("قيد المراجعة" if geography.get("review_required") else "غير محدد"),
            opportunity.location_description if confirmed_location else None,
            details["locations"],
            details["stages"],
            canonicalize("investment_model", getattr(opportunity, "investment_model", None)),
            opportunity.land_area_sqm,
            opportunity.investment_value,
            opportunity.currency if opportunity.investment_value is not None else None,
            opportunity.contract_duration_years,
            _excel_date(opportunity.publication_date),
            _excel_date(opportunity.submission_deadline),
            canonicalize("status", opportunity.status),
            str(opportunity.reference_number) if opportunity.reference_number is not None else None,
            " | ".join(
                record.source_opportunity_id
                if ":" in record.source_opportunity_id
                else f"{record.source.source_key}:{record.source_opportunity_id}"
                for record in opportunity.source_records
            ),
            canonicalize("publication_platform", opportunity.primary_publication_platform),
            len(opportunity.source_records),
            " | ".join(record.source.source_name_ar for record in opportunity.source_records),
                resolve_preferred_source_link(opportunity.source_records).get("url") or "",
            " | ".join(sorted({item.asset_type.label_ar for item in getattr(opportunity, "asset_facility_type_assignments", []) if item.asset_type and item.asset_type.active}, key=lambda value: (value,))) or "غير محدد",
            geography.get("country"), geography.get("region"), geography.get("governorate"),
            geography.get("display_location") or geography.get("locality") or geography.get("governorate") or "غير محدد",
            geography.get("district"), geography.get("status_ar") or geography.get("status"),
        ]
        for column, raw_value in enumerate(values, start=1):
            value = spreadsheet_safe(raw_value)
            cell = sheet.cell(row_index, column, value)
            _apply_style(cell, DATA_EVEN_STYLE if row_index % 2 == 0 else DATA_ODD_STYLE)
            cell.alignment = TEXT_ALIGNMENT if column - 1 in TEXT_COLUMNS else NUMERIC_ALIGNMENT
            if column - 1 in DATE_COLUMNS:
                cell.number_format = "dd/mm/yyyy hh:mm" if isinstance(value, datetime) else "dd/mm/yyyy"
            elif column - 1 in NUMBER_FORMATS and value is not None:
                cell.number_format = NUMBER_FORMATS[column - 1]
            elif column == 20:
                cell.number_format = "@"
            if column == 1:
                cell.font = DATA_TITLE_FONT
            if column in {1, 2, 4, 8, 9, 23, 24, 25}:
                cell.alignment = WRAPPED_TEXT_ALIGNMENT
            if column == 25 and _is_web_url(raw_value):
                cell.hyperlink = raw_value.strip()
                cell.font = HYPERLINK_FONT
        sheet.row_dimensions[row_index].height = 34

    last_row = max(6, 6 + len(records))
    sheet.auto_filter.ref = f"A6:AF{last_row}"
    sheet.print_area = f"A1:X{last_row}"
    if not records:
        sheet["A7"] = "لا توجد فرص مطابقة لعوامل التصفية المحددة."
        _apply_style(sheet["A7"], EMPTY_STYLE)
        sheet.row_dimensions[7].height = 26
        sheet.print_area = "A1:X7"
    if records:
        for formula, fill, font_color in STATUS_RULES:
            sheet.conditional_formatting.add(
                f"S7:S{last_row}",
                FormulaRule(formula=[formula], fill=PatternFill("solid", fgColor=fill), font=Font(name="Ahda Text", color=font_color, bold=True)),
            )
        for formula, fill, font_color in DEADLINE_RULES:
            sheet.conditional_formatting.add(
                f"O7:O{last_row}",
                FormulaRule(formula=[formula], fill=PatternFill("solid", fgColor=fill), font=Font(name="Ahda Text", color=font_color, bold=True)),
            )

    metadata = workbook.create_sheet("معلومات التقرير")
    _style_metadata_sheet(metadata, exported_at, len(records))
    workbook.active = 0
    workbook.properties.title = "تقرير الفرص الاستثمارية في الأحساء"
    workbook.properties.subject = "تصدير بيانات الفرص الاستثمارية"
    workbook.properties.creator = "هيئة تطوير الأحساء"
    return workbook


THIN_JASS = Side(style="thin", color=BRAND["jass"])
GOLD_MEDIUM = Side(style="medium", color=BRAND["bisht"])
GOLD_RULE = Border(bottom=Side(style="thin", color=BRAND["bisht"]))
TITLE_STYLE = Font(name="Ahda Text", size=20, bold=True, color=BRAND["depth"])
SUBTITLE_STYLE = Font(name="Ahda Text", size=12, color=BRAND["depth"])
DESCRIPTION_STYLE = Font(name="Ahda Text", size=10, color="66757A")
META_LABEL_STYLE = Font(name="Ahda Text", size=10, bold=True, color=BRAND["depth"])
META_VALUE_STYLE = Font(name="Ahda Text", size=10, color=BRAND["depth"])
SECTION_STYLE = Font(name="Ahda Text", size=12, bold=True, color="FFFFFF")
TABLE_HEADER_STYLE = (
    Font(name="Ahda Text", size=10, bold=True, color="FFFFFF"),
    PatternFill("solid", fgColor=BRAND["depth"]),
    Alignment(horizontal="center", vertical="center", wrap_text=True, readingOrder=2),
    Border(bottom=GOLD_MEDIUM),
)
DATA_ODD_STYLE = (
    Font(name="Ahda Text", size=9, color=BRAND["depth"]),
    PatternFill("solid", fgColor=BRAND["paper"]),
    Alignment(vertical="center", readingOrder=2),
    Border(bottom=THIN_JASS),
)
DATA_EVEN_STYLE = (
    Font(name="Ahda Text", size=9, color=BRAND["depth"]),
    PatternFill("solid", fgColor=BRAND["canvas"]),
    Alignment(vertical="center", readingOrder=2),
    Border(bottom=THIN_JASS),
)
DATA_TITLE_FONT = Font(name="Ahda Text", size=9, bold=True, color=BRAND["depth"])
HYPERLINK_FONT = Font(name="Ahda Text", size=9, color=BRAND["sea"], underline="single")
TEXT_ALIGNMENT = Alignment(horizontal="right", vertical="center", readingOrder=2)
NUMERIC_ALIGNMENT = Alignment(horizontal="center", vertical="center")
WRAPPED_TEXT_ALIGNMENT = Alignment(horizontal="right", vertical="center", wrap_text=True, readingOrder=2)
EMPTY_STYLE = (
    Font(name="Ahda Text", size=11, color=BRAND["depth"], italic=True),
    PatternFill("solid", fgColor=BRAND["neutral_tint"]),
    Alignment(horizontal="right", vertical="center", readingOrder=2),
)
STATUS_RULES = [
    ('$S7="متاحة"', BRAND["green_tint"], BRAND["oisis"]),
    ('$S7="منشورة"', BRAND["green_tint"], BRAND["oisis"]),
    ('$S7="منتهية"', BRAND["red_tint"], BRAND["red_bread"]),
    ('$S7="Expired"', BRAND["red_tint"], BRAND["red_bread"]),
    ('$S7="أزيلت من المصدر"', BRAND["neutral_tint"], BRAND["tbina"]),
    ('$S7="REMOVED_FROM_SOURCE"', BRAND["neutral_tint"], BRAND["tbina"]),
    ('$S7="غير محددة"', BRAND["neutral_tint"], BRAND["tbina"]),
]
DEADLINE_RULES = [
    ('AND(ISNUMBER($R7),$R7>=TODAY(),$R7<=TODAY()+7,NOT(OR($S7="منتهية",$S7="أزيلت من المصدر",$S7="REMOVED_FROM_SOURCE")))', BRAND["red_tint"], BRAND["red_bread"]),
    ('AND(ISNUMBER($R7),$R7>TODAY()+7,$R7<=TODAY()+14,NOT(OR($S7="منتهية",$S7="أزيلت من المصدر",$S7="REMOVED_FROM_SOURCE")))', BRAND["gold_tint"], BRAND["depth"]),
    ('AND(ISNUMBER($R7),$R7>TODAY()+14,$R7<=TODAY()+30,NOT(OR($S7="منتهية",$S7="أزيلت من المصدر",$S7="REMOVED_FROM_SOURCE")))', BRAND["sea_tint"], BRAND["depth"]),
]
