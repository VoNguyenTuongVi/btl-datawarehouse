-- D1-D4: monthly quantity, revenue, ASP, growth, YTD, and seasonality.
WITH month_range AS (
    SELECT month_start FROM v_monthly_calendar
),
monthly_totals AS (
    SELECT r.month_start,
           COALESCE(SUM(d.units), 0)::numeric AS units,
           COALESCE(SUM(d.revenue), 0)::numeric AS revenue
    FROM month_range AS r
    LEFT JOIN v_monthly_demand AS d USING (month_start)
    GROUP BY r.month_start
),
metrics AS (
    SELECT month_start,
           units,
           revenue,
           revenue / NULLIF(units, 0) AS asp,
           ROUND(100 * (units - LAG(units) OVER month_order)
               / NULLIF(LAG(units) OVER month_order, 0), 2) AS units_mom_pct,
           ROUND(100 * (units - LAG(units, 12) OVER month_order)
               / NULLIF(LAG(units, 12) OVER month_order, 0), 2) AS units_yoy_pct,
           ROUND(100 * (revenue - LAG(revenue) OVER month_order)
               / NULLIF(LAG(revenue) OVER month_order, 0), 2) AS revenue_mom_pct,
           ROUND(100 * (revenue - LAG(revenue, 12) OVER month_order)
               / NULLIF(LAG(revenue, 12) OVER month_order, 0), 2) AS revenue_yoy_pct,
           SUM(units) OVER (
               PARTITION BY EXTRACT(YEAR FROM month_start)
               ORDER BY month_start
           ) AS units_ytd,
           SUM(revenue) OVER (
               PARTITION BY EXTRACT(YEAR FROM month_start)
               ORDER BY month_start
           ) AS revenue_ytd,
           AVG(units) OVER (PARTITION BY EXTRACT(MONTH FROM month_start))
               / NULLIF(AVG(units) OVER (), 0) AS seasonality_index
    FROM monthly_totals
    WINDOW month_order AS (ORDER BY month_start)
)
SELECT month_start,
       units,
       revenue,
       asp,
       units_mom_pct,
       units_yoy_pct,
       revenue_mom_pct,
       revenue_yoy_pct,
       units_ytd,
       revenue_ytd,
       ROUND(
           100 * (units_ytd - LAG(units_ytd, 12) OVER (ORDER BY month_start))
           / NULLIF(LAG(units_ytd, 12) OVER (ORDER BY month_start), 0),
           2
       ) AS units_ytd_yoy_pct,
       ROUND(
           100 * (revenue_ytd - LAG(revenue_ytd, 12) OVER (ORDER BY month_start))
           / NULLIF(LAG(revenue_ytd, 12) OVER (ORDER BY month_start), 0),
           2
       ) AS revenue_ytd_yoy_pct,
       seasonality_index
FROM metrics
ORDER BY month_start;

-- D1-D2: daily, weekly, monthly, quarterly, and yearly totals.
SELECT 'day'::text AS period_grain,
       d.full_date AS period_start,
       SUM(f.quantity)::numeric AS units,
       SUM(f.price)::numeric AS revenue
FROM fact_car_sales AS f
JOIN dim_date AS d ON f.date_id = d.date_id
GROUP BY d.full_date
UNION ALL
SELECT 'week',
       date_trunc('week', d.full_date)::date,
       SUM(f.quantity)::numeric,
       SUM(f.price)::numeric
FROM fact_car_sales AS f
JOIN dim_date AS d ON f.date_id = d.date_id
GROUP BY date_trunc('week', d.full_date)
UNION ALL
SELECT 'year',
       make_date(d.year, 1, 1),
       SUM(f.quantity)::numeric,
       SUM(f.price)::numeric
FROM fact_car_sales AS f
JOIN dim_date AS d ON f.date_id = d.date_id
GROUP BY d.year
ORDER BY period_grain, period_start;

-- D4: quarterly quantity and revenue growth.
WITH quarterly_totals AS (
    SELECT d.year,
           d.quarter,
           make_date(d.year, ((d.quarter - 1) * 3) + 1, 1) AS quarter_start,
           SUM(f.quantity)::numeric AS units,
           SUM(f.price)::numeric AS revenue
    FROM fact_car_sales AS f
    JOIN dim_date AS d ON f.date_id = d.date_id
    GROUP BY d.year, d.quarter
)
SELECT year,
       quarter,
       quarter_start,
       units,
       revenue,
       ROUND(100 * (units - LAG(units) OVER quarter_order)
           / NULLIF(LAG(units) OVER quarter_order, 0), 2) AS units_qoq_pct,
       ROUND(100 * (units - LAG(units, 4) OVER quarter_order)
           / NULLIF(LAG(units, 4) OVER quarter_order, 0), 2) AS units_yoy_pct,
       ROUND(100 * (revenue - LAG(revenue) OVER quarter_order)
           / NULLIF(LAG(revenue) OVER quarter_order, 0), 2) AS revenue_qoq_pct,
       ROUND(100 * (revenue - LAG(revenue, 4) OVER quarter_order)
           / NULLIF(LAG(revenue, 4) OVER quarter_order, 0), 2) AS revenue_yoy_pct
FROM quarterly_totals
WINDOW quarter_order AS (ORDER BY year, quarter)
ORDER BY year, quarter;

-- D5-D6: share, units, revenue, ASP, and YoY by body style, color, and region.
SELECT month_start,
       dimension_name,
       dimension_value,
       units,
       revenue,
       revenue / NULLIF(units, 0) AS asp,
       ROUND(
           100 * units / NULLIF(SUM(units) OVER (PARTITION BY month_start, dimension_name), 0),
           2
       ) AS units_share_pct,
       ROUND(
           100 * (units - LAG(units, 12) OVER dimension_order)
           / NULLIF(LAG(units, 12) OVER dimension_order, 0),
           2
       ) AS units_yoy_pct
FROM v_monthly_dimension_demand
WHERE dimension_name IN ('body_style', 'color', 'dealer_region')
WINDOW dimension_order AS (
    PARTITION BY dimension_name, dimension_value
    ORDER BY month_start
)
ORDER BY dimension_name, dimension_value, month_start;

-- D8: average units per selling day and weekday index.
WITH weekday_totals AS (
    SELECT d.day_of_week,
           SUM(f.quantity)::numeric AS units,
           COUNT(DISTINCT d.full_date)::numeric AS selling_days
    FROM fact_car_sales AS f
    JOIN dim_date AS d ON f.date_id = d.date_id
    GROUP BY d.day_of_week
),
weekday_averages AS (
    SELECT day_of_week,
           units,
           selling_days,
           units / NULLIF(selling_days, 0) AS units_per_selling_day
    FROM weekday_totals
)
SELECT day_of_week,
       units,
       selling_days,
       units_per_selling_day,
       units_per_selling_day
           / NULLIF(AVG(units_per_selling_day) OVER (), 0) AS weekday_index
FROM weekday_averages
ORDER BY day_of_week;

-- D9: monthly coefficient of variation by company, with zero-sales months included.
WITH month_range AS (
    SELECT month_start FROM v_monthly_calendar
),
companies AS (
    SELECT DISTINCT company
    FROM v_monthly_demand
),
monthly_company AS (
    SELECT month_start, company, SUM(units) AS units
    FROM v_monthly_demand
    GROUP BY month_start, company
),
complete_series AS (
    SELECT c.company,
           r.month_start,
           COALESCE(m.units, 0) AS units
    FROM companies AS c
    CROSS JOIN month_range AS r
    LEFT JOIN monthly_company AS m
        ON m.company = c.company
       AND m.month_start = r.month_start
)
SELECT company,
       ROUND(AVG(units), 1) AS mean_units,
       ROUND(STDDEV_POP(units) / NULLIF(AVG(units), 0), 3) AS cv
FROM complete_series
GROUP BY company
ORDER BY cv DESC;

-- D10: top-10 model share and company-level Herfindahl-Hirschman Index.
WITH shares AS (
    SELECT dimension_name,
           dimension_value,
           SUM(units)::numeric AS units,
           SUM(units)::numeric
               / NULLIF(SUM(SUM(units)) OVER (PARTITION BY dimension_name), 0) AS share
    FROM v_monthly_dimension_demand
    WHERE dimension_name IN ('model', 'company')
    GROUP BY dimension_name, dimension_value
),
ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY dimension_name
               ORDER BY units DESC, dimension_value
           ) AS position
    FROM shares
)
SELECT dimension_name,
       CASE
           WHEN dimension_name = 'model'
               THEN SUM(share) FILTER (WHERE position <= 10)
       END AS top_10_model_share,
       CASE
           WHEN dimension_name = 'company'
               THEN SUM(share * share)
       END AS company_hhi
FROM ranked
GROUP BY dimension_name;

-- D11: quantity, revenue, ASP, and price-to-income by customer income quartile.
WITH customer_segments AS (
    SELECT customer_id,
           annual_income,
           NTILE(4) OVER (ORDER BY annual_income, customer_id) AS income_quartile
    FROM dim_customer
    WHERE annual_income IS NOT NULL
)
SELECT s.income_quartile,
       COUNT(f.car_id) AS units,
       SUM(f.price) AS revenue,
       SUM(f.price)::numeric / NULLIF(COUNT(f.car_id), 0) AS asp,
       AVG(f.price::numeric / NULLIF(s.annual_income, 0)) AS avg_price_to_income
FROM customer_segments AS s
JOIN fact_car_sales AS f USING (customer_id)
GROUP BY s.income_quartile
ORDER BY s.income_quartile;

-- D12-D17: monthly metrics for company, model, transmission, engine,
-- dealer, and gender. The dense calendar makes every LAG refer to the
-- matching month, including for models with zero-sales months.
WITH month_range AS (
    SELECT month_start FROM v_monthly_calendar
),
dimension_values AS (
    SELECT DISTINCT dimension_name, dimension_value
    FROM v_monthly_dimension_demand
    WHERE dimension_name IN (
        'company', 'model', 'transmission', 'engine', 'dealer_name', 'gender'
    )
),
monthly_values AS (
    SELECT month_start,
           dimension_name,
           dimension_value,
           SUM(units)::numeric AS units,
           SUM(revenue)::numeric AS revenue
    FROM v_monthly_dimension_demand
    WHERE dimension_name IN (
        'company', 'model', 'transmission', 'engine', 'dealer_name', 'gender'
    )
    GROUP BY month_start, dimension_name, dimension_value
),
dense_series AS (
    SELECT r.month_start,
           v.dimension_name,
           v.dimension_value,
           COALESCE(m.units, 0)::numeric AS units,
           COALESCE(m.revenue, 0)::numeric AS revenue
    FROM month_range AS r
    CROSS JOIN dimension_values AS v
    LEFT JOIN monthly_values AS m
        ON m.month_start = r.month_start
       AND m.dimension_name = v.dimension_name
       AND m.dimension_value = v.dimension_value
),
metrics AS (
    SELECT month_start,
           dimension_name,
           dimension_value,
           units,
           revenue,
           revenue / NULLIF(units, 0) AS asp,
           ROUND(
               100 * units
               / NULLIF(SUM(units) OVER (PARTITION BY month_start, dimension_name), 0),
               2
           ) AS units_share_pct,
           ROUND(
               100 * (units - LAG(units) OVER dimension_order)
               / NULLIF(LAG(units) OVER dimension_order, 0),
               2
           ) AS units_mom_pct,
           ROUND(
               100 * (units - LAG(units, 12) OVER dimension_order)
               / NULLIF(LAG(units, 12) OVER dimension_order, 0),
               2
           ) AS units_yoy_pct,
           ROUND(
               100 * (revenue - LAG(revenue, 12) OVER dimension_order)
               / NULLIF(LAG(revenue, 12) OVER dimension_order, 0),
               2
           ) AS revenue_yoy_pct,
           units - LAG(units, 12) OVER dimension_order AS units_yoy_delta,
           SUM(revenue) OVER (
               PARTITION BY dimension_name, dimension_value, EXTRACT(YEAR FROM month_start)
               ORDER BY month_start
           ) AS revenue_ytd,
           RANK() OVER (
               PARTITION BY dimension_name, month_start
               ORDER BY units DESC, dimension_value
           ) AS monthly_rank,
           CASE
               WHEN dimension_name = 'transmission'
               THEN 100.0 * SUM(units) FILTER (
                   WHERE LOWER(dimension_value) = 'auto'
               ) OVER (PARTITION BY month_start)
               / NULLIF(SUM(units) OVER (PARTITION BY month_start), 0)
           END AS auto_share_pct
    FROM dense_series
    WINDOW dimension_order AS (
        PARTITION BY dimension_name, dimension_value
        ORDER BY month_start
    )
)
SELECT *,
       auto_share_pct
           - LAG(auto_share_pct, 12) OVER (
               PARTITION BY dimension_name
               ORDER BY month_start
           ) AS auto_share_change_pp
FROM metrics
ORDER BY dimension_name, dimension_value, month_start;

-- D13: five models with the largest gains and losses versus the same month last year.
WITH model_changes AS (
    SELECT dimension_value AS model,
           SUM(units_yoy_delta)::numeric AS units_yoy_delta
    FROM (
        SELECT month_start,
               dimension_value,
               units - LAG(units, 12) OVER (
                   PARTITION BY dimension_value ORDER BY month_start
               ) AS units_yoy_delta
        FROM (
            SELECT months.month_start,
                   models.dimension_value,
                   COALESCE(demand.units, 0) AS units
            FROM v_monthly_calendar AS months
            CROSS JOIN (
                SELECT DISTINCT dimension_value
                FROM v_monthly_dimension_demand
                WHERE dimension_name = 'model'
            ) AS models
            LEFT JOIN v_monthly_dimension_demand AS demand
                ON demand.month_start = months.month_start
               AND demand.dimension_name = 'model'
               AND demand.dimension_value = models.dimension_value
        ) AS dense_models
    ) AS model_lags
    WHERE units_yoy_delta IS NOT NULL
    GROUP BY dimension_value
),
ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (ORDER BY units_yoy_delta DESC, model) AS growth_rank,
           ROW_NUMBER() OVER (ORDER BY units_yoy_delta ASC, model) AS decline_rank
    FROM model_changes
)
SELECT model,
       units_yoy_delta,
       CASE
           WHEN growth_rank <= 5 THEN 'top_growth'
           WHEN decline_rank <= 5 THEN 'top_decline'
       END AS movement
FROM ranked
WHERE growth_rank <= 5 OR decline_rank <= 5
ORDER BY units_yoy_delta DESC;

-- D16: percent of dealers with positive YoY growth, by month.
WITH dealer_growth AS (
    SELECT month_start,
           dimension_value AS dealer_name,
           units_yoy_pct,
           monthly_rank
    FROM (
        SELECT month_start,
               dimension_value,
               units,
               ROUND(
                   100 * (units - LAG(units, 12) OVER dealer_order)
                   / NULLIF(LAG(units, 12) OVER dealer_order, 0),
                   2
               ) AS units_yoy_pct,
               RANK() OVER (PARTITION BY month_start ORDER BY units DESC) AS monthly_rank
        FROM (
            SELECT months.month_start,
                   dealers.dimension_value,
                   COALESCE(demand.units, 0) AS units
            FROM v_monthly_calendar AS months
            CROSS JOIN (
                SELECT DISTINCT dimension_value
                FROM v_monthly_dimension_demand
                WHERE dimension_name = 'dealer_name'
            ) AS dealers
            LEFT JOIN v_monthly_dimension_demand AS demand
                ON demand.month_start = months.month_start
               AND demand.dimension_name = 'dealer_name'
               AND demand.dimension_value = dealers.dimension_value
        ) AS dense_dealers
        WINDOW dealer_order AS (
            PARTITION BY dimension_value ORDER BY month_start
        )
    ) AS ranked_dealers
)
SELECT month_start,
       COUNT(*) AS dealer_count,
       COUNT(*) FILTER (WHERE units_yoy_pct > 0) AS growing_dealer_count,
       COUNT(*) FILTER (WHERE units_yoy_pct > 0)::numeric
           / NULLIF(COUNT(units_yoy_pct), 0) AS dealers_growing_pct
FROM dealer_growth
GROUP BY month_start
ORDER BY month_start;

-- F2-F8: company backtest scores; FVA > 0 means better than seasonal naive.
WITH model_scores AS (
    SELECT model_name,
           100.0 * SUM(ABS(actual_units - forecast_units))
               / NULLIF(SUM(actual_units), 0) AS wape_pct,
           100.0 * AVG(
               ABS(actual_units - forecast_units) / NULLIF(actual_units, 0)
           ) FILTER (WHERE actual_units > 0) AS mape_pct,
           AVG(ABS(actual_units - forecast_units)) AS mae,
           SQRT(AVG(POWER(actual_units - forecast_units, 2))) AS rmse,
           100.0 * SUM(forecast_units - actual_units)
               / NULLIF(SUM(actual_units), 0) AS bias_pct,
           SUM(actual_units - forecast_units)
               / NULLIF(AVG(ABS(actual_units - forecast_units)), 0) AS tracking_signal,
           100.0 * COUNT(*) FILTER (
               WHERE actual_units BETWEEN lower_80 AND upper_80
           ) / NULLIF(COUNT(*), 0) AS coverage_pct
    FROM fact_demand_forecast
    WHERE level = 'company'
      AND is_backtest
    GROUP BY model_name
)
SELECT scores.model_name,
       ROUND(scores.wape_pct, 2) AS wape_pct,
       ROUND(100 - scores.wape_pct, 2) AS accuracy_pct,
       ROUND(scores.mape_pct, 2) AS mape_pct,
       ROUND(scores.mae, 2) AS mae,
       ROUND(scores.rmse, 2) AS rmse,
       ROUND(scores.bias_pct, 2) AS bias_pct,
       ROUND(scores.tracking_signal, 2) AS tracking_signal,
       ROUND(scores.coverage_pct, 1) AS coverage_pct,
       ROUND(baseline.wape_pct - scores.wape_pct, 2) AS fva_pct
FROM model_scores AS scores
CROSS JOIN model_scores AS baseline
WHERE baseline.model_name = 'seasonal_naive'
ORDER BY scores.wape_pct;

-- S1: forecast growth versus actual sales in the same month of the prior year.
WITH actuals AS (
    SELECT 'total'::text AS level,
           'ALL'::text AS member,
           month_start,
           SUM(units)::numeric AS units
    FROM v_monthly_demand
    GROUP BY month_start
    UNION ALL
    SELECT 'company', company, month_start, SUM(units)::numeric
    FROM v_monthly_demand
    GROUP BY company, month_start
    UNION ALL
    SELECT 'region', COALESCE(dealer_region, 'Unknown'), month_start, SUM(units)::numeric
    FROM v_monthly_demand
    GROUP BY dealer_region, month_start
)
SELECT forecast.month_start,
       forecast.level,
       forecast.member,
       forecast.forecast_units,
       actual.units AS prior_year_units,
       (forecast.forecast_units - actual.units) / NULLIF(actual.units, 0) AS forecast_growth_pct
FROM fact_demand_forecast AS forecast
LEFT JOIN actuals AS actual
    ON actual.level = forecast.level
   AND actual.member = forecast.member
   AND actual.month_start = (forecast.month_start - INTERVAL '1 year')::date
WHERE NOT forecast.is_backtest;

-- S2: allocate total forecasts to regions using the latest six months' sales mix.
WITH last_six_months AS (
    SELECT DISTINCT month_id
    FROM v_monthly_demand
    ORDER BY month_id DESC
    LIMIT 6
),
region_shares AS (
    SELECT dealer_region,
           SUM(units)::numeric / NULLIF(SUM(SUM(units)) OVER (), 0) AS share_6m
    FROM v_monthly_demand
    WHERE month_id IN (SELECT month_id FROM last_six_months)
    GROUP BY dealer_region
),
next_forecast AS (
    SELECT month_start, forecast_units
    FROM fact_demand_forecast
    WHERE level = 'total'
      AND NOT is_backtest
      AND model_name = 'sarima'
    ORDER BY month_start
    LIMIT 1
)
SELECT forecast.month_start,
       shares.dealer_region,
       ROUND(shares.share_6m * 100, 2) AS share_pct,
       ROUND(shares.share_6m * forecast.forecast_units) AS allocated_units
FROM region_shares AS shares
CROSS JOIN next_forecast AS forecast
ORDER BY allocated_units DESC;

-- S3/S4/S6: set the what-if inputs below, then calculate order units and revenue.
WITH parameters AS (
    SELECT 0.0::numeric AS demand_change,
           1.0::numeric AS safety_factor
),
history AS (
    SELECT company AS member,
           month_start,
           SUM(units)::numeric AS units,
           SUM(revenue)::numeric AS revenue
    FROM v_monthly_demand
    GROUP BY company, month_start
),
history_cv AS (
    SELECT companies.company AS member,
           STDDEV_POP(COALESCE(history.units, 0))
               / NULLIF(AVG(COALESCE(history.units, 0)), 0) AS cv
    FROM (SELECT DISTINCT company FROM history) AS companies
    CROSS JOIN v_monthly_calendar AS months
    LEFT JOIN history
        ON history.member = companies.company
       AND history.month_start = months.month_start
    GROUP BY companies.company
),
history_metrics AS (
    SELECT full_history.member,
           full_history.cv,
           recent_history.asp
    FROM (
        SELECT member, cv
        FROM history_cv
    ) AS full_history
    LEFT JOIN (
        SELECT member,
               SUM(revenue) / NULLIF(SUM(units), 0) AS asp
        FROM history
        WHERE month_start >= (
            SELECT MAX(month_start) - INTERVAL '5 months' FROM history
        )
        GROUP BY member
    ) AS recent_history USING (member)
)
SELECT forecast.month_start,
       forecast.member AS company,
       forecast.forecast_units,
       history_metrics.cv,
       forecast.forecast_units
           * (1 + parameters.demand_change)
           * (1 + parameters.safety_factor * COALESCE(history_metrics.cv, 0))
           AS recommended_order,
       forecast.forecast_units
           * (1 + parameters.demand_change)
           * history_metrics.asp AS projected_revenue
FROM fact_demand_forecast AS forecast
LEFT JOIN history_metrics ON history_metrics.member = forecast.member
CROSS JOIN parameters
WHERE forecast.level = 'company'
  AND NOT forecast.is_backtest;

-- S5: normalized priority ranking; tune weights to sum to 1.
WITH parameters AS (
    SELECT 0.25::numeric AS growth_weight,
           0.25::numeric AS share_weight,
           0.25::numeric AS stability_weight,
           0.25::numeric AS accuracy_weight
),
company_variation AS (
    SELECT companies.dimension_value AS company,
           STDDEV_POP(COALESCE(dense.units, 0))
               / NULLIF(AVG(COALESCE(dense.units, 0)), 0) AS demand_cv
    FROM (
        SELECT DISTINCT dimension_value
        FROM v_monthly_dimension_demand
        WHERE dimension_name = 'company'
    ) AS companies
    CROSS JOIN v_monthly_calendar AS months
    LEFT JOIN v_monthly_dimension_demand AS dense
        ON dense.dimension_name = 'company'
       AND dense.dimension_value = companies.dimension_value
       AND dense.month_start = months.month_start
    GROUP BY companies.dimension_value
),
company_metrics AS (
    SELECT demand.dimension_value AS company,
           SUM(demand.units)::numeric
               / NULLIF(SUM(SUM(demand.units)) OVER (), 0) AS units_share,
           variation.demand_cv,
           SUM(demand.units) FILTER (
               WHERE demand.month_start = (
                   SELECT MAX(month_start) FROM v_monthly_dimension_demand
               )
           ) AS latest_units,
           SUM(demand.units) FILTER (
               WHERE demand.month_start = (
                   SELECT MAX(month_start) - INTERVAL '12 months'
                   FROM v_monthly_dimension_demand
               )
           ) AS prior_year_units
    FROM v_monthly_dimension_demand AS demand
    JOIN company_variation AS variation
        ON variation.company = demand.dimension_value
    WHERE demand.dimension_name = 'company'
    GROUP BY demand.dimension_value, variation.demand_cv
),
accuracy AS (
    SELECT member AS company,
           1 - SUM(ABS(actual_units - forecast_units))
               / NULLIF(SUM(actual_units), 0) AS forecast_accuracy
    FROM fact_demand_forecast
    WHERE level = 'company'
      AND is_backtest
      AND model_name = 'sarima'
    GROUP BY member
),
raw_scores AS (
    SELECT metrics.company,
           metrics.units_share,
           COALESCE(metrics.latest_units - metrics.prior_year_units, 0)::numeric
               / NULLIF(metrics.prior_year_units, 0) AS growth,
           1 - COALESCE(metrics.demand_cv, 0) AS stability,
           COALESCE(accuracy.forecast_accuracy, 0) AS accuracy
    FROM company_metrics AS metrics
    LEFT JOIN accuracy USING (company)
),
normalized AS (
    SELECT *,
           (growth - MIN(growth) OVER ())
               / NULLIF(MAX(growth) OVER () - MIN(growth) OVER (), 0) AS growth_score,
           (units_share - MIN(units_share) OVER ())
               / NULLIF(MAX(units_share) OVER () - MIN(units_share) OVER (), 0) AS share_score,
           (stability - MIN(stability) OVER ())
               / NULLIF(MAX(stability) OVER () - MIN(stability) OVER (), 0) AS stability_score,
           (accuracy - MIN(accuracy) OVER ())
               / NULLIF(MAX(accuracy) OVER () - MIN(accuracy) OVER (), 0) AS accuracy_score
    FROM raw_scores
)
SELECT company,
       COALESCE(growth_score, 0) * growth_weight
           + COALESCE(share_score, 0) * share_weight
           + COALESCE(stability_score, 0) * stability_weight
           + COALESCE(accuracy_score, 0) * accuracy_weight AS priority_score
FROM normalized
CROSS JOIN parameters
ORDER BY priority_score DESC;

-- Q6: observed months versus all months between the first and last sale.
WITH date_bounds AS (
    SELECT MIN(full_date) AS first_date,
           MAX(full_date) AS last_date
    FROM dim_date
)
SELECT bounds.first_date,
       bounds.last_date,
       (
           SELECT COUNT(DISTINCT date_trunc('month', full_date))
           FROM dim_date
       ) AS months_with_sales,
       (
           SELECT COUNT(*)
           FROM generate_series(
               date_trunc('month', bounds.first_date),
               date_trunc('month', bounds.last_date),
               INTERVAL '1 month'
           )
       ) AS months_in_range
FROM date_bounds AS bounds;
