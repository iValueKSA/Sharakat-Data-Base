from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from openpyxl import load_workbook

from app.excel_export import BRAND, HEADERS, build_opportunities_workbook, build_opportunities_workbook_write_only
from app.main import source_fact_summary, spreadsheet_safe


def _opportunity(**overrides):
    source = SimpleNamespace(source_name_ar="فرص الرسمية", source_url="https://official.example/opportunities/1", source_key="furas")
    source_record = SimpleNamespace(
        source=source,
        source_opportunity_id="furas:01-26-017001-41001",
        source_url=source.source_url,
        raw_data_json={"opportunity_locations": ["العيون"], "project_stage": "طرح", "investment_model": "تأجير"},
        opportunity_locations=[],
    )
    values = {
        "title_ar": "إنشاء وتشغيل مستودع بالقطعة رقم 1 في صناعية العيون",
        "opportunity_owner": "أمانة الأحساء",
        "sector": "صناعي",
        "subsector": "صناعات خفيفة",
        "opportunity_type": "فرصة تأجير",
        "city": "الأحساء",
        "location_description": "صناعية العيون",
        "land_area_sqm": 150000.5,
        "investment_value": 1250000.0,
        "currency": "USD",
        "contract_duration_years": 15.0,
        "publication_date": "2026-10-01",
        "submission_deadline": "2026-10-20",
        "status": "متاحة",
        "reference_number": "06-26-183737-49010",
        "primary_publication_platform": "بوابة فرص",
        "source_records": [source_record],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _build(records):
    return build_opportunities_workbook(
        records,
        source_fact_summary,
        spreadsheet_safe,
        datetime(2026, 10, 13, 15, 45, tzinfo=timezone.utc),
    )


def test_branded_workbook_preserves_dataset_and_excel_analysis_features():
    long_title = "فرصة استثمارية " + "مستودع الأحساء " * 20
    record = _opportunity(title_ar=long_title, reference_number="06-26-183737-49010")
    workbook = _build([record])
    output = BytesIO()
    workbook.save(output)
    reopened = load_workbook(BytesIO(output.getvalue()), data_only=False)

    assert reopened.sheetnames == ["الفرص الاستثمارية", "معلومات التقرير"]
    main = reopened["الفرص الاستثمارية"]
    metadata = reopened["معلومات التقرير"]
    assert main.sheet_view.rightToLeft is True
    assert metadata.sheet_view.rightToLeft is True
    assert main.freeze_panes == "A7"
    assert main.auto_filter.ref == "A6:AF7"
    assert main.max_column == 32
    assert main["E1"].value == "تقرير الفرص الاستثمارية في الأحساء"
    assert main["A6"].value == HEADERS[0]
    assert main["X6"].value == HEADERS[23]
    assert main["AF6"].value == HEADERS[-1]
    assert main["A7"].value == long_title
    assert main["A7"].alignment.wrap_text is True
    assert main["E1"].font.name == "Ahda Text"
    assert main["A6"].font.name == "Ahda Text"
    assert main["A6"].fill.fgColor.rgb.endswith(BRAND["depth"])
    assert main["A6"].border.bottom.color.rgb.endswith(BRAND["bisht"])
    assert len(main._images) == 1
    assert len(metadata._images) == 1
    assert main["Y7"].value == "https://official.example/opportunities/1"
    assert main["Y7"].hyperlink.target == main["Y7"].value
    assert main["Q7"].value.date().isoformat() == "2026-10-01"
    assert main["R7"].value.date().isoformat() == "2026-10-20"
    assert isinstance(main["M7"].value, (int, float))
    assert isinstance(main["N7"].value, (int, float))
    assert main["O7"].value == "USD"
    assert main["T7"].value == "06-26-183737-49010"
    assert main["T7"].number_format == "@"
    assert main["U7"].value == "furas:01-26-017001-41001"
    assert main["N7"].number_format == "#,##0.##"
    assert len(main.merged_cells.ranges) == 0
    assert main.print_title_rows == "$6:$6"
    assert main.page_setup.orientation == "landscape"
    assert main.page_setup.fitToWidth == 1
    assert metadata["B8"].value == 1
    assert metadata["B7"].value.isoformat() == "2026-10-13T15:45:00"
    assert len(main.conditional_formatting) == 2


def test_workbook_keeps_formula_injection_protection_and_unknown_dates_safe():
    record = _opportunity(
        title_ar="=HYPERLINK(\"https://evil.example\",\"افتح\")",
        reference_number="+000123",
        publication_date="تاريخ غير صالح",
        submission_deadline=None,
        status="غير محددة",
    )
    workbook = _build([record])
    main = workbook["الفرص الاستثمارية"]

    assert main["A7"].value.startswith("'=HYPERLINK")
    assert main["T7"].value == "'+000123"
    assert isinstance(main["Q7"].value, str)
    assert main["R7"].value is None
    assert main["Y7"].hyperlink.target == "https://official.example/opportunities/1"
    assert not main["A7"].hyperlink


def test_zero_result_export_is_valid_and_has_explanatory_message():
    workbook = _build([])
    output = BytesIO()
    workbook.save(output)
    reopened = load_workbook(BytesIO(output.getvalue()), data_only=False)
    main = reopened["الفرص الاستثمارية"]
    metadata = reopened["معلومات التقرير"]

    assert main.max_column == 32
    assert main.auto_filter.ref == "A6:AF6"
    assert main.freeze_panes == "A7"
    assert main["A7"].value == "لا توجد فرص مطابقة لعوامل التصفية المحددة."
    assert metadata["B8"].value == 0


def _color_contract(color):
    if color is None:
        return None
    color_type = color.type
    return color_type, getattr(color, color_type, None)


def _cell_contract(cell):
    return {
        "value": cell.value,
        "data_type": cell.data_type,
        "number_format": cell.number_format,
        "font": (cell.font.name, cell.font.sz, cell.font.bold, cell.font.italic,
                 _color_contract(cell.font.color), cell.font.underline),
        "fill": (cell.fill.fill_type, _color_contract(cell.fill.fgColor)),
        "alignment": (cell.alignment.horizontal, cell.alignment.vertical, cell.alignment.wrap_text,
                      cell.alignment.readingOrder),
        "bottom_border": (cell.border.bottom.style, _color_contract(cell.border.bottom.color)),
        "hyperlink": cell.hyperlink.target if cell.hyperlink else None,
    }


def _workbook_contract(workbook):
    result = {"sheetnames": workbook.sheetnames, "properties": (
        workbook.properties.title, workbook.properties.subject, workbook.properties.creator)}
    for sheet in workbook.worksheets:
        rows = sheet.max_row or 0
        columns = sheet.max_column or 0
        result[sheet.title] = {
            "dimensions": (rows, columns),
            "cells": [[_cell_contract(sheet.cell(row, column)) for column in range(1, columns + 1)]
                      for row in range(1, rows + 1)],
            "widths": {key: value.width for key, value in sheet.column_dimensions.items() if value.width},
            "heights": {key: value.height for key, value in sheet.row_dimensions.items() if value.height},
            "rtl": sheet.sheet_view.rightToLeft,
            "freeze": sheet.freeze_panes,
            "autofilter": sheet.auto_filter.ref,
            "print_area": str(sheet.print_area),
            "print_titles": str(sheet.print_title_rows),
            "orientation": sheet.page_setup.orientation,
            "fit_to_width": sheet.page_setup.fitToWidth,
            "images": [(image.width, image.height, image.anchor._from.col, image.anchor._from.row)
                       for image in sheet._images],
            "conditional_ranges": [str(item.sqref) for item in sheet.conditional_formatting],
            "conditional_rule_counts": [len(sheet.conditional_formatting[item])
                                         for item in sheet.conditional_formatting],
            "conditional_formulas": [[tuple(rule.formula or ()) for rule in sheet.conditional_formatting[item]]
                                     for item in sheet.conditional_formatting],
            "merged_ranges": sorted(str(item) for item in sheet.merged_cells.ranges),
            "paper_size": sheet.page_setup.paperSize,
            "fit_to_height": sheet.page_setup.fitToHeight,
            "margins": (sheet.page_margins.left, sheet.page_margins.right, sheet.page_margins.top,
                        sheet.page_margins.bottom, sheet.page_margins.header, sheet.page_margins.footer),
        }
    return result


def test_write_only_workbook_matches_reference_workbook_contract(tmp_path):
    record = _opportunity(publication_date="2026-10-01", submission_deadline="2026-10-20")
    even_record = _opportunity(title_ar="فرصة الصف الزوجي", reference_number="REF-2",
                               publication_date=None, submission_deadline=None)
    exported_at = datetime(2026, 10, 13, 15, 45, tzinfo=timezone.utc)
    reference = _build([record, even_record])
    reference["الفرص الاستثمارية"]["E1"].value = "تقرير الفرص الاستثمارية في الأحساء"
    reference["معلومات التقرير"]["B8"] = 2
    reference["معلومات التقرير"]["B11"] = "الفرص المطابقة للمرشحات المحددة"
    reference["معلومات التقرير"]["B12"] = "عبارة البحث: مستودع"
    reference_output = BytesIO()
    reference.save(reference_output)
    reference = load_workbook(BytesIO(reference_output.getvalue()), data_only=False)
    path = Path(tmp_path) / "write-only.xlsx"
    build_opportunities_workbook_write_only(
        path, [record, even_record], 2, source_fact_summary, spreadsheet_safe, exported_at,
        applied_filters_text="عبارة البحث: مستودع")
    optimized = load_workbook(path, data_only=False)

    assert _workbook_contract(optimized) == _workbook_contract(reference)
    main = optimized["الفرص الاستثمارية"]
    metadata = optimized["معلومات التقرير"]
    assert [main.cell(6, column).value for column in range(1, 33)] == HEADERS
    assert main["Y7"].hyperlink.target == "https://official.example/opportunities/1"
    assert metadata["B8"].value == 2
    assert metadata["B11"].value == "الفرص المطابقة للمرشحات المحددة"
    assert metadata["B12"].value == "عبارة البحث: مستودع"
    assert optimized["الفرص الاستثمارية"]["A8"].value == "فرصة الصف الزوجي"
    assert optimized["الفرص الاستثمارية"]["A8"].fill.fgColor.rgb.endswith(BRAND["canvas"])


def test_write_only_workbook_preserves_empty_and_formula_safety(tmp_path):
    path = Path(tmp_path) / "write-only-empty.xlsx"
    build_opportunities_workbook_write_only(
        path, [], 0, source_fact_summary, spreadsheet_safe,
        datetime(2026, 10, 13, 15, 45, tzinfo=timezone.utc))
    empty = load_workbook(path, data_only=False)
    sheet = empty["الفرص الاستثمارية"]
    assert sheet.max_column == 32
    assert sheet.auto_filter.ref == "A6:AF6"
    assert sheet.freeze_panes == "A7"
    assert sheet["A7"].value == "لا توجد فرص مطابقة لعوامل التصفية المحددة."
    assert empty["معلومات التقرير"]["B8"].value == 0

    formula_path = Path(tmp_path) / "write-only-formula.xlsx"
    record = _opportunity(title_ar="=HYPERLINK(\"https://evil.example\",\"افتح\")",
                          reference_number="+000123", publication_date="تاريخ غير صالح", submission_deadline=None)
    build_opportunities_workbook_write_only(
        formula_path, [record], 1, source_fact_summary, spreadsheet_safe,
        datetime(2026, 10, 13, 15, 45, tzinfo=timezone.utc))
    formula_book = load_workbook(formula_path, data_only=False)
    assert formula_book["الفرص الاستثمارية"]["A7"].value.startswith("'=HYPERLINK")
    assert formula_book["الفرص الاستثمارية"]["T7"].value == "'+000123"
    assert isinstance(formula_book["الفرص الاستثمارية"]["Q7"].value, str)
    assert formula_book["الفرص الاستثمارية"]["R7"].value is None
