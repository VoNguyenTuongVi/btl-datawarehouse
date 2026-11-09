"""Generate monthly demand backtests and six-month-ahead forecasts."""

from __future__ import annotations

import os
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX

MONTHLY_DEMAND_QUERY = """
SELECT month_start, company, dealer_region, units
FROM v_monthly_demand
ORDER BY month_start, company, dealer_region
"""

UPSERT_FORECAST_QUERY = text(
    """
    INSERT INTO fact_demand_forecast (
        month_id, month_start, level, member, model_name,
        forecast_units, lower_80, upper_80, actual_units, is_backtest
    )
    VALUES (
        :month_id, :month_start, :level, :member, :model_name,
        :forecast_units, :lower_80, :upper_80, :actual_units, :is_backtest
    )
    ON CONFLICT (month_id, level, member, model_name)
    DO UPDATE SET
        forecast_units = EXCLUDED.forecast_units,
        lower_80 = EXCLUDED.lower_80,
        upper_80 = EXCLUDED.upper_80,
        actual_units = EXCLUDED.actual_units,
        is_backtest = EXCLUDED.is_backtest
    """
)

SEASONAL_PERIODS = 12
FORECAST_HORIZON = 6
BACKTEST_START = pd.Timestamp("2023-07-01")
BACKTEST_END = pd.Timestamp("2024-01-01")
INTERVAL_Z_VALUE = NormalDist().inv_cdf(0.90)


def _monthly_index(start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    """Return a complete month-start index with both endpoints included."""
    return pd.date_range(start=start, end=end, freq="MS")


def _forecast_series(
    values: np.ndarray,
    horizon: int,
) -> tuple[dict[str, np.ndarray], dict[str, float]]:
    """Fit Holt-Winters, seasonal SARIMA, and seasonal naive forecasts."""
    if len(values) < SEASONAL_PERIODS + 1:
        raise ValueError(
            f"At least {SEASONAL_PERIODS + 1} monthly observations are required; "
            f"received {len(values)}."
        )
    if horizon < 1:
        raise ValueError("Forecast horizon must be positive.")
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("Monthly demand must contain finite, non-negative values.")

    first_season = values[:SEASONAL_PERIODS]
    initial_level = float(first_season.mean())
    initial_seasonal = first_season - initial_level
    annual_changes = values[SEASONAL_PERIODS:] - values[:-SEASONAL_PERIODS]
    initial_trend = float(annual_changes.mean() / SEASONAL_PERIODS)

    model = ExponentialSmoothing(
        values,
        trend="add",
        seasonal="add",
        seasonal_periods=SEASONAL_PERIODS,
        initialization_method="known",
        initial_level=initial_level,
        initial_trend=initial_trend,
        initial_seasonal=initial_seasonal,
    )
    fitted = model.fit(optimized=True)
    holt_winters = np.asarray(fitted.forecast(horizon), dtype=float)
    sarima_fit = SARIMAX(
        values,
        order=(1, 0, 0),
        seasonal_order=(0, 1, 0, SEASONAL_PERIODS),
        enforce_stationarity=False,
        enforce_invertibility=False,
    ).fit(disp=False)
    sarima = np.asarray(sarima_fit.forecast(horizon), dtype=float)
    seasonal_naive = np.asarray(
        [values[-SEASONAL_PERIODS + step % SEASONAL_PERIODS] for step in range(horizon)],
        dtype=float,
    )

    fitted_values = np.asarray(fitted.fittedvalues, dtype=float)
    residuals = values[SEASONAL_PERIODS:] - fitted_values[SEASONAL_PERIODS:]
    residuals = residuals[np.isfinite(residuals)]
    if residuals.size == 0:
        raise ValueError("Holt-Winters did not produce residuals for interval estimation.")
    hw_residual_scale = float(np.sqrt(np.mean(np.square(residuals))))

    sarima_residuals = np.asarray(sarima_fit.resid, dtype=float)
    sarima_residuals = sarima_residuals[np.isfinite(sarima_residuals)]
    sarima_residual_scale = float(np.sqrt(np.mean(np.square(sarima_residuals))))
    naive_residuals = annual_changes[np.isfinite(annual_changes)]
    if naive_residuals.size == 0:
        raise ValueError("Seasonal naive did not produce residuals for interval estimation.")
    naive_residual_scale = float(np.sqrt(np.mean(np.square(naive_residuals))))

    return (
        {
            "holt_winters": np.maximum(holt_winters, 0),
            "sarima": np.maximum(sarima, 0),
            "seasonal_naive": np.maximum(seasonal_naive, 0),
        },
        {
            "holt_winters": hw_residual_scale,
            "sarima": sarima_residual_scale,
            "seasonal_naive": naive_residual_scale,
        },
    )


def _intervals(
    predictions: np.ndarray,
    residual_scale: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Estimate 80% intervals using a normal residual approximation."""
    horizons = np.arange(1, len(predictions) + 1, dtype=float)
    margin = INTERVAL_Z_VALUE * residual_scale * np.sqrt(horizons)
    return np.maximum(predictions - margin, 0), predictions + margin


def _forecast_rows(
    demand: pd.DataFrame,
) -> list[dict[str, Any]]:
    if demand.empty:
        raise ValueError("v_monthly_demand returned no rows.")
    required_columns = {"month_start", "company", "dealer_region", "units"}
    missing_columns = required_columns.difference(demand.columns)
    if missing_columns:
        raise ValueError(f"Monthly demand query is missing columns: {sorted(missing_columns)}")

    data = demand.copy()
    data["month_start"] = pd.to_datetime(data["month_start"]).dt.to_period("M").dt.to_timestamp()
    if data["month_start"].isna().any() or data["units"].isna().any():
        raise ValueError("Monthly demand contains null dates or unit counts.")
    if (data["units"] < 0).any():
        raise ValueError("Monthly demand contains negative unit counts.")

    first_month = data["month_start"].min()
    last_month = data["month_start"].max()
    training_end = BACKTEST_START - pd.offsets.MonthBegin(1)
    training_index = _monthly_index(first_month, training_end)
    backtest_index = _monthly_index(BACKTEST_START, BACKTEST_END - pd.offsets.MonthBegin(1))
    future_index = _monthly_index(
        last_month + pd.offsets.MonthBegin(1),
        last_month + pd.offsets.MonthBegin(FORECAST_HORIZON),
    )
    if len(training_index) < SEASONAL_PERIODS + 1:
        raise ValueError("The fixed Jul-Dec 2023 backtest needs at least 13 training months.")
    expected_backtest = _monthly_index(BACKTEST_START, BACKTEST_END - pd.offsets.MonthBegin(1))
    if not expected_backtest.isin(data["month_start"].unique()).all():
        raise ValueError("The DW must contain actual sales for every month from Jul-Dec 2023.")

    grouped = (
        data.groupby(["month_start", "company", "dealer_region"], dropna=False)["units"]
        .sum()
        .reset_index()
    )
    grouped["company"] = grouped["company"].fillna("Unknown")
    grouped["dealer_region"] = grouped["dealer_region"].fillna("Unknown")
    series_specs: list[tuple[str, str, pd.DataFrame]] = [
        ("total", "ALL", grouped[["month_start", "units"]].groupby("month_start", as_index=False).sum())
    ]
    for level, column in (("company", "company"), ("region", "dealer_region")):
        members = grouped.loc[grouped[column].notna(), column].drop_duplicates()
        for member in members:
            member_rows = grouped.loc[grouped[column] == member, ["month_start", "units"]]
            if member_rows.loc[member_rows["month_start"] <= training_end, "units"].sum() > 0:
                series_specs.append((level, str(member), member_rows))

    output: list[dict[str, Any]] = []
    for level, member, observations in series_specs:
        monthly = observations.groupby("month_start")["units"].sum()
        training = monthly.reindex(training_index, fill_value=0).to_numpy(dtype=float)
        actuals = monthly.reindex(backtest_index, fill_value=0).to_numpy(dtype=float)
        future_training = monthly.reindex(
            _monthly_index(first_month, last_month), fill_value=0
        ).to_numpy(dtype=float)

        try:
            backtest_predictions, backtest_scales = _forecast_series(training, len(backtest_index))
            future_predictions, future_scales = _forecast_series(
                future_training, FORECAST_HORIZON
            )
        except (ValueError, RuntimeError) as error:
            raise RuntimeError(f"Forecast failed for {level}={member!r}: {error}") from error

        for is_backtest, months, actual_values, predictions, scales in (
            (True, backtest_index, actuals, backtest_predictions, backtest_scales),
            (False, future_index, np.full(FORECAST_HORIZON, np.nan), future_predictions, future_scales),
        ):
            for model_name, values in predictions.items():
                lower, upper = _intervals(values, scales[model_name])
                for index, month_start in enumerate(months):
                    output.append(
                        {
                            "month_id": int(month_start.strftime("%Y%m")),
                            "month_start": month_start.date(),
                            "level": level,
                            "member": member,
                            "model_name": model_name,
                            "forecast_units": round(float(values[index]), 2),
                            "lower_80": round(float(lower[index]), 2),
                            "upper_80": round(float(upper[index]), 2),
                            "actual_units": (
                                round(float(actual_values[index]), 2) if is_backtest else None
                            ),
                            "is_backtest": is_backtest,
                        }
                    )
    return output


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "Set DATABASE_URL to a PostgreSQL SQLAlchemy URL, for example "
            "postgresql+psycopg2://user:password@localhost:5432/car_sales_dw."
        )
    if not database_url.startswith(("postgresql://", "postgresql+psycopg2://")):
        raise ValueError("DATABASE_URL must use PostgreSQL.")

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            demand = pd.read_sql(text(MONTHLY_DEMAND_QUERY), connection)
        rows = _forecast_rows(demand)
        with engine.begin() as connection:
            # Static dataset: keep exactly one forecast set so BI sums never double count.
            connection.execute(text("TRUNCATE fact_demand_forecast RESTART IDENTITY"))
            connection.execute(UPSERT_FORECAST_QUERY, rows)
    finally:
        engine.dispose()

    print(
        f"Loaded {len(rows)} forecast rows "
        f"({sum(row['is_backtest'] for row in rows)} backtest rows)."
    )


if __name__ == "__main__":
    main()
