"""
Sinh tự động Semantic Model (định dạng TMDL) cho dự án Power BI (PBIP).

Script ghi lại toàn bộ thư mục <Name>.SemanticModel/definition mỗi lần chạy:
  - 5 bảng nạp từ PostgreSQL (dim_customer, dim_car, dim_dealer,
    fact_car_sales, fact_demand_forecast) qua Power Query (M)
  - Bảng Calendar liên tục, 2 bảng tham số What-if, bảng _Measures
  - Quan hệ, hierarchy, sort-by-column, đánh dấu Date Table
  - Toàn bộ measure DAX nhóm D, F, S + mục tiêu và ngưỡng đạt/không đạt

Thư mục <Name>.Report (các trang dashboard) KHÔNG bị đụng tới, nên dashboard
thiết kế một lần trong Power BI Desktop được giữ nguyên qua các lần sinh lại.

Cách dùng:
    python src/powerbi/build_pbip.py                  # đọc DATABASE_URL
    python src/powerbi/build_pbip.py --server localhost:5432 --database car_sales_dw
    python src/powerbi/build_pbip.py --main-model holt_winters
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# 1. CẤU HÌNH BẢNG NGUỒN (khớp với src/schema.sql)
# ---------------------------------------------------------------------------
# (tên cột, kiểu TMDL, summarizeBy, ẩn?)
SOURCE_TABLES: dict[str, list[tuple[str, str, str, bool]]] = {
    "dim_customer": [
        ("customer_id", "int64", "none", True),
        ("customer_name", "string", "none", False),
        ("gender", "string", "none", False),
        ("annual_income", "int64", "none", False),
        ("phone", "string", "none", True),
    ],
    "dim_car": [
        ("car_key", "int64", "none", True),
        ("company", "string", "none", False),
        ("model", "string", "none", False),
        ("engine", "string", "none", False),
        ("transmission", "string", "none", False),
        ("color", "string", "none", False),
        ("body_style", "string", "none", False),
    ],
    "dim_dealer": [
        ("dealer_id", "int64", "none", True),
        ("dealer_no", "string", "none", False),
        ("dealer_name", "string", "none", False),
        ("dealer_region", "string", "none", False),
    ],
    "fact_car_sales": [
        ("car_id", "string", "none", False),
        ("date_id", "int64", "none", True),
        ("customer_id", "int64", "none", True),
        ("car_key", "int64", "none", True),
        ("dealer_id", "int64", "none", True),
        ("price", "int64", "sum", False),
        ("quantity", "int64", "sum", False),
    ],
    "fact_demand_forecast": [
        ("forecast_id", "int64", "none", True),
        ("month_id", "int64", "none", True),
        ("month_start", "dateTime", "none", False),
        ("level", "string", "none", False),
        ("member", "string", "none", False),
        ("model_name", "string", "none", False),
        ("forecast_units", "double", "sum", False),
        ("lower_80", "double", "sum", False),
        ("upper_80", "double", "sum", False),
        ("actual_units", "double", "sum", False),
        ("is_backtest", "boolean", "none", False),
    ],
}

M_TYPES = {
    "int64": "Int64.Type",
    "string": "type text",
    "dateTime": "type datetime",
    "double": "type number",
    "boolean": "type logical",
}

# (bảng nhiều, cột) -> (bảng một, cột)
RELATIONSHIPS = [
    (("fact_car_sales", "date_id"), ("Calendar", "DateId")),
    (("fact_car_sales", "customer_id"), ("dim_customer", "customer_id")),
    (("fact_car_sales", "car_key"), ("dim_car", "car_key")),
    (("fact_car_sales", "dealer_id"), ("dim_dealer", "dealer_id")),
    (("fact_demand_forecast", "month_start"), ("Calendar", "Date")),
]

HIERARCHIES = {
    "dim_car": [("Product", ["company", "model"])],
    "dim_dealer": [("Geography", ["dealer_region", "dealer_name"])],
}

GREEN, RED = "#2E7D32", "#C62828"


# ---------------------------------------------------------------------------
# 2. MEASURES
# ---------------------------------------------------------------------------
def build_measures(main_model: str, target_growth: float,
                   wape_threshold: float, bias_threshold: float):
    """Trả về list (tên, biểu thức DAX, formatString, displayFolder, mô tả)."""
    PCT, INT, USD, DEC = "0.0%", "#,0", "$#,0", "0.00"
    F2, F3, F4, FT = ("2. Nhu cầu lịch sử", "3. Dự báo", "4. Hỗ trợ quyết định",
                      "5. Mục tiêu & ngưỡng")

    def fc_table(backtest: bool, default_level: str) -> str:
        """Bảng dự báo đã lọc: mô hình chính và cấp mặc định nếu chưa có slicer."""
        # Tên hãng, tên vùng và 'ALL' không trùng nhau, nên khi trục visual là
        # member thì member đã xác định cấp; chỉ dùng cấp mặc định khi cả hai
        # cột level và member đều không bị lọc.
        return (
            "VAR _useModel = NOT ISFILTERED ( fact_demand_forecast[model_name] )\n"
            "VAR _useLevel =\n"
            "    NOT ISFILTERED ( fact_demand_forecast[level] )\n"
            "        && NOT ISFILTERED ( fact_demand_forecast[member] )\n"
            "VAR _t =\n"
            "    FILTER (\n"
            "        fact_demand_forecast,\n"
            f"        fact_demand_forecast[is_backtest] = {'TRUE' if backtest else 'FALSE'} ()\n"
            f"            && ( NOT _useModel || fact_demand_forecast[model_name] = \"{main_model}\" )\n"
            f"            && ( NOT _useLevel || fact_demand_forecast[level] = \"{default_level}\" )\n"
            "    )\n"
        )

    def by_member(measure: str) -> str:
        """Tính measure lịch sử cho đúng hãng / vùng đang hiển thị ở bảng dự báo."""
        return (
            "VAR _lvl = SELECTEDVALUE ( fact_demand_forecast[level], \"total\" )\n"
            "RETURN\n"
            "    SWITCH (\n"
            "        _lvl,\n"
            f"        \"company\", CALCULATE ( {measure}, TREATAS ( VALUES ( fact_demand_forecast[member] ), dim_car[company] ) ),\n"
            f"        \"region\", CALCULATE ( {measure}, TREATAS ( VALUES ( fact_demand_forecast[member] ), dim_dealer[dealer_region] ) ),\n"
            f"        {measure}\n"
            "    )"
        )

    next_month = (
        "VAR _first =\n"
        "    CALCULATE (\n"
        "        MIN ( fact_demand_forecast[month_start] ),\n"
        "        fact_demand_forecast[is_backtest] = FALSE (),\n"
        "        REMOVEFILTERS ( Calendar )\n"
        "    )\n"
    )

    m = [
        # ---------------- Nhóm 2: nhu cầu lịch sử ----------------
        ("Units Sold", "SUM ( fact_car_sales[quantity] )", INT, F2, "D1 – Sản lượng bán"),
        ("Revenue", "SUM ( fact_car_sales[price] )", USD, F2, "D2 – Doanh thu"),
        ("ASP", "DIVIDE ( [Revenue], [Units Sold] )", USD, F2, "D3 – Giá bán bình quân"),
        ("Units PM", "CALCULATE ( [Units Sold], DATEADD ( Calendar[Date], -1, MONTH ) )", INT, F2, None),
        ("Units PQ", "CALCULATE ( [Units Sold], DATEADD ( Calendar[Date], -1, QUARTER ) )", INT, F2, None),
        ("Units PY", "CALCULATE ( [Units Sold], SAMEPERIODLASTYEAR ( Calendar[Date] ) )", INT, F2, None),
        ("Revenue PM", "CALCULATE ( [Revenue], DATEADD ( Calendar[Date], -1, MONTH ) )", USD, F2, None),
        ("Revenue PY", "CALCULATE ( [Revenue], SAMEPERIODLASTYEAR ( Calendar[Date] ) )", USD, F2, None),
        ("Units MoM %", "DIVIDE ( [Units Sold] - [Units PM], [Units PM] )", PCT, F2, "D4"),
        ("Units QoQ %", "DIVIDE ( [Units Sold] - [Units PQ], [Units PQ] )", PCT, F2, "D4"),
        ("Units YoY %", "DIVIDE ( [Units Sold] - [Units PY], [Units PY] )", PCT, F2, "D4"),
        ("Revenue MoM %", "DIVIDE ( [Revenue] - [Revenue PM], [Revenue PM] )", PCT, F2, "D4"),
        ("Revenue YoY %", "DIVIDE ( [Revenue] - [Revenue PY], [Revenue PY] )", PCT, F2, "D4"),
        ("Units YTD", "TOTALYTD ( [Units Sold], Calendar[Date] )", INT, F2, "D4"),
        ("Revenue YTD", "TOTALYTD ( [Revenue], Calendar[Date] )", USD, F2, "D4"),
        ("Revenue YTD YoY %",
         "VAR _py = CALCULATE ( [Revenue YTD], SAMEPERIODLASTYEAR ( Calendar[Date] ) )\n"
         "RETURN DIVIDE ( [Revenue YTD] - _py, _py )", PCT, F2, "D4"),
        ("Units Share %",
         "DIVIDE ( [Units Sold], CALCULATE ( [Units Sold], ALLSELECTED ( dim_car ) ) )",
         PCT, F2, "D5, D12, D14, D15 – tỷ trọng theo thuộc tính xe"),
        ("Region Share %",
         "DIVIDE ( [Units Sold], CALCULATE ( [Units Sold], ALLSELECTED ( dim_dealer ) ) )",
         PCT, F2, "D6"),
        ("Gender Share %",
         "DIVIDE ( [Units Sold], CALCULATE ( [Units Sold], ALLSELECTED ( dim_customer[gender] ) ) )",
         PCT, F2, "D17"),
        ("Seasonality Index",
         "DIVIDE (\n"
         "    [Units Sold],\n"
         "    AVERAGEX ( ALLSELECTED ( Calendar[MonthNo], Calendar[Month] ), [Units Sold] )\n"
         ")", DEC, F2, "D7"),
        ("Demand CV",
         "VAR _t = FILTER ( ADDCOLUMNS ( VALUES ( Calendar[YearMonth] ), \"u\", [Units Sold] ), [u] > 0 )\n"
         "RETURN DIVIDE ( STDEVX.P ( _t, [u] ), AVERAGEX ( _t, [u] ) )", "0.000", F2, "D9"),
        ("Demand CV Hist", "CALCULATE ( [Demand CV], REMOVEFILTERS ( Calendar ) )", "0.000", F2,
         "D9 trên toàn bộ lịch sử, dùng cho tháng dự báo"),
        ("ASP Hist", "CALCULATE ( [ASP], REMOVEFILTERS ( Calendar ) )", USD, F2,
         "D3 trên toàn bộ lịch sử, dùng cho tháng dự báo"),
        ("Top10 Model Share %",
         "DIVIDE (\n"
         "    SUMX ( TOPN ( 10, ALLSELECTED ( dim_car[model] ), [Units Sold] ), [Units Sold] ),\n"
         "    CALCULATE ( [Units Sold], ALLSELECTED ( dim_car[model] ) )\n"
         ")", PCT, F2, "D10"),
        ("Price to Income",
         "AVERAGEX (\n"
         "    fact_car_sales,\n"
         "    DIVIDE ( fact_car_sales[price], RELATED ( dim_customer[annual_income] ) )\n"
         ")", DEC, F2, "D11"),
        ("Units YoY Delta", "[Units Sold] - [Units PY]", "+#,0;-#,0;0", F2, "D13 – mẫu tăng, giảm mạnh nhất"),
        ("Auto Share %",
         "DIVIDE ( CALCULATE ( [Units Sold], dim_car[transmission] = \"Auto\" ), [Units Sold] )",
         PCT, F2, "D14"),
        ("Auto Share Change pp",
         "[Auto Share %] - CALCULATE ( [Auto Share %], SAMEPERIODLASTYEAR ( Calendar[Date] ) )",
         "+0.0%;-0.0%;0.0%", F2, "D14"),
        ("Dealer Rank", "RANKX ( ALLSELECTED ( dim_dealer[dealer_name] ), [Units Sold] )", "0", F2, "D16"),
        ("Units per Dealer per Month",
         "DIVIDE (\n"
         "    [Units Sold],\n"
         "    DISTINCTCOUNT ( fact_car_sales[dealer_id] ) * DISTINCTCOUNT ( Calendar[YearMonth] )\n"
         ")", "0.0", F2, "D16"),
        ("Dealers Growing %",
         "DIVIDE (\n"
         "    COUNTROWS ( FILTER ( VALUES ( dim_dealer[dealer_name] ), [Units YoY %] > 0 ) ),\n"
         "    COUNTROWS ( VALUES ( dim_dealer[dealer_name] ) )\n"
         ")", PCT, F2, "D16"),

        # ---------------- Nhóm 3: dự báo ----------------
        ("Forecast Units", fc_table(False, "total") + "RETURN SUMX ( _t, fact_demand_forecast[forecast_units] )",
         INT, F3, f"F1 – mặc định mô hình {main_model}, cấp tổng"),
        ("Forecast Lower", fc_table(False, "total") + "RETURN SUMX ( _t, fact_demand_forecast[lower_80] )",
         INT, F3, "F1 – cận dưới khoảng 80%"),
        ("Forecast Upper", fc_table(False, "total") + "RETURN SUMX ( _t, fact_demand_forecast[upper_80] )",
         INT, F3, "F1 – cận trên khoảng 80%"),
        ("Forecast Next Month",
         next_month + "RETURN CALCULATE ( [Forecast Units], fact_demand_forecast[month_start] = _first, REMOVEFILTERS ( Calendar ) )",
         INT, F3, "F1 – tháng đầu tiên sau dữ liệu (01/2024)"),
        ("Backtest Forecast", fc_table(True, "company") + "RETURN SUMX ( _t, fact_demand_forecast[forecast_units] )",
         INT, F3, "Dự báo cho 6 tháng backtest"),
        ("Backtest Actual", fc_table(True, "company") + "RETURN SUMX ( _t, fact_demand_forecast[actual_units] )",
         INT, F3, "Thực tế của 6 tháng backtest"),
        ("WAPE %",
         fc_table(True, "company")
         + "RETURN DIVIDE (\n"
           "    SUMX ( _t, ABS ( fact_demand_forecast[actual_units] - fact_demand_forecast[forecast_units] ) ),\n"
           "    SUMX ( _t, fact_demand_forecast[actual_units] )\n"
           ")", PCT, F3, "F3 – mặc định cấp hãng"),
        ("Forecast Accuracy %", "IF ( NOT ISBLANK ( [WAPE %] ), 1 - [WAPE %] )", PCT, F3, "F3"),
        ("MAPE %",
         fc_table(True, "company")
         + "RETURN AVERAGEX (\n"
           "    _t,\n"
           "    DIVIDE ( ABS ( fact_demand_forecast[actual_units] - fact_demand_forecast[forecast_units] ), fact_demand_forecast[actual_units] )\n"
           ")", PCT, F3, "F2"),
        ("MAE",
         fc_table(True, "company")
         + "RETURN AVERAGEX ( _t, ABS ( fact_demand_forecast[actual_units] - fact_demand_forecast[forecast_units] ) )",
         "0.0", F3, "F4"),
        ("RMSE",
         fc_table(True, "company")
         + "RETURN SQRT ( AVERAGEX ( _t, ( fact_demand_forecast[actual_units] - fact_demand_forecast[forecast_units] ) ^ 2 ) )",
         "0.0", F3, "F4"),
        ("Bias %",
         fc_table(True, "company")
         + "RETURN DIVIDE (\n"
           "    SUMX ( _t, fact_demand_forecast[forecast_units] - fact_demand_forecast[actual_units] ),\n"
           "    SUMX ( _t, fact_demand_forecast[actual_units] )\n"
           ")", "+0.0%;-0.0%;0.0%", F3, "F5 – dương là dự báo dư"),
        ("Tracking Signal",
         fc_table(True, "company")
         + "RETURN DIVIDE (\n"
           "    SUMX ( _t, fact_demand_forecast[actual_units] - fact_demand_forecast[forecast_units] ),\n"
           "    AVERAGEX ( _t, ABS ( fact_demand_forecast[actual_units] - fact_demand_forecast[forecast_units] ) )\n"
           ")", "0.00", F3, "F6 – ngoài ±4 là cảnh báo"),
        ("FVA",
         "CALCULATE ( [WAPE %], fact_demand_forecast[model_name] = \"seasonal_naive\" ) - [WAPE %]",
         "+0.0%;-0.0%;0.0%", F3, "F7 – dương là mô hình tốt hơn seasonal naive"),
        ("Interval Coverage %",
         fc_table(True, "company")
         + "RETURN DIVIDE (\n"
           "    COUNTROWS ( FILTER ( _t, fact_demand_forecast[actual_units] >= fact_demand_forecast[lower_80]\n"
           "        && fact_demand_forecast[actual_units] <= fact_demand_forecast[upper_80] ) ),\n"
           "    COUNTROWS ( _t )\n"
           ")", PCT, F3, "F8"),

        # ---------------- Nhóm 4: hỗ trợ quyết định ----------------
        ("Actual Units for Member", by_member("[Units Sold]"), INT, F4,
         "Sản lượng thực tế của đúng hãng / vùng trên trục của bảng dự báo"),
        # Dịch thời gian bên trong by_member để danh sách hãng / vùng vẫn lấy
        # từ tháng dự báo, không bị mất khi lùi về năm trước.
        ("Actual Units PY for Member", by_member("[Units PY]"), INT, F4,
         "Sản lượng cùng kỳ năm trước của đúng hãng / vùng"),
        ("Forecast Growth %",
         "DIVIDE ( [Forecast Units] - [Actual Units PY for Member], [Actual Units PY for Member] )",
         PCT, F4, "S1"),
        ("Region Share 6M %",
         "VAR _lastDay = CALCULATE ( MAX ( fact_car_sales[date_id] ), ALL ( fact_car_sales ) )\n"
         "VAR _lastDate = DATE ( INT ( _lastDay / 10000 ), MOD ( INT ( _lastDay / 100 ), 100 ), MOD ( _lastDay, 100 ) )\n"
         "VAR _win = DATESINPERIOD ( Calendar[Date], _lastDate, -6, MONTH )\n"
         "RETURN\n"
         "    DIVIDE (\n"
         "        CALCULATE ( [Units Sold], _win, REMOVEFILTERS ( Calendar ) ),\n"
         "        CALCULATE ( [Units Sold], _win, REMOVEFILTERS ( Calendar ), ALL ( dim_dealer ) )\n"
         "    )", PCT, F4, "Tỷ trọng vùng / đại lý trong 6 tháng cuối dataset"),
        ("Allocated Units Next Month",
         "[Forecast Next Month] * [Region Share 6M %]", INT, F4, "S2"),
        ("Demand CV for Member", by_member("[Demand CV Hist]"), "0.000", F4, None),
        ("ASP for Member", by_member("[ASP Hist]"), USD, F4, None),
        ("Recommended Order",
         "[Forecast Units] * ( 1 + [Demand Change Value] ) * ( 1 + [Safety Factor Value] * [Demand CV for Member] )",
         INT, F4, "S3, S6 – có đệm theo độ biến động"),
        ("Projected Revenue",
         "[Forecast Units] * ( 1 + [Demand Change Value] ) * [ASP for Member]",
         USD, F4, "S4, S6"),

        # ---------------- Mục tiêu & ngưỡng ----------------
        ("Target Growth", f"{target_growth}", PCT, FT, "Mục tiêu tăng trưởng so với cùng kỳ"),
        ("WAPE Threshold", f"{wape_threshold}", PCT, FT, None),
        ("Bias Threshold", f"{bias_threshold}", PCT, FT, None),
        ("Target Units", "IF ( NOT ISBLANK ( [Units PY] ), [Units PY] * ( 1 + [Target Growth] ) )", INT, FT, None),
        ("Target Revenue", "IF ( NOT ISBLANK ( [Revenue PY] ), [Revenue PY] * ( 1 + [Target Growth] ) )", USD, FT, None),
        ("Units vs Target %", "DIVIDE ( [Units Sold], [Target Units] ) - 1", "+0.0%;-0.0%;0.0%", FT, None),
        ("Revenue vs Target %", "DIVIDE ( [Revenue], [Target Revenue] ) - 1", "+0.0%;-0.0%;0.0%", FT, None),
        ("Units Target Color",
         f"IF ( ISBLANK ( [Target Units] ), BLANK (), IF ( [Units Sold] >= [Target Units], \"{GREEN}\", \"{RED}\" ) )",
         None, FT, "Dùng cho Conditional formatting > Field value"),
        ("Revenue Target Color",
         f"IF ( ISBLANK ( [Target Revenue] ), BLANK (), IF ( [Revenue] >= [Target Revenue], \"{GREEN}\", \"{RED}\" ) )",
         None, FT, None),
        ("WAPE Color",
         f"IF ( ISBLANK ( [WAPE %] ), BLANK (), IF ( [WAPE %] <= [WAPE Threshold], \"{GREEN}\", \"{RED}\" ) )",
         None, FT, None),
        ("Bias Color",
         f"IF ( ISBLANK ( [Bias %] ), BLANK (), IF ( ABS ( [Bias %] ) <= [Bias Threshold], \"{GREEN}\", \"{RED}\" ) )",
         None, FT, None),
        ("Forecast Status",
         "IF (\n"
         "    ISBLANK ( [WAPE %] ),\n"
         "    BLANK (),\n"
         "    IF ( [WAPE %] <= [WAPE Threshold] && ABS ( [Bias %] ) <= [Bias Threshold], \"Đạt\", \"Không đạt\" )\n"
         ")", None, FT, "Đạt khi WAPE và |Bias| cùng trong ngưỡng"),
    ]
    return m


# ---------------------------------------------------------------------------
# 3. SINH TMDL
# ---------------------------------------------------------------------------
def q(name: str) -> str:
    """Đặt tên trong nháy đơn (luôn hợp lệ trong TMDL)."""
    return "'" + name.replace("'", "''") + "'"


def indent(text: str, tabs: int) -> str:
    pad = "\t" * tabs
    return "\n".join(pad + line if line.strip() else "" for line in text.splitlines())


def tag() -> str:
    return str(uuid.uuid4())


def measure_block(name, expr, fmt, folder, desc) -> str:
    out = []
    if desc:
        out.append(f"\t/// {desc}")
    if "\n" in expr:
        out.append(f"\tmeasure {q(name)} =")
        out.append(indent(expr, 3))
    else:
        out.append(f"\tmeasure {q(name)} = {expr}")
    if fmt:
        out.append(f"\t\tformatString: {fmt}")
    if folder:
        out.append(f"\t\tdisplayFolder: {folder}")
    out.append(f"\t\tlineageTag: {tag()}")
    return "\n".join(out) + "\n"


def column_block(name, dtype, summarize="none", hidden=False, source=None,
                 fmt=None, extra=None) -> str:
    out = [f"\tcolumn {q(name)}", f"\t\tdataType: {dtype}"]
    if fmt:
        out.append(f"\t\tformatString: {fmt}")
    if hidden:
        out.append("\t\tisHidden")
    out.append(f"\t\tsummarizeBy: {summarize}")
    for line in extra or []:
        out.append(f"\t\t{line}")
    out.append(f"\t\tsourceColumn: {source or name}")
    out.append(f"\t\tlineageTag: {tag()}")
    return "\n".join(out) + "\n"


def source_table_tmdl(table: str, cols) -> str:
    parts = [f"table {q(table)}", f"\tlineageTag: {tag()}", ""]
    for name, dtype, summ, hidden in cols:
        fmt = "yyyy-mm-dd" if dtype == "dateTime" else None
        parts.append(column_block(name, dtype, summ, hidden, fmt=fmt))
    for hname, levels in HIERARCHIES.get(table, []):
        parts.append(f"\thierarchy {q(hname)}")
        parts.append(f"\t\tlineageTag: {tag()}")
        for lv in levels:
            parts.append(f"\t\tlevel {q(lv)}")
            parts.append(f"\t\t\tcolumn: {q(lv)}")
            parts.append(f"\t\t\tlineageTag: {tag()}")
        parts.append("")
    col_list = ", ".join(f'"{c[0]}"' for c in cols)
    type_list = ", ".join(f'{{"{c[0]}", {M_TYPES[c[1]]}}}' for c in cols)
    m = (
        "let\n"
        "    Source = PostgreSQL.Database(PgServer, PgDatabase),\n"
        f"    Data = Source{{[Schema = PgSchema, Item = \"{table}\"]}}[Data],\n"
        f"    Selected = Table.SelectColumns(Data, {{{col_list}}}),\n"
        f"    Typed = Table.TransformColumnTypes(Selected, {{{type_list}}})\n"
        "in\n"
        "    Typed"
    )
    parts.append(f"\tpartition {q(table)} = m")
    parts.append("\t\tmode: import")
    parts.append("\t\tsource =")
    parts.append(indent(m, 4))
    parts.append("")
    return "\n".join(parts)


def calendar_tmdl(start: str, end: str) -> str:
    y1, m1, d1 = (int(x) for x in start.split("-"))
    y2, m2, d2 = (int(x) for x in end.split("-"))
    dax = (
        "ADDCOLUMNS (\n"
        f"    CALENDAR ( DATE ( {y1}, {m1}, {d1} ), DATE ( {y2}, {m2}, {d2} ) ),\n"
        "    \"Year\", YEAR ( [Date] ),\n"
        "    \"Quarter\", \"Q\" & QUARTER ( [Date] ),\n"
        "    \"MonthNo\", MONTH ( [Date] ),\n"
        "    \"Month\", FORMAT ( [Date], \"MMM\" ),\n"
        "    \"YearMonth\", YEAR ( [Date] ) * 100 + MONTH ( [Date] ),\n"
        "    \"DateId\", YEAR ( [Date] ) * 10000 + MONTH ( [Date] ) * 100 + DAY ( [Date] ),\n"
        "    \"DayOfWeek\", FORMAT ( [Date], \"ddd\" ),\n"
        "    \"DayOfWeekNo\", WEEKDAY ( [Date], 2 )\n"
        ")"
    )
    inferred = ["isNameInferred"]
    parts = [
        "table Calendar",
        "\tdataCategory: Time",
        f"\tlineageTag: {tag()}",
        "",
        column_block("Date", "dateTime", "none", source="[Date]", fmt="yyyy-mm-dd",
                     extra=["isKey"] + inferred),
        column_block("Year", "int64", "none", source="[Year]", fmt="0", extra=inferred),
        column_block("Quarter", "string", "none", source="[Quarter]", extra=inferred),
        column_block("MonthNo", "int64", "none", hidden=True, source="[MonthNo]", extra=inferred),
        column_block("Month", "string", "none", source="[Month]",
                     extra=["sortByColumn: MonthNo"] + inferred),
        column_block("YearMonth", "int64", "none", source="[YearMonth]", fmt="0", extra=inferred),
        column_block("DateId", "int64", "none", hidden=True, source="[DateId]", extra=inferred),
        column_block("DayOfWeekNo", "int64", "none", hidden=True, source="[DayOfWeekNo]", extra=inferred),
        column_block("DayOfWeek", "string", "none", source="[DayOfWeek]",
                     extra=["sortByColumn: DayOfWeekNo"] + inferred),
        "\thierarchy 'Date Hierarchy'",
        f"\t\tlineageTag: {tag()}",
    ]
    for lv in ["Year", "Quarter", "Month", "Date"]:
        parts += [f"\t\tlevel {lv}", f"\t\t\tcolumn: {lv}", f"\t\t\tlineageTag: {tag()}"]
    parts += ["", "\tpartition Calendar = calculated", "\t\tmode: import", "\t\tsource =",
              indent(dax, 4), ""]
    return "\n".join(parts)


def whatif_tmdl(table: str, start: float, end: float, step: float, default: float, fmt: str) -> str:
    measure_name = f"{table} Value"
    return "\n".join([
        f"table {q(table)}",
        f"\tlineageTag: {tag()}",
        "",
        measure_block(measure_name, f"SELECTEDVALUE ( {q(table)}[Value], {default} )", fmt, None,
                      "Tham số What-if (S6)"),
        column_block("Value", "double", "none", source="[Value]", fmt=fmt, extra=["isNameInferred"]),
        f"\tpartition {q(table)} = calculated",
        "\t\tmode: import",
        f"\t\tsource = GENERATESERIES ( {start}, {end}, {step} )",
        "",
    ])


def measures_tmdl(measures) -> str:
    parts = ["table _Measures", f"\tlineageTag: {tag()}", ""]
    for mdef in measures:
        parts.append(measure_block(*mdef))
    parts.append(column_block("Value", "int64", "none", hidden=True, source="[Value]",
                              extra=["isNameInferred"]))
    parts += ["\tpartition _Measures = calculated", "\t\tmode: import",
              "\t\tsource = ROW ( \"Value\", 0 )", ""]
    return "\n".join(parts)


def expressions_tmdl(server: str, database: str, schema: str) -> str:
    def param(name, value):
        return (f'expression {name} = "{value}" meta [IsParameterQuery=true, Type="Text", '
                f'IsParameterQueryRequired=true]\n\tlineageTag: {tag()}\n\n'
                f'\tannotation PBI_ResultType = Text\n')
    return "\n".join([param("PgServer", server), param("PgDatabase", database),
                      param("PgSchema", schema)])


def relationships_tmdl() -> str:
    out = []
    for (ft, fc), (tt, tc) in RELATIONSHIPS:
        out += [f"relationship {tag()}",
                f"\tfromColumn: {q(ft)}.{q(fc)}",
                f"\ttoColumn: {q(tt)}.{q(tc)}", ""]
    return "\n".join(out)


def model_tmdl() -> str:
    # Các bảng được nạp từ thư mục tables/, không cần dòng 'ref table'.
    return "\n".join([
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tdiscourageImplicitMeasures",
        "\tsourceQueryCulture: en-US",
        "",
    ])


def write_blank_report(out_dir: Path, name: str) -> None:
    """Report trống (1 trang) trỏ tới semantic model, chỉ tạo khi chưa có."""
    rep = out_dir / f"{name}.Report"
    # Định dạng PBIR (thư mục definition/), là định dạng mặc định của Power BI Desktop mới
    base = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
    dump = lambda o: json.dumps(o, ensure_ascii=False, indent=2) + "\n"
    write(rep / "definition.pbir", dump({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{name}.SemanticModel"}},
    }))
    d = rep / "definition"
    write(d / "version.json", dump({"$schema": f"{base}/versionMetadata/1.0.0/schema.json",
                                    "version": "2.0.0"}))
    write(d / "report.json", dump({
        "$schema": f"{base}/report/3.0.0/schema.json",
        "themeCollection": {"baseTheme": {
            "name": "CY24SU10", "type": "SharedResources",
            "reportVersionAtImport": {"visual": "2.0.0", "report": "3.0.0", "page": "2.0.0"}}},
        "resourcePackages": [{"name": "SharedResources", "type": "SharedResources",
                              "items": [{"name": "CY24SU10", "path": "BaseThemes/CY24SU10.json",
                                         "type": "BaseTheme"}]}],
    }))
    write(d / "pages" / "pages.json", dump({
        "$schema": f"{base}/pagesMetadata/1.0.0/schema.json",
        "pageOrder": ["ReportSection"], "activePageName": "ReportSection"}))
    write(d / "pages" / "ReportSection" / "page.json", dump({
        "$schema": f"{base}/page/2.0.0/schema.json",
        "name": "ReportSection", "displayName": "Tổng quan",
        "displayOption": "FitToPage", "height": 720, "width": 1280}))
    write(out_dir / f"{name}.pbip", json.dumps({
        "version": "1.0",
        "artifacts": [{"report": {"path": f"{name}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    }, indent=2) + "\n")


# ---------------------------------------------------------------------------
# 4. GHI RA ĐĨA
# ---------------------------------------------------------------------------
def parse_database_url() -> tuple[str | None, str | None]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        return None, None
    p = urlparse(url.replace("postgresql+psycopg2", "postgresql"))
    server = f"{p.hostname}:{p.port or 5432}" if p.hostname else None
    db = p.path.lstrip("/") or None
    return server, db


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def build(args) -> Path:
    out_dir = Path(args.out).resolve()
    sm_dir = out_dir / f"{args.name}.SemanticModel"
    def_dir = sm_dir / "definition"

    # Xóa định nghĩa cũ và cache dữ liệu cũ để Power BI nạp lại từ PostgreSQL
    if def_dir.exists():
        shutil.rmtree(def_dir)
    for stale in [sm_dir / "model.bim", sm_dir / ".pbi" / "cache.abf"]:
        if stale.exists():
            stale.unlink()

    write(sm_dir / "definition.pbism", json.dumps({"version": "4.0", "settings": {}}, indent=2) + "\n")
    write(def_dir / "database.tmdl", f"database {q(args.name)}\n\tcompatibilityLevel: 1567\n")

    measures = build_measures(args.main_model, args.target_growth,
                              args.wape_threshold, args.bias_threshold)
    tables: dict[str, str] = {}
    for t, cols in SOURCE_TABLES.items():
        tables[t] = source_table_tmdl(t, cols)
    tables["Calendar"] = calendar_tmdl(args.calendar_start, args.calendar_end)
    tables["Demand Change"] = whatif_tmdl("Demand Change", -0.3, 0.3, 0.05, 0, "0%")
    tables["Safety Factor"] = whatif_tmdl("Safety Factor", 0, 2, 0.1, 1, "0.0")
    tables["_Measures"] = measures_tmdl(measures)

    for t, text in tables.items():
        write(def_dir / "tables" / f"{t}.tmdl", text)
    write(def_dir / "model.tmdl", model_tmdl())
    write(def_dir / "expressions.tmdl", expressions_tmdl(args.server, args.database, args.schema))
    write(def_dir / "relationships.tmdl", relationships_tmdl())

    gi = out_dir / ".gitignore"
    if not gi.exists():
        write(gi, "**/.pbi/localSettings.json\n**/.pbi/cache.abf\n")

    report_dir = out_dir / f"{args.name}.Report"
    pbip = out_dir / f"{args.name}.pbip"
    print(f"-> Đã sinh semantic model: {sm_dir}")
    print(f"   {len(tables)} bảng, {len(RELATIONSHIPS)} quan hệ, {len(measures)} measure "
          f"(mô hình dự báo chính: {args.main_model})")
    if not report_dir.exists():
        write_blank_report(out_dir, args.name)
        print(f"-> Chưa có report, đã tạo report trống: {report_dir}")
    elif not pbip.exists():
        write(pbip, json.dumps({"version": "1.0",
                                "artifacts": [{"report": {"path": f"{args.name}.Report"}}],
                                "settings": {"enableAutoRecovery": True}}, indent=2) + "\n")
    else:
        print(f"-> Giữ nguyên report đã thiết kế: {report_dir}")
    return pbip


def main(argv=None) -> int:
    env_server, env_db = parse_database_url()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "powerbi"), help="thư mục chứa dự án PBIP")
    ap.add_argument("--name", default="CarSalesDSS", help="tên dự án PBIP")
    ap.add_argument("--server", default=env_server or "localhost:5432")
    ap.add_argument("--database", default=env_db or "car_sales_dw")
    ap.add_argument("--schema", default="public")
    ap.add_argument("--main-model", default="sarima",
                    choices=["sarima", "holt_winters", "seasonal_naive"])
    ap.add_argument("--target-growth", type=float, default=0.05)
    ap.add_argument("--wape-threshold", type=float, default=0.20)
    ap.add_argument("--bias-threshold", type=float, default=0.05)
    ap.add_argument("--calendar-start", default="2022-01-01")
    ap.add_argument("--calendar-end", default="2024-12-31")
    args = ap.parse_args(argv)
    build(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
