"""
Sinh tự động Semantic Model (TMDL) cho dự án Power BI (PBIP) từ lớp mart KPI.

Power BI chỉ nạp các bảng đã tổng hợp trong schema "mart" của PostgreSQL
(do src/build_marts.py tạo), không nạp bảng thô dim_* / fact_*:

  Chiều dùng chung  dim_year, dim_month, dim_member, dim_forecast_member, dim_forecast_model
  KPI lịch sử       kpi_monthly_overview, kpi_quarterly, kpi_daily, kpi_weekday,
                    kpi_monthly_by_dimension, kpi_dimension_summary,
                    kpi_customer_segment, kpi_annual_summary
  Dự báo            forecast_series, forecast_accuracy
  Hỗ trợ quyết định dss_forecast_plan, dss_dealer_allocation, dss_company_priority
  Khác              kpi_parameters, dq_checks

Measure chỉ cộng các cột thành phần rồi chia lại (không cộng dồn phần trăm),
nên số khớp với SQL ở mọi mức gộp. Thư mục <Name>.Report không bị đụng tới.

Cách dùng:
    python src/powerbi/build_pbip.py                 # đọc DATABASE_URL trong .env
    python src/powerbi/build_pbip.py --server localhost:5432 --database car_sales_dw
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# 1. CÁC BẢNG MART (khớp với src/kpi_marts.sql)
# ---------------------------------------------------------------------------
MART_TABLES: dict[str, list[str]] = {
    "dim_year": ["year", "year_label", "period_type"],
    "dim_month": ["month_start", "year", "quarter_no", "quarter", "year_quarter", "month_no",
                  "month_name", "year_month", "year_month_label", "period_type"],
    "dim_member": ["member_key", "dimension_name", "dimension_label", "dimension_value",
                   "parent_value", "dimension_order"],
    "dim_forecast_member": ["series_key", "level", "level_label", "member", "level_order"],
    "dim_forecast_model": ["model_name", "model_label", "is_main_model"],
    "kpi_monthly_overview": [
        "month_start", "year", "units", "revenue", "asp", "units_pm", "revenue_pm", "units_py",
        "revenue_py", "units_mom_pct", "revenue_mom_pct", "units_yoy_pct", "revenue_yoy_pct",
        "units_ytd", "revenue_ytd", "units_ytd_py", "revenue_ytd_py", "units_ytd_yoy_pct",
        "revenue_ytd_yoy_pct", "seasonality_index", "seasonality_index_2y", "target_units",
        "target_revenue", "units_vs_target_pct", "revenue_vs_target_pct", "units_target_status",
        "revenue_target_status", "auto_units", "auto_share_pct", "auto_share_change_pp",
        "active_dealers", "units_per_dealer", "selling_days", "dealers_growing",
        "dealers_compared", "dealers_growing_pct"],
    "kpi_quarterly": [
        "quarter_start", "year", "quarter_no", "year_quarter", "units", "revenue", "asp", "units_pq",
        "revenue_pq", "units_py", "revenue_py", "units_qoq_pct", "revenue_qoq_pct",
        "units_yoy_pct", "revenue_yoy_pct"],
    "kpi_daily": ["full_date", "month_start", "year", "dow_no", "day_of_week", "units", "revenue", "asp"],
    "kpi_weekday": ["period", "year", "dow_no", "day_of_week", "selling_days", "units", "revenue",
                    "avg_units_per_day", "weekday_index"],
    "kpi_monthly_by_dimension": [
        "dimension_name", "dimension_label", "dimension_value", "parent_value", "member_key",
        "month_start", "year", "units", "revenue", "asp", "units_pm", "units_py", "revenue_py",
        "units_mom_pct", "units_yoy_pct", "revenue_yoy_pct", "units_yoy_delta", "units_share_pct",
        "revenue_share_pct", "share_change_pp", "units_ytd", "revenue_ytd", "rank_in_month"],
    "kpi_dimension_summary": [
        "dimension_name", "dimension_label", "dimension_value", "parent_value", "member_key",
        "period", "year", "units", "revenue", "asp", "units_share_pct", "revenue_share_pct",
        "units_py", "revenue_py", "units_yoy_pct", "revenue_yoy_pct", "units_yoy_delta",
        "share_change_pp", "avg_monthly_units", "demand_cv", "active_months", "rank_units",
        "rank_revenue", "mover_group"],
    "kpi_customer_segment": [
        "period", "year", "income_quartile", "income_band", "income_min", "income_max", "gender",
        "units", "revenue", "asp", "avg_income", "sum_income", "sum_price_to_income",
        "price_to_income", "units_share_pct"],
    "kpi_annual_summary": [
        "period", "year", "units", "revenue", "asp", "units_py", "revenue_py", "units_yoy_pct",
        "revenue_yoy_pct", "target_units", "target_revenue", "units_target_status",
        "auto_share_pct", "auto_share_change_pp", "top10_model_share_pct", "hhi_company",
        "n_companies", "n_models", "n_dealers", "selling_days", "units_per_dealer_month",
        "dealers_growing_pct", "demand_cv", "peak_month", "peak_month_units", "low_month",
        "low_month_units"],
    "forecast_series": [
        "month_start", "level", "level_label", "member", "series_key", "model_name", "is_main_model",
        "series_type", "actual_units", "forecast_units", "lower_80", "upper_80", "forecast_error",
        "in_interval"],
    "forecast_accuracy": [
        "level", "level_label", "member", "series_key", "model_name", "is_main_model", "n_points",
        "actual_total", "forecast_total", "abs_error_total", "error_total", "n_in_interval", "mae",
        "rmse", "mape_pct", "wape_pct", "accuracy_pct", "bias_pct", "tracking_signal",
        "interval_coverage_pct", "naive_wape_pct", "fva_pp", "wape_threshold", "bias_threshold",
        "wape_pass", "bias_pass", "status", "tracking_status", "model_rank"],
    "dss_forecast_plan": [
        "month_start", "level", "level_label", "member", "series_key", "model_name",
        "forecast_units", "lower_80", "upper_80", "units_py", "forecast_growth_pct", "demand_cv",
        "avg_monthly_units", "asp_hist", "safety_factor", "recommended_order", "projected_revenue",
        "projected_revenue_low", "projected_revenue_high", "backtest_accuracy_pct",
        "backtest_status"],
    "dss_dealer_allocation": [
        "month_start", "dealer_region", "dealer_name", "units_6m", "dealer_share_6m",
        "region_share_6m", "total_forecast_units", "allocated_units", "allocated_units_low",
        "allocated_units_high", "allocated_revenue", "region_model_forecast"],
    "dss_company_priority": [
        "company", "series_key", "forecast_next_6m", "units_same_6m_py", "forecast_growth_pct",
        "demand_cv", "forecast_accuracy_pct", "projected_revenue_6m", "units_share_pct",
        "score_growth", "score_share", "score_stability", "score_accuracy", "w_growth", "w_share",
        "w_stability", "w_accuracy", "priority_score", "priority_rank", "priority_tier"],
    "kpi_parameters": ["main_model", "target_growth", "wape_threshold", "bias_threshold",
                       "safety_factor", "w_growth", "w_share", "w_stability", "w_accuracy",
                       "updated_at"],
    "dq_checks": ["check_code", "check_name", "metric_value", "threshold", "passed", "detail",
                  "checked_at"],
}

# (bảng nhiều, cột) -> (bảng một, cột)
RELATIONSHIPS = [
    (("dim_month", "year"), ("dim_year", "year")),
    (("kpi_monthly_overview", "month_start"), ("dim_month", "month_start")),
    (("kpi_quarterly", "quarter_start"), ("dim_month", "month_start")),
    (("kpi_daily", "month_start"), ("dim_month", "month_start")),
    (("kpi_weekday", "year"), ("dim_year", "year")),
    (("kpi_monthly_by_dimension", "month_start"), ("dim_month", "month_start")),
    (("kpi_monthly_by_dimension", "member_key"), ("dim_member", "member_key")),
    (("kpi_dimension_summary", "member_key"), ("dim_member", "member_key")),
    (("kpi_dimension_summary", "year"), ("dim_year", "year")),
    (("kpi_customer_segment", "year"), ("dim_year", "year")),
    (("kpi_annual_summary", "year"), ("dim_year", "year")),
    (("forecast_series", "month_start"), ("dim_month", "month_start")),
    (("forecast_series", "series_key"), ("dim_forecast_member", "series_key")),
    (("forecast_series", "model_name"), ("dim_forecast_model", "model_name")),
    (("forecast_accuracy", "series_key"), ("dim_forecast_member", "series_key")),
    (("forecast_accuracy", "model_name"), ("dim_forecast_model", "model_name")),
    (("dss_forecast_plan", "month_start"), ("dim_month", "month_start")),
    (("dss_forecast_plan", "series_key"), ("dim_forecast_member", "series_key")),
    (("dss_dealer_allocation", "month_start"), ("dim_month", "month_start")),
    (("dss_company_priority", "series_key"), ("dim_forecast_member", "series_key")),
]

# Cột trùng thông tin với bảng chiều -> ẩn, để người dựng visual dùng cột của bảng chiều
_FK = {ft: set() for (ft, _), _ in RELATIONSHIPS}
for (ft, fc), _ in RELATIONSHIPS:
    _FK[ft].add(fc)
HIDE_EXTRA = {
    "kpi_monthly_by_dimension": {"dimension_name", "dimension_label", "dimension_value", "parent_value", "year"},
    "kpi_dimension_summary": {"dimension_name", "dimension_label", "dimension_value", "parent_value", "period"},
    "forecast_series": {"level", "level_label", "member", "is_main_model"},
    "forecast_accuracy": {"level", "level_label", "member", "is_main_model"},
    "dss_forecast_plan": {"level", "level_label", "member", "model_name"},
    "dss_company_priority": set(),
    "kpi_customer_segment": {"sum_income", "sum_price_to_income"},
    "dim_member": {"member_key", "dimension_order"},
    "dim_forecast_member": {"series_key", "level_order"},
    "kpi_monthly_overview": {"year"},
    "kpi_daily": {"year"},
    "kpi_quarterly": {"year"},
}

SORT_BY = {
    ("dim_month", "month_name"): "month_no",
    ("dim_member", "dimension_label"): "dimension_order",
    ("dim_forecast_member", "level_label"): "level_order",
    ("kpi_weekday", "day_of_week"): "dow_no",
    ("kpi_daily", "day_of_week"): "dow_no",
    ("kpi_customer_segment", "income_band"): "income_quartile",
}

HIERARCHIES = {
    "dim_month": [("Thời gian", ["year", "year_quarter", "year_month_label"])],
    "dim_member": [("Phân tích", ["dimension_label", "dimension_value"])],
    "dim_forecast_member": [("Chuỗi dự báo", ["level_label", "member"])],
}

TEXT_COLS = {
    "year_label", "period_type", "quarter", "year_quarter", "month_name", "year_month_label",
    "member_key", "dimension_name", "dimension_label", "dimension_value", "parent_value",
    "series_key", "level", "level_label", "member", "model_name", "model_label",
    "units_target_status", "revenue_target_status", "day_of_week", "period", "income_band",
    "gender", "peak_month", "low_month", "series_type", "status", "tracking_status",
    "backtest_status", "dealer_region", "dealer_name", "company", "priority_tier", "main_model",
    "check_code", "check_name", "threshold", "detail", "mover_group",
}
BOOL_COLS = {"is_main_model", "in_interval", "wape_pass", "bias_pass", "passed"}
DATE_COLS = {"month_start", "quarter_start", "full_date", "updated_at", "checked_at"}
INT_COLS = {
    "year", "quarter_no", "month_no", "year_month", "dimension_order", "level_order", "quarter",
    "dow_no", "income_quartile", "income_min", "income_max", "active_dealers", "selling_days",
    "dealers_growing", "dealers_compared", "n_companies", "n_models", "n_dealers", "n_points",
    "n_in_interval", "active_months", "rank_units", "rank_revenue", "rank_in_month",
    "model_rank", "priority_rank",
}
# Cột cộng được giữa các dòng (còn lại là tỷ lệ / chỉ số: không tự cộng)
ADDITIVE = re.compile(
    r"^(units|revenue|units_p[mqy]|revenue_p[mqy]|target_units|target_revenue|auto_units|"
    r"units_yoy_delta|actual_units|forecast_units|lower_80|upper_80|forecast_error|"
    r"recommended_order|projected_revenue.*|allocated_.*|units_6m|forecast_next_6m|"
    r"units_same_6m_py|actual_total|forecast_total|abs_error_total|error_total|n_in_interval|"
    r"n_points|selling_days|dealers_growing|dealers_compared|sum_income|sum_price_to_income)$")

M_TYPES = {"int64": "Int64.Type", "string": "type text", "dateTime": "type date",
           "double": "type number", "boolean": "type logical"}
TIMESTAMP_COLS = {"updated_at", "checked_at"}


def col_spec(table: str, col: str) -> dict:
    """Suy kiểu, định dạng, cách gộp và ẩn/hiện từ tên cột."""
    if col in TEXT_COLS:
        dtype, fmt = "string", None
    elif col in BOOL_COLS:
        dtype, fmt = "boolean", None
    elif col in DATE_COLS:
        dtype = "dateTime"
        fmt = "yyyy-mm-dd hh:nn" if col in TIMESTAMP_COLS else (
            "mmm yyyy" if col in {"month_start", "quarter_start"} else "yyyy-mm-dd")
    elif col in INT_COLS:
        dtype, fmt = "int64", "0"
    else:
        dtype = "double"
        if col.endswith("_pct") or col.startswith(("w_", "score_")) or col in {
                "target_growth", "wape_threshold", "bias_threshold", "dealer_share_6m",
                "region_share_6m", "metric_value"}:
            fmt = "0.0%"
        elif col.endswith("_pp"):
            fmt = "+0.0%;-0.0%;0.0%"
        elif "revenue" in col or col.startswith("asp") or col == "avg_income":
            fmt = "$#,0"
        elif col in {"seasonality_index", "seasonality_index_2y", "weekday_index", "demand_cv",
                     "hhi_company", "price_to_income", "tracking_signal", "priority_score",
                     "safety_factor"}:
            fmt = "0.000"
        elif col in {"mae", "rmse", "units_per_dealer", "avg_units_per_day", "avg_monthly_units",
                     "units_per_dealer_month"}:
            fmt = "#,0.0"
        else:
            fmt = "#,0"
    if col in {"income_min", "income_max"}:
        fmt = "$#,0"
    summarize = "sum" if (ADDITIVE.match(col) and dtype in {"double", "int64"}
                          and not table.startswith("dim_")) else "none"
    hidden = col in _FK.get(table, set()) or col in HIDE_EXTRA.get(table, set())
    return {"dtype": dtype, "fmt": fmt, "summarize": summarize, "hidden": hidden}


# ---------------------------------------------------------------------------
# 2. MEASURES (chỉ cộng cột thành phần rồi chia lại)
# ---------------------------------------------------------------------------
GREEN, RED = "#2E7D32", "#C62828"


def build_measures():
    """Trả về list (tên, DAX, formatString, displayFolder, mô tả)."""
    PCT, PP, INT, USD, DEC = "0.0%", "+0.0%;-0.0%;0.0%", "#,0", "$#,0", "0.000"
    F1, F2, F3, F4, F5, F6, F7 = ("1. Tổng quan", "2. Theo chiều phân tích", "3. Khách hàng & ngày",
                                  "4. Dự báo", "5. Hỗ trợ quyết định", "6. Mục tiêu & ngưỡng",
                                  "7. Chất lượng dữ liệu")
    O, D = "kpi_monthly_overview", "kpi_monthly_by_dimension"
    FS, FA, PL = "forecast_series", "forecast_accuracy", "dss_forecast_plan"

    def comparable(table: str, value: str, base: str) -> str:
        """Tăng trưởng chỉ trên các tháng có kỳ so sánh (tránh lẫn tháng chưa có năm trước)."""
        return (
            f"VAR _t = FILTER ( {table}, NOT ISBLANK ( {table}[{base}] ) )\n"
            f"VAR _cur = SUMX ( _t, {table}[{value}] )\n"
            f"VAR _base = SUMX ( _t, {table}[{base}] )\n"
            "RETURN DIVIDE ( _cur - _base, _base )"
        )

    def level_default(expr: str, level: str) -> str:
        """Chưa chọn cấp / thành viên dự báo thì dùng cấp mặc định, tránh cộng lẫn các cấp."""
        return (
            "IF (\n"
            "    ISFILTERED ( dim_forecast_member[level] ) || ISFILTERED ( dim_forecast_member[level_label] )\n"
            "        || ISFILTERED ( dim_forecast_member[member] ),\n"
            f"    {expr},\n"
            f"    CALCULATE ( {expr}, dim_forecast_member[level] = \"{level}\" )\n"
            ")"
        )

    def main_model(expr: str) -> str:
        """Chưa chọn mô hình thì dùng mô hình chính (đặt trong build_marts.py)."""
        return (
            "IF (\n"
            "    ISFILTERED ( dim_forecast_model[model_name] ) || ISFILTERED ( dim_forecast_model[model_label] ),\n"
            f"    {expr},\n"
            f"    CALCULATE ( {expr}, dim_forecast_model[is_main_model] = TRUE () )\n"
            ")"
        )

    def last_month(table: str, col: str) -> str:
        return (f"VAR _m = MAX ( {table}[month_start] )\n"
                f"RETURN CALCULATE ( SUM ( {table}[{col}] ), {table}[month_start] = _m )")

    whatif = "( 1 + [Demand Change Value] )"

    return [
        # ---------- 1. Tổng quan (kpi_monthly_overview) ----------
        ("Units", f"SUM ( {O}[units] )", INT, F1, "D1 – Sản lượng bán"),
        ("Revenue", f"SUM ( {O}[revenue] )", USD, F1, "D2 – Doanh thu"),
        ("ASP", "DIVIDE ( [Revenue], [Units] )", USD, F1, "D3 – Giá bán bình quân"),
        ("Units PY", f"SUM ( {O}[units_py] )", INT, F1, "Sản lượng cùng kỳ năm trước"),
        ("Revenue PY", f"SUM ( {O}[revenue_py] )", USD, F1, None),
        ("Units YoY %", comparable(O, "units", "units_py"), PCT, F1, "D4 – so cùng kỳ"),
        ("Revenue YoY %", comparable(O, "revenue", "revenue_py"), PCT, F1, "D4 – so cùng kỳ"),
        ("Units MoM %", comparable(O, "units", "units_pm"), PCT, F1, "D4 – so tháng trước"),
        ("Revenue MoM %", comparable(O, "revenue", "revenue_pm"), PCT, F1, "D4"),
        ("Units YTD", last_month(O, "units_ytd"), INT, F1, "D4 – lũy kế đến tháng cuối đang chọn"),
        ("Revenue YTD", last_month(O, "revenue_ytd"), USD, F1, None),
        ("Units YTD YoY %",
         f"VAR _m = MAX ( {O}[month_start] )\n"
         f"VAR _c = CALCULATE ( SUM ( {O}[units_ytd] ), {O}[month_start] = _m )\n"
         f"VAR _p = CALCULATE ( SUM ( {O}[units_ytd_py] ), {O}[month_start] = _m )\n"
         "RETURN DIVIDE ( _c - _p, _p )", PCT, F1, "D4"),
        ("Revenue YTD YoY %",
         f"VAR _m = MAX ( {O}[month_start] )\n"
         f"VAR _c = CALCULATE ( SUM ( {O}[revenue_ytd] ), {O}[month_start] = _m )\n"
         f"VAR _p = CALCULATE ( SUM ( {O}[revenue_ytd_py] ), {O}[month_start] = _m )\n"
         "RETURN DIVIDE ( _c - _p, _p )", PCT, F1, "D4"),
        ("Seasonality Index", f"AVERAGE ( {O}[seasonality_index_2y] )", DEC, F1,
         "D7 – 1,0 = tháng trung bình; trung bình 2 năm"),
        ("Auto Share %", f"DIVIDE ( SUM ( {O}[auto_units] ), [Units] )", PCT, F1, "D14"),
        ("Dealers Growing %", f"DIVIDE ( SUM ( {O}[dealers_growing] ), SUM ( {O}[dealers_compared] ) )",
         PCT, F1, "D16 – % đại lý tăng so cùng kỳ"),
        ("Units per Dealer", f"AVERAGE ( {O}[units_per_dealer] )", "#,0.0", F1, "D16 – xe/đại lý/tháng"),

        # ---------- 2. Theo chiều (kpi_monthly_by_dimension + dim_member) ----------
        ("Dim Units", f"SUM ( {D}[units] )", INT, F2,
         "Sản lượng theo chiều đang chọn ở dim_member[dimension_label]"),
        ("Dim Revenue", f"SUM ( {D}[revenue] )", USD, F2, None),
        ("Dim ASP", "DIVIDE ( [Dim Revenue], [Dim Units] )", USD, F2, None),
        ("Dim Units PY", f"SUM ( {D}[units_py] )", INT, F2, None),
        ("Dim Units YoY %", comparable(D, "units", "units_py"), PCT, F2, "D12–D17"),
        ("Dim Revenue YoY %", comparable(D, "revenue", "revenue_py"), PCT, F2, "D12–D17"),
        ("Dim Units YoY Delta", f"SUM ( {D}[units_yoy_delta] )", "+#,0;-#,0;0", F2,
         "D13 – chênh lệch xe so cùng kỳ"),
        ("Dim Units Share %",
         "DIVIDE (\n"
         "    [Dim Units],\n"
         "    CALCULATE ( [Dim Units], ALLSELECTED ( dim_member[dimension_value], dim_member[parent_value] ) )\n"
         ")", PCT, F2, "D5, D6, D12–D17 – tỷ trọng trong chiều đang chọn"),
        ("Dim Rank", "IF ( NOT ISBLANK ( [Dim Units] ), RANKX ( ALLSELECTED ( dim_member[dimension_value] ), [Dim Units] ) )",
         "0", F2, "D16 – xếp hạng theo sản lượng"),

        # ---------- 3. Khách hàng & ngày ----------
        ("Segment Units", "SUM ( kpi_customer_segment[units] )", INT, F3, "D11, D17"),
        ("Segment Revenue", "SUM ( kpi_customer_segment[revenue] )", USD, F3, None),
        ("Segment ASP", "DIVIDE ( [Segment Revenue], [Segment Units] )", USD, F3, None),
        ("Segment Avg Income", "DIVIDE ( SUM ( kpi_customer_segment[sum_income] ), [Segment Units] )",
         USD, F3, None),
        ("Price to Income",
         "DIVIDE ( SUM ( kpi_customer_segment[sum_price_to_income] ), [Segment Units] )", "0.00", F3,
         "D11 – giá xe / thu nhập năm"),
        ("Segment Share %",
         "DIVIDE ( [Segment Units], CALCULATE ( [Segment Units], ALLSELECTED ( kpi_customer_segment[income_band], kpi_customer_segment[gender] ) ) )",
         PCT, F3, None),
        ("Daily Units", "SUM ( kpi_daily[units] )", INT, F3, "D1 theo ngày"),
        ("Daily Revenue", "SUM ( kpi_daily[revenue] )", USD, F3, None),
        ("Weekday Index",
         "DIVIDE (\n"
         "    DIVIDE ( SUM ( kpi_weekday[units] ), SUM ( kpi_weekday[selling_days] ) ),\n"
         "    CALCULATE ( DIVIDE ( SUM ( kpi_weekday[units] ), SUM ( kpi_weekday[selling_days] ) ),\n"
         "                ALLSELECTED ( kpi_weekday[day_of_week], kpi_weekday[dow_no] ) )\n"
         ")", DEC, F3, "D8 – 1,0 = ngày trung bình"),

        # ---------- 4. Dự báo ----------
        ("Actual Units",
         level_default(f"DIVIDE ( SUM ( {FS}[actual_units] ), DISTINCTCOUNT ( {FS}[model_name] ) )", "total"),
         INT, F4, "Thực tế trên trục dự báo (mặc định cấp tổng)"),
        ("Forecast Units", level_default(main_model(f"SUM ( {FS}[forecast_units] )"), "total"), INT, F4,
         "F1 – mặc định mô hình chính, cấp tổng"),
        ("Forecast Lower 80", level_default(main_model(f"SUM ( {FS}[lower_80] )"), "total"), INT, F4, None),
        ("Forecast Upper 80", level_default(main_model(f"SUM ( {FS}[upper_80] )"), "total"), INT, F4, None),
        ("WAPE %",
         level_default(main_model(f"DIVIDE ( SUM ( {FA}[abs_error_total] ), SUM ( {FA}[actual_total] ) )"), "company"),
         PCT, F4, "F3 – mặc định cấp hãng, mô hình chính"),
        ("Forecast Accuracy %", "IF ( NOT ISBLANK ( [WAPE %] ), 1 - [WAPE %] )", PCT, F4, "F3"),
        ("Bias %",
         level_default(main_model(f"DIVIDE ( SUM ( {FA}[error_total] ), SUM ( {FA}[actual_total] ) )"), "company"),
         PP, F4, "F5 – dương là dự báo dư"),
        ("MAE", level_default(main_model(f"DIVIDE ( SUM ( {FA}[abs_error_total] ), SUM ( {FA}[n_points] ) )"), "company"),
         "#,0.0", F4, "F4"),
        ("Interval Coverage %",
         level_default(main_model(f"DIVIDE ( SUM ( {FA}[n_in_interval] ), SUM ( {FA}[n_points] ) )"), "company"),
         PCT, F4, "F8 – mục tiêu ≈ 80%"),
        ("Naive WAPE %",
         "CALCULATE ( [WAPE %], dim_forecast_model[model_name] = \"seasonal_naive\" )", PCT, F4, None),
        ("FVA", "IF ( NOT ISBLANK ( [WAPE %] ), [Naive WAPE %] - [WAPE %] )", PP, F4,
         "F7 – dương là tốt hơn seasonal naive"),

        # ---------- 5. Hỗ trợ quyết định ----------
        ("Plan Forecast Units", level_default(f"SUM ( {PL}[forecast_units] )", "total"), INT, F5,
         "F1 6 tháng tới, mô hình chính"),
        ("Plan Units PY", level_default(f"SUM ( {PL}[units_py] )", "total"), INT, F5, None),
        ("Forecast Growth %", "DIVIDE ( [Plan Forecast Units] - [Plan Units PY], [Plan Units PY] )",
         PCT, F5, "S1"),
        ("Recommended Order",
         level_default(f"SUMX ( {PL}, {PL}[forecast_units] * {whatif} * ( 1 + [Safety Factor Value] * {PL}[demand_cv] ) )", "total"),
         INT, F5, "S3, S6 – theo thanh trượt What-if"),
        ("Projected Revenue",
         level_default(f"SUMX ( {PL}, {PL}[forecast_units] * {whatif} * {PL}[asp_hist] )", "total"),
         USD, F5, "S4, S6"),
        ("Allocated Units", f"SUM ( dss_dealer_allocation[allocated_units] ) * {whatif}", INT, F5, "S2"),
        ("Allocated Revenue", f"SUM ( dss_dealer_allocation[allocated_revenue] ) * {whatif}", USD, F5, "S2"),
        ("Priority Score", "AVERAGE ( dss_company_priority[priority_score] )", DEC, F5, "S5"),
        ("Priority Rank", "MIN ( dss_company_priority[priority_rank] )", "0", F5, "S5"),

        # ---------- 6. Mục tiêu & ngưỡng ----------
        ("Target Growth", "MAX ( kpi_parameters[target_growth] )", PCT, F6, None),
        ("WAPE Threshold", "MAX ( kpi_parameters[wape_threshold] )", PCT, F6, None),
        ("Bias Threshold", "MAX ( kpi_parameters[bias_threshold] )", PCT, F6, None),
        ("Target Units",
         f"SUMX ( FILTER ( {O}, NOT ISBLANK ( {O}[target_units] ) ), {O}[target_units] )", INT, F6, None),
        ("Target Revenue",
         f"SUMX ( FILTER ( {O}, NOT ISBLANK ( {O}[target_revenue] ) ), {O}[target_revenue] )", USD, F6, None),
        ("Units vs Target %",
         f"VAR _a = SUMX ( FILTER ( {O}, NOT ISBLANK ( {O}[target_units] ) ), {O}[units] )\n"
         "RETURN DIVIDE ( _a, [Target Units] ) - 1", PP, F6, None),
        ("Revenue vs Target %",
         f"VAR _a = SUMX ( FILTER ( {O}, NOT ISBLANK ( {O}[target_revenue] ) ), {O}[revenue] )\n"
         "RETURN DIVIDE ( _a, [Target Revenue] ) - 1", PP, F6, None),
        ("Units Target Color",
         f"IF ( ISBLANK ( [Units vs Target %] ), BLANK (), IF ( [Units vs Target %] >= 0, \"{GREEN}\", \"{RED}\" ) )",
         None, F6, "Conditional formatting > Field value"),
        ("Revenue Target Color",
         f"IF ( ISBLANK ( [Revenue vs Target %] ), BLANK (), IF ( [Revenue vs Target %] >= 0, \"{GREEN}\", \"{RED}\" ) )",
         None, F6, None),
        ("WAPE Color",
         f"IF ( ISBLANK ( [WAPE %] ), BLANK (), IF ( [WAPE %] <= [WAPE Threshold], \"{GREEN}\", \"{RED}\" ) )",
         None, F6, None),
        ("Bias Color",
         f"IF ( ISBLANK ( [Bias %] ), BLANK (), IF ( ABS ( [Bias %] ) <= [Bias Threshold], \"{GREEN}\", \"{RED}\" ) )",
         None, F6, None),
        ("Forecast Status",
         "IF (\n"
         "    ISBLANK ( [WAPE %] ),\n"
         "    BLANK (),\n"
         "    IF ( [WAPE %] <= [WAPE Threshold] && ABS ( [Bias %] ) <= [Bias Threshold], \"Đạt\", \"Không đạt\" )\n"
         ")", None, F6, "Đạt khi WAPE và |Bias| cùng trong ngưỡng"),

        # ---------- 7. Chất lượng dữ liệu ----------
        ("DQ Checks Passed", "COUNTROWS ( FILTER ( dq_checks, dq_checks[passed] = TRUE () ) )", "0", F7, None),
        ("DQ Pass Rate", "DIVIDE ( [DQ Checks Passed], COUNTROWS ( dq_checks ) )", PCT, F7, "Q1–Q6"),
    ]


# ---------------------------------------------------------------------------
# 3. SINH TMDL
# ---------------------------------------------------------------------------
def q(name: str) -> str:
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
        out += [f"\tmeasure {q(name)} =", indent(expr, 3)]
    else:
        out.append(f"\tmeasure {q(name)} = {expr}")
    if fmt:
        out.append(f"\t\tformatString: {fmt}")
    if folder:
        out.append(f"\t\tdisplayFolder: {folder}")
    out.append(f"\t\tlineageTag: {tag()}")
    return "\n".join(out) + "\n"


def column_block(name, dtype, summarize="none", hidden=False, source=None, fmt=None, extra=None) -> str:
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


def mart_table_tmdl(table: str, cols: list[str]) -> str:
    parts = [f"table {q(table)}", f"\tlineageTag: {tag()}", ""]
    specs = {c: col_spec(table, c) for c in cols}
    for c in cols:
        s = specs[c]
        extra = []
        if (table, c) in SORT_BY:
            extra.append(f"sortByColumn: {q(SORT_BY[(table, c)])}")
        if table.startswith("dim_") and c == cols[0]:
            extra.append("isKey")
        parts.append(column_block(c, s["dtype"], s["summarize"], s["hidden"], fmt=s["fmt"], extra=extra))
    for hname, levels in HIERARCHIES.get(table, []):
        parts += [f"\thierarchy {q(hname)}", f"\t\tlineageTag: {tag()}", ""]
        for lv in levels:
            parts += [f"\t\tlevel {q(lv)}", f"\t\t\tcolumn: {q(lv)}", f"\t\t\tlineageTag: {tag()}", ""]
    col_list = ", ".join(f'"{c}"' for c in cols)
    type_list = ", ".join(
        f'{{"{c}", {"type datetime" if c in TIMESTAMP_COLS else M_TYPES[specs[c]["dtype"]]}}}' for c in cols)
    m = (
        "let\n"
        "    Source = PostgreSQL.Database(PgServer, PgDatabase),\n"
        f"    Data = Source{{[Schema = PgSchema, Item = \"{table}\"]}}[Data],\n"
        f"    Selected = Table.SelectColumns(Data, {{{col_list}}}),\n"
        f"    Typed = Table.TransformColumnTypes(Selected, {{{type_list}}})\n"
        "in\n"
        "    Typed"
    )
    parts += [f"\tpartition {q(table)} = m", "\t\tmode: import", "\t\tsource =", indent(m, 4), ""]
    return "\n".join(parts)


def whatif_tmdl(table: str, start: float, end: float, step: float, default: float, fmt: str) -> str:
    return "\n".join([
        f"table {q(table)}",
        f"\tlineageTag: {tag()}",
        "",
        measure_block(f"{table} Value", f"SELECTEDVALUE ( {q(table)}[Value], {default} )", fmt,
                      None, "Tham số What-if (S6)"),
        column_block("Value", "double", "none", source="[Value]", fmt=fmt, extra=["isNameInferred"]),
        f"\tpartition {q(table)} = calculated",
        "\t\tmode: import",
        f"\t\tsource = GENERATESERIES ( {start}, {end}, {step} )",
        "",
    ])


def measures_tmdl(measures) -> str:
    parts = ["table _Measures", f"\tlineageTag: {tag()}", ""]
    parts += [measure_block(*m) for m in measures]
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
    return "\n".join([param("PgServer", server), param("PgDatabase", database), param("PgSchema", schema)])


def relationships_tmdl() -> str:
    out = []
    for (ft, fc), (tt, tc) in RELATIONSHIPS:
        out += [f"relationship {tag()}", f"\tfromColumn: {q(ft)}.{q(fc)}",
                f"\ttoColumn: {q(tt)}.{q(tc)}", ""]
    return "\n".join(out)


def model_tmdl() -> str:
    return "\n".join(["model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
                      "\tdiscourageImplicitMeasures", "\tsourceQueryCulture: en-US", ""])


def write_blank_report(out_dir: Path, name: str) -> None:
    """Report trống (PBIR, 1 trang) trỏ tới semantic model, chỉ tạo khi chưa có."""
    rep = out_dir / f"{name}.Report"
    base = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
    dump = lambda o: json.dumps(o, ensure_ascii=False, indent=2) + "\n"
    write(rep / "definition.pbir", dump({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{name}.SemanticModel"}},
    }))
    d = rep / "definition"
    write(d / "version.json", dump({"$schema": f"{base}/versionMetadata/1.0.0/schema.json", "version": "2.0.0"}))
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
        "version": "1.0", "artifacts": [{"report": {"path": f"{name}.Report"}}],
        "settings": {"enableAutoRecovery": True}}, indent=2) + "\n")


# ---------------------------------------------------------------------------
# 4. GHI RA ĐĨA
# ---------------------------------------------------------------------------
def load_env(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def parse_database_url() -> tuple[str | None, str | None]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        return None, None
    p = urlparse(url.replace("postgresql+psycopg2", "postgresql"))
    server = f"{p.hostname}:{p.port or 5432}" if p.hostname else None
    return server, (p.path.lstrip("/") or None)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def build(args) -> Path:
    out_dir = Path(args.out).resolve()
    sm_dir = out_dir / f"{args.name}.SemanticModel"
    def_dir = sm_dir / "definition"

    # Xóa định nghĩa cũ và cache để Power BI nạp lại từ PostgreSQL
    if def_dir.exists():
        shutil.rmtree(def_dir)
    for stale in [sm_dir / "model.bim", sm_dir / ".pbi" / "cache.abf"]:
        if stale.exists():
            stale.unlink()

    write(sm_dir / "definition.pbism", json.dumps({"version": "4.0", "settings": {}}, indent=2) + "\n")
    write(def_dir / "database.tmdl", f"database {q(args.name)}\n\tcompatibilityLevel: 1567\n")

    measures = build_measures()
    tables = {t: mart_table_tmdl(t, cols) for t, cols in MART_TABLES.items()}
    tables["Demand Change"] = whatif_tmdl("Demand Change", -0.3, 0.3, 0.05, 0, "+0%;-0%;0%")
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
    print(f"   {len(MART_TABLES)} bảng mart + 3 bảng phụ, {len(RELATIONSHIPS)} quan hệ, {len(measures)} measure")
    if not report_dir.exists():
        write_blank_report(out_dir, args.name)
        print(f"-> Chưa có report, đã tạo report trống: {report_dir}")
    else:
        print(f"-> Giữ nguyên report đã thiết kế: {report_dir}")
    return pbip


def main(argv=None) -> int:
    load_env()
    env_server, env_db = parse_database_url()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "powerbi"), help="thư mục chứa dự án PBIP")
    ap.add_argument("--name", default="CarSalesDSS", help="tên dự án PBIP")
    ap.add_argument("--server", default=env_server or "localhost:5432")
    ap.add_argument("--database", default=env_db or "car_sales_dw")
    ap.add_argument("--schema", default="mart", help="schema chứa các bảng KPI")
    build(ap.parse_args(argv))
    return 0


if __name__ == "__main__":
    sys.exit(main())
