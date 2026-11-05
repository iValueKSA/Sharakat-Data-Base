from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace

from openpyxl import load_workbook

from app.excel_export import BRAND, HEADERS, build_opportunities_workbook
from app.main import source_fact_summary, spreadsheet_safe


def _opportunity(**overrides):
    source = SimpleNamespace(source_name_ar="فرص الرسمية", source_url="https://official.example/opportunities/1")
    source_record = SimpleNamespace(
        source=source,
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
    assert main.auto_filter.ref == "A6:AD7"
    assert main.max_column == 30
    assert main["E1"].value == "تقرير الفرص الاستثمارية في الأحساء"
    assert main["A6"].value == HEADERS[0]
    assert main["X6"].value == HEADERS[23]
    assert main["AD6"].value == HEADERS[-1]
    assert main["A7"].value == long_title
    assert main["A7"].alignment.wrap_text is True
    assert main["E1"].font.name == "Ahda Text"
    assert main["A6"].font.name == "Ahda Text"
    assert main["A6"].fill.fgColor.rgb.endswith(BRAND["depth"])
    assert main["A6"].border.bottom.color.rgb.endswith(BRAND["bisht"])
    assert len(main._images) == 1
    assert len(metadata._images) == 1
    assert main["W7"].value == "https://official.example/opportunities/1"
    assert main["W7"].hyperlink.target == main["W7"].value
    assert main["P7"].value.date().isoformat() == "2026-10-01"
    assert main["Q7"].value.date().isoformat() == "2026-10-20"
    assert isinstance(main["M7"].value, (int, float))
    assert isinstance(main["N7"].value, (int, float))
    assert main["S7"].value == "06-26-183737-49010"
    assert main["S7"].number_format == "@"
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
    assert main["S7"].value == "'+000123"
    assert isinstance(main["P7"].value, str)
    assert main["Q7"].value is None
    assert main["W7"].hyperlink.target == "https://official.example/opportunities/1"
    assert not main["A7"].hyperlink


def test_zero_result_export_is_valid_and_has_explanatory_message():
    workbook = _build([])
    output = BytesIO()
    workbook.save(output)
    reopened = load_workbook(BytesIO(output.getvalue()), data_only=False)
    main = reopened["الفرص الاستثمارية"]
    metadata = reopened["معلومات التقرير"]

    assert main.max_column == 30
    assert main.auto_filter.ref == "A6:AD6"
    assert main.freeze_panes == "A7"
    assert main["A7"].value == "لا توجد فرص مطابقة لعوامل التصفية المحددة."
    assert metadata["B8"].value == 0
