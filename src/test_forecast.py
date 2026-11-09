
import numpy as np
import pandas as pd
import pytest

from src import forecast


def test_forecast_series_returns_all_documented_models() -> None:
    months = np.arange(24, dtype=float)
    values = 100 + months * 2 + 15 * np.sin(2 * np.pi * months / 12)

    forecasts, scales = forecast._forecast_series(values, horizon=6)

    assert set(forecasts) == {"holt_winters", "sarima", "seasonal_naive"}
    assert set(scales) == set(forecasts)
    assert all(len(prediction) == 6 for prediction in forecasts.values())
    assert all(np.isfinite(prediction).all() for prediction in forecasts.values())
    assert all((prediction >= 0).all() for prediction in forecasts.values())


def test_forecast_rows_builds_backtest_and_future_at_each_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    months = pd.date_range("2022-01-01", "2023-12-01", freq="MS")
    demand = pd.DataFrame(
        [
            {
                "month_start": month,
                "company": company,
                "dealer_region": region,
                "units": 10 + month_index + company_index + region_index,
            }
            for month_index, month in enumerate(months)
            for company_index, company in enumerate(("A", "B"))
            for region_index, region in enumerate(("North", "South"))
        ]
    )

    def fixed_forecast(
        values: np.ndarray,
        horizon: int,
    ) -> tuple[dict[str, np.ndarray], dict[str, float]]:
        return (
            {
                model: np.full(horizon, 20.0)
                for model in ("holt_winters", "sarima", "seasonal_naive")
            },
            {model: 2.0 for model in ("holt_winters", "sarima", "seasonal_naive")},
        )

    monkeypatch.setattr(forecast, "_forecast_series", fixed_forecast)
    rows = forecast._forecast_rows(demand)

    assert len(rows) == 5 * 3 * 12
    backtest = [row for row in rows if row["is_backtest"]]
    future = [row for row in rows if not row["is_backtest"]]
    assert len(backtest) == 5 * 3 * 6
    assert len(future) == 5 * 3 * 6
    assert {row["month_start"].month for row in backtest} == set(range(7, 13))
    assert {row["month_start"].month for row in future} == set(range(1, 7))
    assert {row["level"] for row in rows} == {"total", "company", "region"}
    assert all(row["actual_units"] is not None for row in backtest)
    assert all(row["actual_units"] is None for row in future)


def test_forecast_rows_rejects_negative_demand() -> None:
    demand = pd.DataFrame(
        {
            "month_start": [pd.Timestamp("2022-01-01")],
            "company": ["A"],
            "dealer_region": ["North"],
            "units": [-1],
        }
    )

    with pytest.raises(ValueError, match="negative unit counts"):
        forecast._forecast_rows(demand)
