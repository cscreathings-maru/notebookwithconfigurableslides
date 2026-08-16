"""Unit: `ChartSpec`/`TableSpec` validation (D3).

`deck/charts.py` is not wired into the LD-8 renderer yet (see that module's
docstring), but the contracts themselves are unchanged and still worth
protecting: a chart whose series don't match its categories, or a table row
that doesn't match its header width, must fail validation rather than reach
`insert_chart`/`insert_table` and produce a malformed `.pptx`.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.deck.charts import ChartSeries, ChartSpec, TableSpec


def test_chart_spec_requires_series_values_to_match_categories() -> None:
    with pytest.raises(ValidationError):
        ChartSpec(
            categories=["Q1", "Q2", "Q3"],
            series=[ChartSeries(name="Revenue", values=[1.0, 2.0])],
        )


def test_chart_spec_accepts_matching_series() -> None:
    chart = ChartSpec(
        categories=["Q1", "Q2"],
        series=[ChartSeries(name="Revenue", values=[10.0, 20.0])],
    )
    assert chart.kind == "bar"


def test_table_spec_requires_rows_to_match_header_width() -> None:
    with pytest.raises(ValidationError):
        TableSpec(headers=["A", "B"], rows=[["1", "2", "3"]])


def test_table_spec_accepts_matching_rows() -> None:
    table = TableSpec(headers=["A", "B"], rows=[["1", "2"], ["3", "4"]])
    assert len(table.rows) == 2
