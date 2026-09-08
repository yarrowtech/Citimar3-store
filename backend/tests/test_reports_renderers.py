"""One small synthetic ReportPayload (one of each block type), rendered
through every one of the 8 format writers -- verifies each produces
well-formed, non-empty output of the right shape without needing
DATASET.xlsx or any chart/table builder (matches this project's synthetic-
data testing philosophy)."""
from __future__ import annotations

import io
import json
from xml.etree import ElementTree

import docx
import openpyxl
import plotly.graph_objects as go
import pytest
from pptx import Presentation

from src import charts
from src.reports.dispatch import RENDERERS
from src.reports.models import (
    ChartBlock,
    DataQualityBlock,
    FiltersSummaryBlock,
    ForecastSummaryBlock,
    GaugeBlock,
    KpiGridBlock,
    KpiItem,
    ReportMeta,
    ReportPayload,
    TableBlock,
    TextBlock,
    TitleBlock,
)


@pytest.fixture()
def sample_payload() -> ReportPayload:
    figure = json.loads(go.Figure(data=[go.Bar(x=["Jan", "Feb"], y=[100.0, 200.0])]).to_json())
    gauge_spec = charts.atv_gauge(950.0, target=1000.0)

    return ReportPayload(
        meta=ReportMeta(
            title="Test Report",
            generated_at="2026-08-26 12:00",
            filters_summary_text="Store: NM | Date: 2026-08-01 to 2026-08-26",
        ),
        blocks=[
            TitleBlock(text="Test Report"),
            TextBlock(heading="Notes", text="Some free-text notes."),
            FiltersSummaryBlock(text="Store: NM | Date: 2026-08-01 to 2026-08-26"),
            KpiGridBlock(heading="KPI Summary", items=[KpiItem(label="Net Sales", value="₹1,000.00", status="green")]),
            ChartBlock(title="Test Chart", figure=figure),
            GaugeBlock(spec=gauge_spec),
            TableBlock(title="Test Table", columns=["A", "B"], rows=[{"A": 1, "B": 2}, {"A": 3, "B": 4}]),
            DataQualityBlock(heading="Data Quality Warnings", items=["43,650 rows flagged as zero-amount duplicates."]),
            ForecastSummaryBlock(heading="Forecast Model", items=[KpiItem(label="Model", value="SARIMAX")], note="Backtested over 4 folds."),
        ],
    )


def test_pdf_renderer_produces_valid_pdf(sample_payload):
    content = RENDERERS["pdf"].render(sample_payload)
    assert content.startswith(b"%PDF")
    assert len(content) > 1000


def test_pptx_renderer_produces_valid_pptx(sample_payload):
    content = RENDERERS["pptx"].render(sample_payload)
    prs = Presentation(io.BytesIO(content))
    assert len(prs.slides) >= len(sample_payload.blocks)  # title slide + one per non-title block


def test_docx_renderer_produces_valid_docx(sample_payload):
    content = RENDERERS["docx"].render(sample_payload)
    doc = docx.Document(io.BytesIO(content))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert "Test Report" in full_text


def test_xlsx_renderer_produces_valid_xlsx(sample_payload):
    content = RENDERERS["xlsx"].render(sample_payload)
    wb = openpyxl.load_workbook(io.BytesIO(content))
    assert "Summary" in wb.sheetnames
    assert "Test Table" in wb.sheetnames
    table_sheet = wb["Test Table"]
    assert table_sheet["A1"].value == "A"
    assert table_sheet["A2"].value == 1


def test_csv_renderer_contains_kpi_and_table_data(sample_payload):
    content = RENDERERS["csv"].render(sample_payload)
    text = content.decode("utf-8-sig")
    assert "Test Report" in text
    assert "Net Sales" in text
    assert "Test Table" in text
    assert "1" in text and "2" in text


def test_md_renderer_contains_markdown_headings(sample_payload):
    content = RENDERERS["md"].render(sample_payload)
    text = content.decode("utf-8")
    assert "# Test Report" in text
    assert "## Test Table" in text
    assert "data:image/png;base64," in text  # chart/gauge embedded as base64


def test_html_renderer_produces_valid_self_contained_html(sample_payload):
    content = RENDERERS["html"].render(sample_payload)
    text = content.decode("utf-8")
    assert "<!doctype html>" in text.lower()
    assert "Test Report" in text
    assert "data:image/png;base64," in text


def test_xml_renderer_produces_parseable_structured_xml(sample_payload):
    content = RENDERERS["xml"].render(sample_payload)
    root = ElementTree.fromstring(content)
    assert root.tag == "report"
    assert root.find("meta/title").text == "Test Report"
    table_titles = [el.get("title") for el in root.findall("blocks/table")]
    assert "Test Table" in table_titles


def test_pie_transformed_chart_still_rasterizes(sample_payload):
    """A chart the frontend switched to pie (via charts.apply_chart_type) is a
    real go.Pie figure by the time it reaches a report block -- confirm the
    visual renderers still rasterize it."""
    pie_fig = charts.apply_chart_type(
        json.loads(go.Figure(data=[go.Bar(x=["Jan", "Feb", "Mar"], y=[10.0, 20.0, 30.0], name="Net Sales")]).to_json()),
        "pie",
    )
    assert pie_fig["data"][0]["type"] == "pie"
    payload = ReportPayload(
        meta=sample_payload.meta,
        blocks=[TitleBlock(text="Pie"), ChartBlock(title="Pie Chart", figure=pie_fig)],
    )
    for fmt in ("pdf", "md", "html"):
        content = RENDERERS[fmt].render(payload)
        assert isinstance(content, bytes) and len(content) > 500


def test_unknown_block_free_payload_still_round_trips_all_formats(sample_payload):
    """Every registered renderer should at least produce non-empty bytes --
    a broad smoke test in case a future format is added to RENDERERS."""
    for fmt, spec in RENDERERS.items():
        content = spec.render(sample_payload)
        assert isinstance(content, bytes)
        assert len(content) > 0, f"{fmt} renderer produced empty output"
