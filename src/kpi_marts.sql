-- =====================================================================
-- LỚP MART: KPI ĐÃ TỔNG HỢP SẴN CHO POWER BI
-- =====================================================================
-- Mỗi bảng trong schema "mart" là kết quả của một nhóm KPI, ở đúng grain
-- dùng để vẽ biểu đồ. Power BI chỉ nạp các bảng này, không nạp bảng thô.
--
-- Quy ước:
--   * Tỷ lệ lưu dạng thập phân (0.05 = 5%) để Power BI định dạng %.
--   * Mỗi bảng có kèm cột thành phần (units_py, revenue_py, ...) để Power BI
--     tính lại tỷ lệ đúng khi gộp nhiều dòng (không cộng dồn phần trăm).
--   * Dữ liệu tĩnh 01/2022–12/2023; mọi mốc "gần nhất" lấy tháng cuối dataset.
--
-- Chạy sau forecast.py (cần fact_demand_forecast). Tham số đọc từ
-- mart.kpi_parameters, do src/build_marts.py ghi trước khi chạy file này.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS mart;

-- ---------------------------------------------------------------------
-- 0. THAM SỐ (1 dòng)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mart.kpi_parameters (
    id              INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    main_model      VARCHAR(50) NOT NULL DEFAULT 'sarima',
    target_growth   NUMERIC NOT NULL DEFAULT 0.05,
    wape_threshold  NUMERIC NOT NULL DEFAULT 0.20,
    bias_threshold  NUMERIC NOT NULL DEFAULT 0.05,
    safety_factor   NUMERIC NOT NULL DEFAULT 1.0,
    w_growth        NUMERIC NOT NULL DEFAULT 0.25,
    w_share         NUMERIC NOT NULL DEFAULT 0.25,
    w_stability     NUMERIC NOT NULL DEFAULT 0.25,
    w_accuracy      NUMERIC NOT NULL DEFAULT 0.25,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO mart.kpi_parameters (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
-- @@END_PARAMETERS (build_marts.py chạy phần trên, ghi tham số, rồi chạy cả file)

-- ---------------------------------------------------------------------
-- 1. VIEW CƠ SỞ: 1 dòng = 1 xe bán, đã gắn tháng và nhóm thu nhập
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.v_sales AS
WITH income_cut AS (
    SELECT percentile_cont(0.25) WITHIN GROUP (ORDER BY annual_income) AS p25,
           percentile_cont(0.50) WITHIN GROUP (ORDER BY annual_income) AS p50,
           percentile_cont(0.75) WITHIN GROUP (ORDER BY annual_income) AS p75
    FROM dim_customer
)
SELECT f.car_id,
       d.full_date,
       make_date(d.year, d.month, 1)                    AS month_start,
       d.year,
       d.quarter,
       d.month,
       EXTRACT(ISODOW FROM d.full_date)::int            AS dow_no,
       d.day_of_week,
       c.company, c.model, c.engine, c.transmission, c.color, c.body_style,
       de.dealer_name, de.dealer_region,
       cu.gender, cu.annual_income,
       CASE WHEN cu.annual_income <= ic.p25 THEN 1
            WHEN cu.annual_income <= ic.p50 THEN 2
            WHEN cu.annual_income <= ic.p75 THEN 3
            ELSE 4 END                                  AS income_quartile,
       f.quantity::numeric                              AS units,
       f.price::numeric                                 AS revenue
FROM fact_car_sales f
JOIN dim_date d      ON f.date_id = d.date_id
JOIN dim_car c       ON f.car_key = c.car_key
JOIN dim_dealer de   ON f.dealer_id = de.dealer_id
JOIN dim_customer cu ON f.customer_id = cu.customer_id
CROSS JOIN income_cut ic;

-- ---------------------------------------------------------------------
-- 2. DIM_MONTH: trục thời gian chung (lịch sử + các tháng dự báo)
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.dim_month CASCADE;
CREATE TABLE mart.dim_month AS
WITH bounds AS (
    SELECT MIN(month_start) AS first_month,
           GREATEST(MAX(month_start),
                    COALESCE((SELECT MAX(month_start) FROM fact_demand_forecast), MAX(month_start)))
               AS last_month,
           MAX(month_start) AS last_actual
    FROM mart.v_sales
)
SELECT gs::date                                         AS month_start,
       EXTRACT(YEAR FROM gs)::int                       AS year,
       EXTRACT(QUARTER FROM gs)::int                    AS quarter_no,
       'Q' || EXTRACT(QUARTER FROM gs)::int             AS quarter,
       EXTRACT(YEAR FROM gs)::int || '-Q' || EXTRACT(QUARTER FROM gs)::int AS year_quarter,
       EXTRACT(MONTH FROM gs)::int                      AS month_no,
       to_char(gs, 'Mon')                               AS month_name,
       (EXTRACT(YEAR FROM gs) * 100 + EXTRACT(MONTH FROM gs))::int AS year_month,
       to_char(gs, 'YYYY-MM')                           AS year_month_label,
       CASE WHEN gs > b.last_actual THEN 'Dự báo' ELSE 'Thực tế' END AS period_type
FROM bounds b,
     generate_series(b.first_month, b.last_month, INTERVAL '1 month') AS gs;
ALTER TABLE mart.dim_month ADD PRIMARY KEY (month_start);

DROP TABLE IF EXISTS mart.dim_year CASCADE;
CREATE TABLE mart.dim_year AS
SELECT DISTINCT year, year::text AS year_label,
       MIN(period_type) AS period_type   -- 'Dự báo' < 'Thực tế' theo thứ tự chữ
FROM mart.dim_month GROUP BY year ORDER BY year;
ALTER TABLE mart.dim_year ADD PRIMARY KEY (year);

-- ---------------------------------------------------------------------
-- 3. KPI THEO THÁNG (D1–D4, D7, D14, D16, mục tiêu) – 1 dòng/tháng
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.kpi_monthly_overview;
CREATE TABLE mart.kpi_monthly_overview AS
WITH p AS (SELECT * FROM mart.kpi_parameters WHERE id = 1),
months AS (SELECT month_start, year, month_no FROM mart.dim_month WHERE period_type = 'Thực tế'),
agg AS (
    SELECT month_start,
           SUM(units) AS units,
           SUM(revenue) AS revenue,
           SUM(units) FILTER (WHERE transmission = 'Auto') AS auto_units,
           COUNT(DISTINCT dealer_name) AS active_dealers,
           COUNT(DISTINCT full_date) AS selling_days
    FROM mart.v_sales GROUP BY month_start
),
m AS (
    SELECT mo.month_start, mo.year, mo.month_no,
           COALESCE(a.units, 0) AS units, COALESCE(a.revenue, 0) AS revenue,
           COALESCE(a.auto_units, 0) AS auto_units,
           COALESCE(a.active_dealers, 0) AS active_dealers,
           COALESCE(a.selling_days, 0) AS selling_days
    FROM months mo LEFT JOIN agg a USING (month_start)
),
dealer_m AS (   -- D16: đại lý tăng trưởng so với cùng kỳ
    SELECT cur.month_start,
           COUNT(*) FILTER (WHERE cur.u > COALESCE(py.u, 0)) AS dealers_growing,
           COUNT(*) AS dealers_compared
    FROM (SELECT month_start, dealer_name, SUM(units) AS u FROM mart.v_sales GROUP BY 1, 2) cur
    JOIN (SELECT month_start, dealer_name, SUM(units) AS u FROM mart.v_sales GROUP BY 1, 2) py
      ON py.dealer_name = cur.dealer_name
     AND py.month_start = (cur.month_start - INTERVAL '1 year')::date
    GROUP BY cur.month_start
),
w AS (
    SELECT m.*,
           LAG(units) OVER o AS units_pm,
           LAG(revenue) OVER o AS revenue_pm,
           LAG(units, 12) OVER o AS units_py,
           LAG(revenue, 12) OVER o AS revenue_py,
           LAG(auto_units, 12) OVER o AS auto_units_py,
           SUM(units) OVER (PARTITION BY year ORDER BY month_start) AS units_ytd,
           SUM(revenue) OVER (PARTITION BY year ORDER BY month_start) AS revenue_ytd,
           AVG(units) OVER (PARTITION BY year) AS avg_units_year,
           AVG(units) OVER (PARTITION BY month_no) AS avg_units_same_month,
           AVG(units) OVER () AS avg_units_all
    FROM m WINDOW o AS (ORDER BY month_start)
),
w2 AS (
    SELECT w.*,
           LAG(units_ytd, 12) OVER (ORDER BY month_start) AS units_ytd_py,
           LAG(revenue_ytd, 12) OVER (ORDER BY month_start) AS revenue_ytd_py
    FROM w
)
SELECT w2.month_start,
       w2.year,
       w2.units, w2.revenue,
       w2.revenue / NULLIF(w2.units, 0)                              AS asp,
       w2.units_pm, w2.revenue_pm, w2.units_py, w2.revenue_py,
       (w2.units - w2.units_pm) / NULLIF(w2.units_pm, 0)             AS units_mom_pct,
       (w2.revenue - w2.revenue_pm) / NULLIF(w2.revenue_pm, 0)       AS revenue_mom_pct,
       (w2.units - w2.units_py) / NULLIF(w2.units_py, 0)             AS units_yoy_pct,
       (w2.revenue - w2.revenue_py) / NULLIF(w2.revenue_py, 0)       AS revenue_yoy_pct,
       w2.units_ytd, w2.revenue_ytd, w2.units_ytd_py, w2.revenue_ytd_py,
       (w2.units_ytd - w2.units_ytd_py) / NULLIF(w2.units_ytd_py, 0)       AS units_ytd_yoy_pct,
       (w2.revenue_ytd - w2.revenue_ytd_py) / NULLIF(w2.revenue_ytd_py, 0) AS revenue_ytd_yoy_pct,
       w2.units / NULLIF(w2.avg_units_year, 0)                       AS seasonality_index,
       w2.avg_units_same_month / NULLIF(w2.avg_units_all, 0)         AS seasonality_index_2y,
       w2.units_py * (1 + p.target_growth)                           AS target_units,
       w2.revenue_py * (1 + p.target_growth)                         AS target_revenue,
       w2.units / NULLIF(w2.units_py * (1 + p.target_growth), 0) - 1     AS units_vs_target_pct,
       w2.revenue / NULLIF(w2.revenue_py * (1 + p.target_growth), 0) - 1 AS revenue_vs_target_pct,
       CASE WHEN w2.units_py IS NULL THEN NULL
            WHEN w2.units >= w2.units_py * (1 + p.target_growth) THEN 'Đạt' ELSE 'Không đạt' END
                                                                     AS units_target_status,
       CASE WHEN w2.revenue_py IS NULL THEN NULL
            WHEN w2.revenue >= w2.revenue_py * (1 + p.target_growth) THEN 'Đạt' ELSE 'Không đạt' END
                                                                     AS revenue_target_status,
       w2.auto_units,
       w2.auto_units / NULLIF(w2.units, 0)                           AS auto_share_pct,
       w2.auto_units / NULLIF(w2.units, 0)
           - w2.auto_units_py / NULLIF(w2.units_py, 0)               AS auto_share_change_pp,
       w2.active_dealers,
       w2.units / NULLIF(w2.active_dealers, 0)                       AS units_per_dealer,
       w2.selling_days,
       dm.dealers_growing, dm.dealers_compared,
       dm.dealers_growing::numeric / NULLIF(dm.dealers_compared, 0)  AS dealers_growing_pct
FROM w2
CROSS JOIN p
LEFT JOIN dealer_m dm USING (month_start)
ORDER BY w2.month_start;

-- ---------------------------------------------------------------------
-- 4. KPI THEO QUÝ (D4 QoQ) – 1 dòng/quý
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.kpi_quarterly;
CREATE TABLE mart.kpi_quarterly AS
WITH q AS (
    SELECT make_date(year, (quarter - 1) * 3 + 1, 1) AS quarter_start,
           year, quarter,
           SUM(units) AS units, SUM(revenue) AS revenue
    FROM mart.v_sales GROUP BY year, quarter
)
SELECT quarter_start, year, quarter AS quarter_no,
       year || '-Q' || quarter                                    AS year_quarter,
       units, revenue, revenue / NULLIF(units, 0)                 AS asp,
       LAG(units) OVER o                                          AS units_pq,
       LAG(revenue) OVER o                                        AS revenue_pq,
       LAG(units, 4) OVER o                                       AS units_py,
       LAG(revenue, 4) OVER o                                     AS revenue_py,
       (units - LAG(units) OVER o) / NULLIF(LAG(units) OVER o, 0)          AS units_qoq_pct,
       (revenue - LAG(revenue) OVER o) / NULLIF(LAG(revenue) OVER o, 0)    AS revenue_qoq_pct,
       (units - LAG(units, 4) OVER o) / NULLIF(LAG(units, 4) OVER o, 0)    AS units_yoy_pct,
       (revenue - LAG(revenue, 4) OVER o) / NULLIF(LAG(revenue, 4) OVER o, 0) AS revenue_yoy_pct
FROM q WINDOW o AS (ORDER BY quarter_start)
ORDER BY quarter_start;

-- ---------------------------------------------------------------------
-- 5. KPI THEO NGÀY (D1 ngày) – 1 dòng/ngày có bán
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.kpi_daily;
CREATE TABLE mart.kpi_daily AS
SELECT full_date, month_start, year, dow_no, day_of_week,
       SUM(units) AS units, SUM(revenue) AS revenue,
       SUM(revenue) / NULLIF(SUM(units), 0) AS asp
FROM mart.v_sales
GROUP BY full_date, month_start, year, dow_no, day_of_week
ORDER BY full_date;

-- ---------------------------------------------------------------------
-- 6. CHỈ SỐ NGÀY TRONG TUẦN (D8) – theo năm và gộp 2 năm
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.kpi_weekday;
CREATE TABLE mart.kpi_weekday AS
WITH d AS (
    SELECT year::text AS period, year, dow_no, day_of_week, units, revenue FROM mart.kpi_daily
    UNION ALL
    SELECT '2022–2023', NULL::int, dow_no, day_of_week, units, revenue FROM mart.kpi_daily
),
g AS (
    SELECT period, year, dow_no, day_of_week,
           COUNT(*) AS selling_days, SUM(units) AS units, SUM(revenue) AS revenue
    FROM d GROUP BY period, year, dow_no, day_of_week
)
SELECT g.*,
       units / NULLIF(selling_days, 0) AS avg_units_per_day,
       (units / NULLIF(selling_days, 0))
         / NULLIF(SUM(units) OVER (PARTITION BY period) / SUM(selling_days) OVER (PARTITION BY period), 0)
           AS weekday_index
FROM g ORDER BY period, dow_no;

-- ---------------------------------------------------------------------
-- 7. KPI THEO THÁNG × CHIỀU PHÂN TÍCH (D5, D6, D11–D17)
--    Dạng dài: dimension_name chọn chiều (Hãng, Mẫu xe, Hộp số, ...)
--    Lịch dày đủ 24 tháng cho mọi thành viên nên LAG luôn đúng tháng.
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.kpi_monthly_by_dimension;
CREATE TABLE mart.kpi_monthly_by_dimension AS
WITH long AS (
    SELECT month_start, 'company'::text AS dimension_name, company AS dimension_value, NULL::text AS parent_value, units, revenue FROM mart.v_sales
    UNION ALL SELECT month_start, 'model', model, company, units, revenue FROM mart.v_sales
    UNION ALL SELECT month_start, 'transmission', transmission, NULL, units, revenue FROM mart.v_sales
    UNION ALL SELECT month_start, 'engine', engine, NULL, units, revenue FROM mart.v_sales
    UNION ALL SELECT month_start, 'body_style', body_style, NULL, units, revenue FROM mart.v_sales
    UNION ALL SELECT month_start, 'color', color, NULL, units, revenue FROM mart.v_sales
    UNION ALL SELECT month_start, 'dealer_region', dealer_region, NULL, units, revenue FROM mart.v_sales
    UNION ALL SELECT month_start, 'dealer_name', dealer_name, NULL, units, revenue FROM mart.v_sales
    UNION ALL SELECT month_start, 'gender', gender, NULL, units, revenue FROM mart.v_sales
    UNION ALL SELECT month_start, 'income_quartile', 'Q' || income_quartile, NULL, units, revenue FROM mart.v_sales
),
agg AS (
    SELECT dimension_name, COALESCE(dimension_value, 'Unknown') AS dimension_value,
           COALESCE(parent_value, '') AS parent_value, month_start,
           SUM(units) AS units, SUM(revenue) AS revenue
    FROM long GROUP BY 1, 2, 3, 4
),
members AS (SELECT DISTINCT dimension_name, dimension_value, parent_value FROM agg),
dense AS (
    SELECT mb.dimension_name, mb.dimension_value, mb.parent_value, mo.month_start, mo.year,
           COALESCE(a.units, 0) AS units, COALESCE(a.revenue, 0) AS revenue
    FROM members mb
    CROSS JOIN (SELECT month_start, year FROM mart.dim_month WHERE period_type = 'Thực tế') mo
    LEFT JOIN agg a USING (dimension_name, dimension_value, parent_value, month_start)
),
w AS (
    SELECT d.*,
           LAG(units) OVER o AS units_pm,
           LAG(units, 12) OVER o AS units_py,
           LAG(revenue, 12) OVER o AS revenue_py,
           SUM(units) OVER (PARTITION BY dimension_name, dimension_value, parent_value, year ORDER BY month_start) AS units_ytd,
           SUM(revenue) OVER (PARTITION BY dimension_name, dimension_value, parent_value, year ORDER BY month_start) AS revenue_ytd,
           SUM(units) OVER (PARTITION BY dimension_name, month_start) AS dim_month_units,
           SUM(revenue) OVER (PARTITION BY dimension_name, month_start) AS dim_month_revenue
    FROM dense d
    WINDOW o AS (PARTITION BY dimension_name, dimension_value, parent_value ORDER BY month_start)
),
w2 AS (
    SELECT w.*,
           LAG(dim_month_units, 12) OVER (PARTITION BY dimension_name, dimension_value, parent_value ORDER BY month_start)
               AS dim_month_units_py
    FROM w
)
SELECT dimension_name,
       CASE dimension_name
            WHEN 'company' THEN 'Hãng' WHEN 'model' THEN 'Mẫu xe'
            WHEN 'transmission' THEN 'Hộp số' WHEN 'engine' THEN 'Động cơ'
            WHEN 'body_style' THEN 'Kiểu thân xe' WHEN 'color' THEN 'Màu'
            WHEN 'dealer_region' THEN 'Vùng' WHEN 'dealer_name' THEN 'Đại lý'
            WHEN 'gender' THEN 'Giới tính' WHEN 'income_quartile' THEN 'Nhóm thu nhập'
       END                                                         AS dimension_label,
       dimension_value, NULLIF(parent_value, '') AS parent_value,
       dimension_name || '|' || dimension_value || '|' || parent_value AS member_key,
       month_start, year,
       units, revenue, revenue / NULLIF(units, 0)                  AS asp,
       units_pm, units_py, revenue_py,
       (units - units_pm) / NULLIF(units_pm, 0)                    AS units_mom_pct,
       (units - units_py) / NULLIF(units_py, 0)                    AS units_yoy_pct,
       (revenue - revenue_py) / NULLIF(revenue_py, 0)              AS revenue_yoy_pct,
       units - units_py                                            AS units_yoy_delta,
       units / NULLIF(dim_month_units, 0)                          AS units_share_pct,
       revenue / NULLIF(dim_month_revenue, 0)                      AS revenue_share_pct,
       units / NULLIF(dim_month_units, 0)
           - units_py / NULLIF(dim_month_units_py, 0)              AS share_change_pp,
       units_ytd, revenue_ytd,
       RANK() OVER (PARTITION BY dimension_name, month_start ORDER BY units DESC) AS rank_in_month
FROM w2
ORDER BY dimension_name, dimension_value, month_start;

DROP TABLE IF EXISTS mart.dim_member;
CREATE TABLE mart.dim_member AS
SELECT DISTINCT member_key, dimension_name, dimension_label, dimension_value, parent_value,
       CASE dimension_name WHEN 'company' THEN 1 WHEN 'model' THEN 2 WHEN 'transmission' THEN 3
            WHEN 'engine' THEN 4 WHEN 'body_style' THEN 5 WHEN 'color' THEN 6
            WHEN 'dealer_region' THEN 7 WHEN 'dealer_name' THEN 8 WHEN 'gender' THEN 9 ELSE 10 END
           AS dimension_order
FROM mart.kpi_monthly_by_dimension;
ALTER TABLE mart.dim_member ADD PRIMARY KEY (member_key);

-- ---------------------------------------------------------------------
-- 8. TỔNG HỢP THEO NĂM × CHIỀU (D9, D10, D12–D17: xếp hạng, biến động,
--    mẫu tăng/giảm mạnh nhất) – dùng cho bảng xếp hạng, bar chart
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.kpi_dimension_summary;
CREATE TABLE mart.kpi_dimension_summary AS
WITH y AS (
    SELECT dimension_name, dimension_label, dimension_value, parent_value, year,
           SUM(units) AS units, SUM(revenue) AS revenue,
           AVG(units) AS avg_monthly_units,
           STDDEV_POP(units) / NULLIF(AVG(units), 0) AS demand_cv,
           COUNT(*) FILTER (WHERE units > 0) AS active_months
    FROM mart.kpi_monthly_by_dimension
    GROUP BY dimension_name, dimension_label, dimension_value, parent_value, year
),
w AS (
    SELECT y.*,
           LAG(units) OVER o AS units_py,
           LAG(revenue) OVER o AS revenue_py,
           units / NULLIF(SUM(units) OVER (PARTITION BY dimension_name, year), 0) AS units_share_pct,
           revenue / NULLIF(SUM(revenue) OVER (PARTITION BY dimension_name, year), 0) AS revenue_share_pct
    FROM y WINDOW o AS (PARTITION BY dimension_name, dimension_value, parent_value ORDER BY year)
),
w2 AS (
    SELECT w.*,
           LAG(units_share_pct) OVER (PARTITION BY dimension_name, dimension_value, parent_value ORDER BY year)
               AS units_share_py_pct
    FROM w
)
SELECT dimension_name, dimension_label, dimension_value, parent_value,
       dimension_name || '|' || dimension_value || '|' || COALESCE(parent_value, '') AS member_key,
       year::text AS period, year,
       units, revenue, revenue / NULLIF(units, 0)                  AS asp,
       units_share_pct, revenue_share_pct,
       units_py, revenue_py,
       (units - units_py) / NULLIF(units_py, 0)                    AS units_yoy_pct,
       (revenue - revenue_py) / NULLIF(revenue_py, 0)              AS revenue_yoy_pct,
       units - units_py                                            AS units_yoy_delta,
       units_share_pct - units_share_py_pct                        AS share_change_pp,
       avg_monthly_units, demand_cv, active_months,
       RANK() OVER (PARTITION BY dimension_name, year ORDER BY units DESC)   AS rank_units,
       RANK() OVER (PARTITION BY dimension_name, year ORDER BY revenue DESC) AS rank_revenue,
       CASE WHEN units_py IS NULL THEN NULL
            WHEN RANK() OVER (PARTITION BY dimension_name, year ORDER BY units - units_py DESC NULLS LAST) <= 5
                 THEN 'Top 5 tăng'
            WHEN RANK() OVER (PARTITION BY dimension_name, year ORDER BY units - units_py ASC NULLS LAST) <= 5
                 THEN 'Top 5 giảm'
       END                                                         AS mover_group
FROM w2
ORDER BY dimension_name, year, units DESC;

-- ---------------------------------------------------------------------
-- 9. PHÂN KHÚC KHÁCH HÀNG (D11, D17): năm × nhóm thu nhập × giới tính
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.kpi_customer_segment;
CREATE TABLE mart.kpi_customer_segment AS
WITH bands AS (
    SELECT income_quartile, MIN(annual_income) AS income_min, MAX(annual_income) AS income_max
    FROM mart.v_sales GROUP BY income_quartile
)
SELECT s.year::text AS period, s.year,
       s.income_quartile,
       'Q' || s.income_quartile || ' (' || to_char(b.income_min, 'FM999,999,999')
           || '–' || to_char(b.income_max, 'FM999,999,999') || ')'  AS income_band,
       b.income_min, b.income_max,
       s.gender,
       SUM(s.units)                                    AS units,
       SUM(s.revenue)                                  AS revenue,
       SUM(s.revenue) / NULLIF(SUM(s.units), 0)        AS asp,
       AVG(s.annual_income)                            AS avg_income,
       SUM(s.annual_income)                            AS sum_income,
       SUM(s.revenue / NULLIF(s.annual_income, 0))     AS sum_price_to_income,
       AVG(s.revenue / NULLIF(s.annual_income, 0))     AS price_to_income,
       SUM(s.units) / NULLIF(SUM(SUM(s.units)) OVER (PARTITION BY s.year), 0) AS units_share_pct
FROM mart.v_sales s JOIN bands b USING (income_quartile)
GROUP BY s.year, s.income_quartile, b.income_min, b.income_max, s.gender
ORDER BY s.year, s.income_quartile, s.gender;

-- ---------------------------------------------------------------------
-- 10. KPI TỔNG HỢP THEO NĂM (thẻ KPI, D10 HHI, Top 10 mẫu)
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.kpi_annual_summary;
CREATE TABLE mart.kpi_annual_summary AS
WITH p AS (SELECT * FROM mart.kpi_parameters WHERE id = 1),
y AS (
    SELECT year, SUM(units) AS units, SUM(revenue) AS revenue,
           SUM(units) FILTER (WHERE transmission = 'Auto') AS auto_units,
           COUNT(DISTINCT company) AS n_companies,
           COUNT(DISTINCT company || '|' || model) AS n_models,
           COUNT(DISTINCT dealer_name) AS n_dealers,
           COUNT(DISTINCT full_date) AS selling_days
    FROM mart.v_sales GROUP BY year
),
hhi AS (
    SELECT year, SUM(units_share_pct ^ 2) AS hhi_company
    FROM mart.kpi_dimension_summary WHERE dimension_name = 'company' GROUP BY year
),
top10 AS (
    SELECT year, SUM(units_share_pct) AS top10_model_share_pct
    FROM (SELECT year, units_share_pct,
                 ROW_NUMBER() OVER (PARTITION BY year ORDER BY units DESC) AS rn
          FROM mart.kpi_dimension_summary WHERE dimension_name = 'model') t
    WHERE rn <= 10 GROUP BY year
),
growing AS (
    SELECT year,
           COUNT(*) FILTER (WHERE units_yoy_delta > 0)::numeric
             / NULLIF(COUNT(*) FILTER (WHERE units_py IS NOT NULL), 0) AS dealers_growing_pct
    FROM mart.kpi_dimension_summary WHERE dimension_name = 'dealer_name' GROUP BY year
),
mo AS (
    SELECT year,
           STDDEV_POP(units) / NULLIF(AVG(units), 0) AS demand_cv,
           (ARRAY_AGG(to_char(month_start, 'MM/YYYY') ORDER BY units DESC))[1] AS peak_month,
           MAX(units) AS peak_month_units,
           (ARRAY_AGG(to_char(month_start, 'MM/YYYY') ORDER BY units ASC))[1] AS low_month,
           MIN(units) AS low_month_units
    FROM mart.kpi_monthly_overview GROUP BY year
)
SELECT y.year::text AS period, y.year,
       y.units, y.revenue, y.revenue / NULLIF(y.units, 0)             AS asp,
       LAG(y.units) OVER o                                            AS units_py,
       LAG(y.revenue) OVER o                                          AS revenue_py,
       (y.units - LAG(y.units) OVER o) / NULLIF(LAG(y.units) OVER o, 0)       AS units_yoy_pct,
       (y.revenue - LAG(y.revenue) OVER o) / NULLIF(LAG(y.revenue) OVER o, 0) AS revenue_yoy_pct,
       LAG(y.units) OVER o * (1 + p.target_growth)                    AS target_units,
       LAG(y.revenue) OVER o * (1 + p.target_growth)                  AS target_revenue,
       CASE WHEN LAG(y.units) OVER o IS NULL THEN NULL
            WHEN y.units >= LAG(y.units) OVER o * (1 + p.target_growth) THEN 'Đạt' ELSE 'Không đạt' END
                                                                      AS units_target_status,
       y.auto_units / NULLIF(y.units, 0)                              AS auto_share_pct,
       y.auto_units / NULLIF(y.units, 0)
         - LAG(y.auto_units / NULLIF(y.units, 0)) OVER o              AS auto_share_change_pp,
       t.top10_model_share_pct, h.hhi_company,
       y.n_companies, y.n_models, y.n_dealers, y.selling_days,
       y.units / NULLIF(y.n_dealers * 12.0, 0)                        AS units_per_dealer_month,
       g.dealers_growing_pct,
       mo.demand_cv, mo.peak_month, mo.peak_month_units, mo.low_month, mo.low_month_units
FROM y
CROSS JOIN p
LEFT JOIN hhi h USING (year)
LEFT JOIN top10 t USING (year)
LEFT JOIN growing g USING (year)
LEFT JOIN mo USING (year)
WINDOW o AS (ORDER BY y.year)
ORDER BY y.year;

-- ---------------------------------------------------------------------
-- 11. CHUỖI THỰC TẾ + DỰ BÁO (F1) – vẽ line chart có dải 80%
--     1 dòng = tháng × cấp × thành viên × mô hình
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.forecast_series;
CREATE TABLE mart.forecast_series AS
WITH p AS (SELECT * FROM mart.kpi_parameters WHERE id = 1),
actual AS (
    SELECT 'total'::text AS level, 'ALL'::text AS member, month_start, SUM(units) AS units
    FROM mart.v_sales GROUP BY month_start
    UNION ALL
    SELECT 'company', company, month_start, SUM(units) FROM mart.v_sales GROUP BY company, month_start
    UNION ALL
    SELECT 'region', dealer_region, month_start, SUM(units) FROM mart.v_sales GROUP BY dealer_region, month_start
),
series AS (SELECT DISTINCT level, member, model_name FROM fact_demand_forecast),
grid AS (
    SELECT s.level, s.member, s.model_name, m.month_start, m.period_type
    FROM series s CROSS JOIN mart.dim_month m
)
SELECT g.month_start, g.level,
       CASE g.level WHEN 'total' THEN 'Tổng' WHEN 'company' THEN 'Hãng' ELSE 'Vùng' END AS level_label,
       g.member, g.level || '|' || g.member AS series_key, g.model_name,
       (g.model_name = p.main_model)                                 AS is_main_model,
       CASE WHEN g.period_type = 'Dự báo' THEN 'Dự báo'
            WHEN f.is_backtest THEN 'Backtest'
            ELSE 'Lịch sử' END                                       AS series_type,
       CASE WHEN g.period_type = 'Thực tế' THEN COALESCE(a.units, 0) END AS actual_units,
       f.forecast_units, f.lower_80, f.upper_80,
       f.forecast_units - CASE WHEN f.is_backtest THEN COALESCE(a.units, 0) END AS forecast_error,
       CASE WHEN f.is_backtest THEN
            COALESCE(a.units, 0) BETWEEN f.lower_80 AND f.upper_80 END       AS in_interval
FROM grid g
CROSS JOIN p
LEFT JOIN actual a
       ON a.level = g.level AND a.member = g.member AND a.month_start = g.month_start
LEFT JOIN fact_demand_forecast f
       ON f.level = g.level AND f.member = g.member
      AND f.model_name = g.model_name AND f.month_start = g.month_start
ORDER BY g.level, g.member, g.model_name, g.month_start;

DROP TABLE IF EXISTS mart.dim_forecast_member;
CREATE TABLE mart.dim_forecast_member AS
SELECT DISTINCT series_key, level, level_label, member,
       CASE level WHEN 'total' THEN 1 WHEN 'company' THEN 2 ELSE 3 END AS level_order
FROM mart.forecast_series;
ALTER TABLE mart.dim_forecast_member ADD PRIMARY KEY (series_key);

DROP TABLE IF EXISTS mart.dim_forecast_model;
CREATE TABLE mart.dim_forecast_model AS
SELECT DISTINCT f.model_name,
       CASE f.model_name WHEN 'sarima' THEN 'SARIMA' WHEN 'holt_winters' THEN 'Holt-Winters'
            ELSE 'Seasonal naive' END AS model_label,
       (f.model_name = p.main_model) AS is_main_model
FROM fact_demand_forecast f CROSS JOIN mart.kpi_parameters p WHERE p.id = 1;
ALTER TABLE mart.dim_forecast_model ADD PRIMARY KEY (model_name);

-- ---------------------------------------------------------------------
-- 12. ĐỘ CHÍNH XÁC DỰ BÁO (F2–F8) trên 6 tháng backtest
--     Cột thành phần (abs_error_total, error_total, n_in_interval) để Power BI
--     gộp nhiều thành viên vẫn ra WAPE / Bias / độ phủ đúng.
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.forecast_accuracy;
CREATE TABLE mart.forecast_accuracy AS
WITH p AS (SELECT * FROM mart.kpi_parameters WHERE id = 1),
bt AS (
    SELECT level, member, model_name, month_start,
           actual_units AS a, forecast_units AS f, lower_80, upper_80
    FROM fact_demand_forecast WHERE is_backtest
),
s AS (
    SELECT level, member, model_name,
           COUNT(*)                                            AS n_points,
           SUM(a) AS actual_total, SUM(f) AS forecast_total,
           SUM(ABS(a - f)) AS abs_error_total,
           SUM(f - a) AS error_total,
           SUM(CASE WHEN a BETWEEN lower_80 AND upper_80 THEN 1 ELSE 0 END) AS n_in_interval,
           AVG(ABS(a - f))                                     AS mae,
           SQRT(AVG((a - f) ^ 2))                              AS rmse,
           AVG(ABS(a - f) / NULLIF(a, 0))                      AS mape_pct,
           SUM(ABS(a - f)) / NULLIF(SUM(a), 0)                 AS wape_pct,
           SUM(f - a) / NULLIF(SUM(a), 0)                      AS bias_pct,
           SUM(a - f) / NULLIF(AVG(ABS(a - f)), 0)             AS tracking_signal,
           AVG(CASE WHEN a BETWEEN lower_80 AND upper_80 THEN 1.0 ELSE 0 END) AS interval_coverage_pct
    FROM bt GROUP BY level, member, model_name
)
SELECT s.level,
       CASE s.level WHEN 'total' THEN 'Tổng' WHEN 'company' THEN 'Hãng' ELSE 'Vùng' END AS level_label,
       s.member, s.level || '|' || s.member AS series_key, s.model_name,
       (s.model_name = p.main_model)                           AS is_main_model,
       s.n_points, s.actual_total, s.forecast_total, s.abs_error_total, s.error_total, s.n_in_interval,
       s.mae, s.rmse, s.mape_pct, s.wape_pct,
       1 - s.wape_pct                                          AS accuracy_pct,
       s.bias_pct, s.tracking_signal, s.interval_coverage_pct,
       n.wape_pct                                              AS naive_wape_pct,
       n.wape_pct - s.wape_pct                                 AS fva_pp,
       p.wape_threshold, p.bias_threshold,
       (s.wape_pct <= p.wape_threshold)                        AS wape_pass,
       (ABS(s.bias_pct) <= p.bias_threshold)                   AS bias_pass,
       CASE WHEN s.wape_pct <= p.wape_threshold AND ABS(s.bias_pct) <= p.bias_threshold
            THEN 'Đạt' ELSE 'Không đạt' END                    AS status,
       CASE WHEN ABS(s.tracking_signal) > 4 THEN 'Cảnh báo' ELSE 'Ổn định' END AS tracking_status,
       RANK() OVER (PARTITION BY s.level, s.member ORDER BY s.wape_pct) AS model_rank
FROM s
CROSS JOIN p
LEFT JOIN s n
       ON n.level = s.level AND n.member = s.member AND n.model_name = 'seasonal_naive'
ORDER BY s.level, s.member, s.wape_pct;

-- ---------------------------------------------------------------------
-- 13. KẾ HOẠCH TỪ DỰ BÁO (S1, S3, S4) – 6 tháng tới, mô hình chính
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.dss_forecast_plan;
CREATE TABLE mart.dss_forecast_plan AS
WITH p AS (SELECT * FROM mart.kpi_parameters WHERE id = 1),
hist AS (   -- thống kê 24 tháng lịch sử cho từng thành viên
    SELECT level, member,
           STDDEV_POP(actual_units) / NULLIF(AVG(actual_units), 0) AS demand_cv,
           AVG(actual_units) AS avg_monthly_units
    FROM mart.forecast_series
    WHERE series_type <> 'Dự báo' AND is_main_model
    GROUP BY level, member
),
asp AS (
    SELECT 'total'::text AS level, 'ALL'::text AS member, SUM(revenue) / SUM(units) AS asp_hist FROM mart.v_sales
    UNION ALL SELECT 'company', company, SUM(revenue) / SUM(units) FROM mart.v_sales GROUP BY company
    UNION ALL SELECT 'region', dealer_region, SUM(revenue) / SUM(units) FROM mart.v_sales GROUP BY dealer_region
),
py AS (
    SELECT level, member, month_start, actual_units
    FROM mart.forecast_series WHERE is_main_model AND series_type <> 'Dự báo'
),
acc AS (SELECT level, member, accuracy_pct, status FROM mart.forecast_accuracy WHERE is_main_model)
SELECT f.month_start, f.level, f.level_label, f.member, f.series_key, f.model_name,
       f.forecast_units, f.lower_80, f.upper_80,
       py.actual_units                                          AS units_py,
       (f.forecast_units - py.actual_units) / NULLIF(py.actual_units, 0) AS forecast_growth_pct,
       h.demand_cv, h.avg_monthly_units,
       asp.asp_hist,
       p.safety_factor,
       f.forecast_units * (1 + p.safety_factor * COALESCE(h.demand_cv, 0)) AS recommended_order,
       f.forecast_units * asp.asp_hist                          AS projected_revenue,
       f.lower_80 * asp.asp_hist                                AS projected_revenue_low,
       f.upper_80 * asp.asp_hist                                AS projected_revenue_high,
       acc.accuracy_pct                                         AS backtest_accuracy_pct,
       acc.status                                               AS backtest_status
FROM mart.forecast_series f
CROSS JOIN p
LEFT JOIN hist h ON h.level = f.level AND h.member = f.member
LEFT JOIN asp    ON asp.level = f.level AND asp.member = f.member
LEFT JOIN py     ON py.level = f.level AND py.member = f.member
                AND py.month_start = (f.month_start - INTERVAL '1 year')::date
LEFT JOIN acc    ON acc.level = f.level AND acc.member = f.member
WHERE f.series_type = 'Dự báo' AND f.is_main_model
ORDER BY f.level, f.member, f.month_start;

-- ---------------------------------------------------------------------
-- 14. PHÂN BỔ XE THEO VÙNG / ĐẠI LÝ (S2): dự báo tổng × tỷ trọng 6 tháng cuối
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.dss_dealer_allocation;
CREATE TABLE mart.dss_dealer_allocation AS
WITH last6 AS (
    SELECT month_start FROM mart.dim_month WHERE period_type = 'Thực tế'
    ORDER BY month_start DESC LIMIT 6
),
mix AS (
    SELECT dealer_region, dealer_name,
           SUM(units) AS units_6m,
           SUM(revenue) / NULLIF(SUM(units), 0) AS asp_6m
    FROM mart.v_sales WHERE month_start IN (SELECT month_start FROM last6)
    GROUP BY dealer_region, dealer_name
),
mix2 AS (
    SELECT mix.*,
           units_6m / SUM(units_6m) OVER () AS dealer_share_6m,
           SUM(units_6m) OVER (PARTITION BY dealer_region) / SUM(units_6m) OVER () AS region_share_6m
    FROM mix
),
total_fc AS (
    SELECT month_start, forecast_units, lower_80, upper_80
    FROM mart.dss_forecast_plan WHERE level = 'total'
),
region_fc AS (
    SELECT month_start, member AS dealer_region, forecast_units AS region_model_forecast
    FROM mart.dss_forecast_plan WHERE level = 'region'
)
SELECT t.month_start, m.dealer_region, m.dealer_name,
       m.units_6m, m.dealer_share_6m, m.region_share_6m,
       t.forecast_units                                AS total_forecast_units,
       t.forecast_units * m.dealer_share_6m            AS allocated_units,
       t.lower_80 * m.dealer_share_6m                  AS allocated_units_low,
       t.upper_80 * m.dealer_share_6m                  AS allocated_units_high,
       t.forecast_units * m.dealer_share_6m * m.asp_6m AS allocated_revenue,
       r.region_model_forecast
FROM total_fc t
CROSS JOIN mix2 m
LEFT JOIN region_fc r ON r.month_start = t.month_start AND r.dealer_region = m.dealer_region
ORDER BY t.month_start, m.dealer_region, allocated_units DESC;

-- ---------------------------------------------------------------------
-- 15. ĐIỂM ƯU TIÊN NHẬP HÀNG THEO HÃNG (S5)
--     4 thành phần chuẩn hóa min-max 0–1, trọng số trong kpi_parameters
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.dss_company_priority;
CREATE TABLE mart.dss_company_priority AS
WITH p AS (SELECT * FROM mart.kpi_parameters WHERE id = 1),
base AS (
    SELECT fp.member AS company,
           SUM(fp.forecast_units) AS forecast_next_6m,
           SUM(fp.units_py) AS units_same_6m_py,
           SUM(fp.forecast_units) / NULLIF(SUM(fp.units_py), 0) - 1 AS forecast_growth_pct,
           MAX(fp.demand_cv) AS demand_cv,
           MAX(fp.backtest_accuracy_pct) AS forecast_accuracy_pct,
           SUM(fp.projected_revenue) AS projected_revenue_6m
    FROM mart.dss_forecast_plan fp WHERE fp.level = 'company'
    GROUP BY fp.member
),
share AS (
    SELECT dimension_value AS company, units_share_pct
    FROM mart.kpi_dimension_summary
    WHERE dimension_name = 'company' AND year = (SELECT MAX(year) FROM mart.kpi_dimension_summary)
),
x AS (
    SELECT b.*, COALESCE(s.units_share_pct, 0) AS units_share_pct
    FROM base b LEFT JOIN share s USING (company)
),
n AS (
    SELECT x.*,
           (forecast_growth_pct - MIN(forecast_growth_pct) OVER ())
               / NULLIF(MAX(forecast_growth_pct) OVER () - MIN(forecast_growth_pct) OVER (), 0) AS score_growth,
           (units_share_pct - MIN(units_share_pct) OVER ())
               / NULLIF(MAX(units_share_pct) OVER () - MIN(units_share_pct) OVER (), 0) AS score_share,
           1 - (demand_cv - MIN(demand_cv) OVER ())
               / NULLIF(MAX(demand_cv) OVER () - MIN(demand_cv) OVER (), 0) AS score_stability,
           (GREATEST(forecast_accuracy_pct, 0) - MIN(GREATEST(forecast_accuracy_pct, 0)) OVER ())
               / NULLIF(MAX(GREATEST(forecast_accuracy_pct, 0)) OVER ()
                        - MIN(GREATEST(forecast_accuracy_pct, 0)) OVER (), 0) AS score_accuracy
    FROM x
),
scored AS (
    SELECT n.*,
           p.w_growth, p.w_share, p.w_stability, p.w_accuracy,
           p.w_growth * COALESCE(score_growth, 0) + p.w_share * COALESCE(score_share, 0)
         + p.w_stability * COALESCE(score_stability, 0) + p.w_accuracy * COALESCE(score_accuracy, 0)
               AS priority_score
    FROM n CROSS JOIN p
)
SELECT scored.*,
       'company|' || company AS series_key,
       RANK() OVER (ORDER BY priority_score DESC) AS priority_rank,
       CASE NTILE(3) OVER (ORDER BY priority_score DESC)
            WHEN 1 THEN 'Ưu tiên cao' WHEN 2 THEN 'Trung bình' ELSE 'Ưu tiên thấp' END AS priority_tier
FROM scored
ORDER BY priority_score DESC;

-- ---------------------------------------------------------------------
-- 16. CHẤT LƯỢNG DỮ LIỆU (Q3–Q6). Q1–Q2 (so với CSV) do build_marts.py thêm.
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.dq_checks;
CREATE TABLE mart.dq_checks (
    check_code   VARCHAR(10) PRIMARY KEY,
    check_name   TEXT NOT NULL,
    metric_value NUMERIC,
    threshold    TEXT,
    passed       BOOLEAN,
    detail       TEXT,
    checked_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO mart.dq_checks (check_code, check_name, metric_value, threshold, passed, detail)
SELECT 'Q3', 'Tỷ lệ khóa ngoại mồ côi', orphans::numeric / NULLIF(total, 0), '= 0', orphans = 0,
       orphans || ' / ' || total || ' dòng fact'
FROM (
    SELECT COUNT(*) AS total,
           COUNT(*) FILTER (WHERE d.date_id IS NULL OR c.customer_id IS NULL
                                 OR ca.car_key IS NULL OR de.dealer_id IS NULL) AS orphans
    FROM fact_car_sales f
    LEFT JOIN dim_date d ON f.date_id = d.date_id
    LEFT JOIN dim_customer c ON f.customer_id = c.customer_id
    LEFT JOIN dim_car ca ON f.car_key = ca.car_key
    LEFT JOIN dim_dealer de ON f.dealer_id = de.dealer_id
) t
UNION ALL
SELECT 'Q4', 'Tỷ lệ đầy đủ (khóa, price, date)',
       1 - nulls::numeric / NULLIF(cells, 0), '= 100%', nulls = 0, nulls || ' ô null / ' || cells || ' ô'
FROM (
    SELECT COUNT(*) * 6 AS cells,
           SUM((car_id IS NULL)::int + (date_id IS NULL)::int + (customer_id IS NULL)::int
             + (car_key IS NULL)::int + (dealer_id IS NULL)::int + (price IS NULL)::int) AS nulls
    FROM fact_car_sales
) t
UNION ALL
SELECT 'Q5', 'Tỷ lệ trùng car_id', dup::numeric / NULLIF(total, 0), '= 0', dup = 0,
       dup || ' dòng trùng'
FROM (SELECT COUNT(*) AS total, COUNT(*) - COUNT(DISTINCT car_id) AS dup FROM fact_car_sales) t
UNION ALL
SELECT 'Q6', 'Độ phủ chuỗi thời gian (tháng)',
       observed::numeric / NULLIF(in_range, 0), '>= 24 tháng, không thiếu tháng',
       observed >= 24 AND observed = in_range,
       observed || ' / ' || in_range || ' tháng (' || first_m || ' → ' || last_m || ')'
FROM (
    SELECT COUNT(DISTINCT month_start) AS observed,
           (EXTRACT(YEAR FROM age(MAX(month_start), MIN(month_start))) * 12
              + EXTRACT(MONTH FROM age(MAX(month_start), MIN(month_start))) + 1)::int AS in_range,
           to_char(MIN(month_start), 'MM/YYYY') AS first_m,
           to_char(MAX(month_start), 'MM/YYYY') AS last_m
    FROM mart.v_sales
) t;
