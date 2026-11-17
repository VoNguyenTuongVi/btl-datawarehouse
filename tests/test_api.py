"""HTTP + SQL integration: DB changes must be visible without exporting JSON.

Uses an in-memory SQLite database with the same queried columns, not mocked SQL
responses. PostgreSQL-specific isolation/permissions still require a real PG run.
"""
import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

from src.api import create_app


@pytest.fixture
def engine():
    sqlite3.register_converter("BOOLEAN", lambda value: bool(int(value)))
    db = create_engine("sqlite://", poolclass=StaticPool,
                       connect_args={"check_same_thread": False, "detect_types": sqlite3.PARSE_DECLTYPES})

    @event.listens_for(db, "connect")
    def prepare(connection, _):
        connection.create_function("to_char", 2, lambda value, fmt: str(value)[:7])
        connection.execute("ATTACH DATABASE ':memory:' AS mart")

    definitions = [
        "CREATE TABLE dim_date (date_id INT, year INT, month INT)",
        "CREATE TABLE dim_car (car_key INT, company TEXT)",
        "CREATE TABLE fact_car_sales (date_id INT, car_key INT, quantity INT, price NUMERIC)",
        """CREATE TABLE fact_demand_forecast (month_id INT, level TEXT, member TEXT,
        model_name TEXT, forecast_units NUMERIC, actual_units NUMERIC,
        lower_80 NUMERIC, upper_80 NUMERIC, is_backtest BOOLEAN)""",
        """CREATE TABLE mart.kpi_parameters (id INT, main_model TEXT, target_growth NUMERIC,
        wape_threshold NUMERIC, bias_threshold NUMERIC)""",
        """CREATE TABLE mart.kpi_monthly_overview (month_start TEXT, year INT, units NUMERIC,
        revenue NUMERIC, asp NUMERIC, units_py NUMERIC, target_units NUMERIC,
        units_mom_pct NUMERIC, units_yoy_pct NUMERIC, seasonality_index_2y NUMERIC)""",
        """CREATE TABLE mart.forecast_series (month_start TEXT, level TEXT, member TEXT,
        model_name TEXT, series_type TEXT, actual_units NUMERIC, forecast_units NUMERIC,
        lower_80 NUMERIC, upper_80 NUMERIC)""",
        """CREATE TABLE mart.forecast_accuracy (level TEXT, member TEXT, model_name TEXT,
        n_points INT, actual_total NUMERIC, abs_error_total NUMERIC, error_total NUMERIC,
        n_in_interval INT)""",
        """CREATE TABLE mart.kpi_dimension_summary (dimension_value TEXT, parent_value TEXT,
        dimension_name TEXT, year INT, units NUMERIC, units_share_pct NUMERIC,
        units_yoy_pct NUMERIC, revenue NUMERIC, revenue_share_pct NUMERIC, revenue_yoy_pct NUMERIC)""",
        """CREATE TABLE mart.kpi_annual_summary (year INT, units NUMERIC, revenue NUMERIC,
        asp NUMERIC, units_yoy_pct NUMERIC, revenue_yoy_pct NUMERIC, target_units NUMERIC,
        units_target_status TEXT)""",
        "CREATE TABLE mart.dq_checks (check_code TEXT, check_name TEXT, metric_value NUMERIC, passed BOOLEAN, detail TEXT)",
        "CREATE TABLE mart.v_sales (year INT, dealer_name TEXT, dealer_region TEXT, units NUMERIC, revenue NUMERIC)",
    ]
    seeds = [
        "INSERT INTO dim_date VALUES (1, 2025, 1), (2, 2025, 2)",
        "INSERT INTO dim_car VALUES (1, 'A')",
        "INSERT INTO fact_car_sales VALUES (1, 1, 10, 1000), (2, 1, 20, 2000)",
        "INSERT INTO fact_demand_forecast VALUES (202601, 'company', 'A', 'holt_winters', 15, NULL, 10, 20, 0), (202601, 'company', 'A', 'sarima', 12, NULL, 8, 16, 0), (202502, 'company', 'A', 'sarima', 18, 20, 10, 25, 1)",
        "INSERT INTO mart.kpi_parameters VALUES (1, 'holt_winters', 0.08, 0.25, 0.1)",
        "INSERT INTO mart.kpi_monthly_overview VALUES ('2025-01-01', 2025, 10, 1000, 100, 8, 9, NULL, 0.25, 1)",
        "INSERT INTO mart.forecast_series VALUES ('2026-01-01', 'total', 'ALL', 'holt_winters', 'Dự báo', NULL, 15, 10, 20)",
        "INSERT INTO mart.forecast_accuracy VALUES ('company', 'A', 'sarima', 1, 20, 2, -2, 1)",
        "INSERT INTO mart.kpi_dimension_summary VALUES ('A', NULL, 'company', 2025, 30, 1, NULL, 3000, 1, NULL), ('X', 'A', 'model', 2025, 30, 1, NULL, 3000, 1, NULL), ('West', NULL, 'dealer_region', 2025, 30, 1, NULL, 3000, 1, NULL)",
        "INSERT INTO mart.kpi_annual_summary VALUES (2025, 30, 3000, 100, NULL, NULL, 32, 'Chưa đạt')",
        "INSERT INTO mart.dq_checks VALUES ('Q1', 'Rows', 30, 1, 'OK')",
        "INSERT INTO mart.v_sales VALUES (2025, 'Dealer A', 'West', 30, 3000)",
    ]
    with db.begin() as connection:
        for sql in definitions + seeds:
            connection.execute(text(sql))
    yield db
    db.dispose()


def test_reload_reads_committed_database_changes_for_dss_and_main(engine):
    with TestClient(create_app(engine)) as client:
        first = client.get("/api/dashboard")
        assert first.status_code == 200
        before = first.json()
        assert before["dss"]["history"][0]["units"] == 10
        assert before["dss"]["forecasts"][0]["forecast_units"] == 15
        assert before["dss"]["default_month"] == 202601
        assert before["dss"]["default_model"] == "holt_winters"
        assert before["latest_year"] == 2025
        assert before["parameters"]["wape_threshold"] == 0.25
        assert len(before["dss"]["cases"]) == 9
        with engine.begin() as connection:
            connection.execute(text("UPDATE fact_car_sales SET quantity=25, price=2500 WHERE date_id=1"))
            connection.execute(text("UPDATE fact_demand_forecast SET forecast_units=99 WHERE model_name='holt_winters'"))
            connection.execute(text("UPDATE mart.kpi_annual_summary SET units=45"))
            connection.execute(text("UPDATE mart.kpi_parameters SET main_model='sarima'"))
        second = client.get("/api/dashboard")
        assert second.status_code == 200
        after = second.json()
        assert after["dss"]["history"][0]["units"] == 25
        assert after["dss"]["history"][0]["revenue"] == 2500
        assert after["dss"]["forecasts"][0]["forecast_units"] == 99
        assert after["annual"][0]["units"] == 45
        assert after["dss"]["default_model"] == "sarima"
        assert after["exported_at"] != before["exported_at"]
        assert second.headers["cache-control"] == "no-store"
        assert "password" not in second.text.lower()
        assert "DATABASE_URL" not in second.text


def test_unavailable_schema_returns_sanitized_error_and_recovers(engine):
    with TestClient(create_app(engine)) as client:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE fact_demand_forecast RENAME TO saved_forecast"))
        response = client.get("/api/dashboard")
        assert response.status_code == 503
        assert response.json()["code"] == "DATABASE_UNAVAILABLE"
        assert "SELECT" not in response.text
        assert "Traceback" not in response.text
        assert response.headers["cache-control"] == "no-store"
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE saved_forecast RENAME TO fact_demand_forecast"))
        assert client.get("/api/dashboard").status_code == 200


def test_incomplete_data_does_not_fall_back_to_sample(engine):
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM fact_demand_forecast WHERE is_backtest=0"))
    with TestClient(create_app(engine)) as client:
        response = client.get("/api/dashboard")
        assert response.status_code == 409
        assert response.json()["code"] == "DATA_NOT_READY"
        assert "dss" not in response.json()


def test_nonfinite_database_numbers_fail_cleanly(engine):
    with engine.begin() as connection:
        connection.execute(text("UPDATE mart.kpi_annual_summary SET revenue=:value"), {"value": float("inf")})
    with TestClient(create_app(engine)) as client:
        assert client.get("/api/dashboard").status_code == 409


def test_get_does_not_write_database_and_health_does_not_leak_configuration(engine):
    statements = []

    @event.listens_for(engine, "before_cursor_execute")
    def record(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement.lstrip().upper())

    with TestClient(create_app(engine)) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok", "database": "connected"}
        assert client.get("/api/dashboard").status_code == 200
        assert all(statement.startswith(("SELECT", "WITH")) for statement in statements)
        assert client.post("/api/dashboard", json={"sql": "DELETE FROM fact_car_sales"}).status_code == 405


def test_built_frontend_and_api_use_same_origin_without_serving_project_files(engine, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<h1>Built frontend</h1>", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=not-for-browser", encoding="utf-8")
    with TestClient(create_app(engine, dist_dir=dist)) as client:
        assert "Built frontend" in client.get("/").text
        assert client.get("/api/dashboard").status_code == 200
        assert client.get("/.env").status_code == 404
        assert client.get("/data.json").status_code == 404
