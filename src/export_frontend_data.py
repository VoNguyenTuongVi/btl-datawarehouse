"""Đọc dashboard từ DB, dùng chung cho API và lệnh xuất snapshot tùy chọn."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import math
from pathlib import Path
import sys

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from env_config import get_database_url

HISTORY_QUERY = """
SELECT d.year * 100 + d.month AS month_id, c.company,
       SUM(f.quantity) AS units, SUM(f.price) AS revenue
FROM fact_car_sales f
JOIN dim_date d ON d.date_id = f.date_id
JOIN dim_car c ON c.car_key = f.car_key
GROUP BY d.year, d.month, c.company
ORDER BY c.company, month_id
"""
FORECAST_QUERY = """
SELECT month_id, level, member, model_name, forecast_units, actual_units,
       lower_80, upper_80, is_backtest
FROM fact_demand_forecast
WHERE level = 'company'
ORDER BY member, model_name, month_id
"""
QUERIES = {
    "monthly": """SELECT to_char(month_start, 'YYYY-MM') AS month, year,
        units, revenue, asp, units_py, target_units, units_mom_pct, units_yoy_pct,
        seasonality_index_2y AS seasonality
        FROM mart.kpi_monthly_overview ORDER BY month_start""",
    "forecast": """SELECT to_char(month_start, 'YYYY-MM') AS month, model_name,
        series_type, actual_units, forecast_units, lower_80, upper_80
        FROM mart.forecast_series WHERE level = 'total' AND member = 'ALL'
        ORDER BY month_start, model_name""",
    "accuracy": """SELECT level, member, model_name, n_points, actual_total,
        abs_error_total, error_total, n_in_interval FROM mart.forecast_accuracy
        ORDER BY level, member, model_name""",
    "company": """SELECT dimension_value AS member, units, units_share_pct, units_yoy_pct
        FROM mart.kpi_dimension_summary WHERE dimension_name = 'company'
        AND year = (SELECT MAX(year) FROM mart.kpi_annual_summary)
        ORDER BY units DESC, dimension_value""",
    "region": """SELECT dimension_value AS member, units, units_share_pct, units_yoy_pct
        FROM mart.kpi_dimension_summary WHERE dimension_name = 'dealer_region'
        AND year = (SELECT MAX(year) FROM mart.kpi_annual_summary)
        ORDER BY units DESC, dimension_value""",
    "annual": """SELECT year, units, revenue, asp, units_yoy_pct, revenue_yoy_pct,
        target_units, units_target_status FROM mart.kpi_annual_summary ORDER BY year""",
    "dq": """SELECT check_code, check_name, metric_value, passed, detail
        FROM mart.dq_checks ORDER BY check_code""",
    "model": """SELECT dimension_value || ' (' || COALESCE(parent_value, '') || ')' AS member,
        dimension_value AS model, parent_value AS company, units, revenue,
        revenue_share_pct, revenue_yoy_pct FROM mart.kpi_dimension_summary
        WHERE dimension_name = 'model'
        AND year = (SELECT MAX(year) FROM mart.kpi_annual_summary)
        ORDER BY revenue DESC, dimension_value, parent_value LIMIT 50""",
    "dealer": """WITH y AS (
        SELECT year, dealer_name, dealer_region, SUM(units) AS units, SUM(revenue) AS revenue
        FROM mart.v_sales GROUP BY year, dealer_name, dealer_region
    ), c AS (SELECT * FROM y WHERE year = (SELECT MAX(year) FROM y))
    SELECT c.dealer_name AS member, c.dealer_region AS region, c.units, c.revenue,
        1.0 * c.units / NULLIF(SUM(c.units) OVER (), 0) AS units_share_pct,
        1.0 * (c.units - p.units) / NULLIF(p.units, 0) AS units_yoy_pct,
        1.0 * c.revenue / NULLIF(SUM(c.revenue) OVER (), 0) AS revenue_share_pct
    FROM c LEFT JOIN y p ON p.year = c.year - 1 AND p.dealer_name = c.dealer_name
        AND p.dealer_region = c.dealer_region
    ORDER BY c.revenue DESC, c.dealer_name, c.dealer_region LIMIT 10""",
}
PARAMETERS_QUERY = """SELECT main_model, target_growth, wape_threshold, bias_threshold
FROM mart.kpi_parameters WHERE id = 1"""


def _number(value, label, *, nullable=False):
    if value is None and nullable:
        return None
    if value is None or isinstance(value, bool):
        raise ValueError(f"Thiếu hoặc sai số liệu: {label}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"Số liệu không hữu hạn: {label}")
    return result


def _month(value):
    result = int(value)
    if result < 190001 or not 1 <= result % 100 <= 12:
        raise ValueError(f"Tháng không hợp lệ: {value}")
    return result


def build_dss_payload(history, forecasts, cases, *, source="PostgreSQL", exported_at=None, default_model=None):
    """Chuẩn hóa dữ liệu đầu vào; không xuất tài khoản, mật khẩu hay dữ liệu khách hàng."""
    hist, fc, seen_history, seen_forecasts = [], [], set(), set()
    for row in history:
        company = str(row["company"])
        month = _month(row["month_id"])
        key = (company, month)
        if key in seen_history:
            raise ValueError(f"Lịch sử trùng hãng/tháng: {key}")
        seen_history.add(key)
        units = _number(row["units"], "units")
        revenue = _number(row["revenue"], "revenue")
        if units < 0 or revenue < 0:
            raise ValueError("Lịch sử có sản lượng hoặc doanh thu âm")
        hist.append({"company": company, "month_id": month, "units": units, "revenue": revenue})
    for row in forecasts:
        if row.get("level") != "company":
            continue
        month = _month(row["month_id"])
        backtest = row["is_backtest"]
        if not isinstance(backtest, bool):
            raise ValueError("is_backtest phải là boolean")
        member, model = str(row["member"]), str(row["model_name"])
        key = (member, model, month, backtest)
        if key in seen_forecasts:
            raise ValueError(f"Forecast trùng hãng/model/tháng: {key}")
        seen_forecasts.add(key)
        forecast = _number(row["forecast_units"], "forecast_units")
        actual = _number(row.get("actual_units"), "actual_units", nullable=not backtest)
        if forecast < 0 or (actual is not None and actual < 0):
            raise ValueError("Forecast hoặc actual có giá trị âm")
        fc.append({"level": "company", "member": member, "model_name": model,
                   "month_id": month, "is_backtest": backtest, "forecast_units": forecast,
                   "actual_units": actual,
                   "lower_80": _number(row.get("lower_80"), "lower_80", nullable=True),
                   "upper_80": _number(row.get("upper_80"), "upper_80", nullable=True)})
    future = [r for r in fc if not r["is_backtest"]]
    if not hist or not future:
        raise ValueError("Thiếu lịch sử hoặc forecast cấp hãng. Chạy ETL và forecast trước.")
    months = sorted({r["month_id"] for r in future})
    models = sorted({r["model_name"] for r in future})
    latest_actual = max(r["month_id"] for r in hist)
    next_months = [month for month in months if month > latest_actual]
    return {"schema_version": 1,
            "exported_at": exported_at or datetime.now(timezone.utc).isoformat(),
            "source": source,
            "default_month": next_months[0] if next_months else months[0],
            "default_model": default_model if default_model in models else models[0],
            "history": hist, "forecasts": fc, "cases": cases}


def read_dashboard(engine):
    """Mỗi lần gọi đọc lại DB; các truy vấn dùng chung một snapshot giao dịch.

    PostgreSQL: REPEATABLE READ, READ ONLY. Không ETL, train hoặc ghi DB khi GET.
    Nhánh dialect khác dùng cho kiểm thử bằng cơ sở dữ liệu SQLite thực.
    """
    catalogue = json.loads((ROOT / "tests/fixtures/dss_report_testcases.json").read_text(encoding="utf-8"))
    with engine.connect() as connection:
        if engine.dialect.name == "postgresql":
            connection = connection.execution_options(isolation_level="REPEATABLE READ", postgresql_readonly=True)
        with connection.begin():
            if engine.dialect.name == "postgresql":
                connection.execute(text("SET LOCAL statement_timeout = '15000ms'"))
            parameters = connection.execute(text(PARAMETERS_QUERY)).mappings().one_or_none()
            if parameters is None:
                raise ValueError("Thiếu cấu hình mart. Chạy bước marts trước.")
            payload = {name: [dict(r) for r in connection.execute(text(sql)).mappings()]
                       for name, sql in QUERIES.items()}
            history = list(connection.execute(text(HISTORY_QUERY)).mappings())
            forecasts = list(connection.execute(text(FORECAST_QUERY)).mappings())
    if not payload["monthly"] or not payload["annual"]:
        raise ValueError("Mart chưa có dữ liệu. Chạy bước marts sau ETL và forecast.")
    now = datetime.now(timezone.utc).isoformat()
    payload["exported_at"] = now
    payload["source"] = "PostgreSQL"
    payload["parameters"] = dict(parameters)
    payload["latest_year"] = max(int(row["year"]) for row in payload["annual"])
    payload["dss"] = build_dss_payload(history, forecasts, catalogue["cases"], exported_at=now,
                                       default_model=parameters["main_model"])
    return payload


def json_default(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(type(value).__name__)


def write_snapshot(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, default=json_default, separators=(",", ":"))
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(encoded + "\n", encoding="utf-8")
    temporary.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "exports/dashboard.json")
    args = parser.parse_args(argv)
    url = get_database_url()
    if not url or not url.startswith(("postgresql://", "postgresql+psycopg2://")):
        raise SystemExit("Cấu hình DATABASE_URL PostgreSQL trong .env trước khi xuất dữ liệu.")
    engine = create_engine(url, pool_pre_ping=True)
    try:
        payload = read_dashboard(engine)
        write_snapshot(args.out, payload)
    finally:
        engine.dispose()
    print(f"-> Đã xuất frontend: {args.out}")
    print(f"   {len(payload['dss']['history'])} dòng lịch sử hãng/tháng, {len(payload['dss']['forecasts'])} dòng dự báo hãng")


if __name__ == "__main__":
    main()
