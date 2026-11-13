-- 1. Bảng Dim Date
CREATE TABLE IF NOT EXISTS dim_date (
    date_id INT PRIMARY KEY,              -- Định dạng YYYYMMDD (ví dụ: 20220102)
    full_date DATE NOT NULL,
    day INT NOT NULL,
    month INT NOT NULL,
    quarter INT NOT NULL,
    year INT NOT NULL,
    day_of_week VARCHAR(20) NOT NULL
);

-- 2. Bảng Dim Customer
CREATE TABLE IF NOT EXISTS dim_customer (
    customer_id SERIAL PRIMARY KEY,       -- Surrogate Key tự tăng
    customer_name VARCHAR(255) NOT NULL,
    gender VARCHAR(20),
    annual_income BIGINT,
    phone VARCHAR(50)
);

-- 3. Bảng Dim Car
CREATE TABLE IF NOT EXISTS dim_car (
    car_key SERIAL PRIMARY KEY,          -- Surrogate Key tự tăng
    company VARCHAR(100) NOT NULL,
    model VARCHAR(100) NOT NULL,
    engine VARCHAR(100),
    transmission VARCHAR(50),
    color VARCHAR(50),
    body_style VARCHAR(50),
    cars_sold INT NOT NULL DEFAULT 0     -- Số xe đã bán của cấu hình này (tính từ dữ liệu gốc, xem etl.py)
);
-- DB tạo từ phiên bản cũ chưa có cột cars_sold: chạy lại etl.py để nạp số liệu và sắp xếp lại
ALTER TABLE dim_car ADD COLUMN IF NOT EXISTS cars_sold INT NOT NULL DEFAULT 0;

-- 4. Bảng Dim Dealer
CREATE TABLE IF NOT EXISTS dim_dealer (
    dealer_id SERIAL PRIMARY KEY,         -- Surrogate Key tự tăng
    dealer_name VARCHAR(255) NOT NULL,
    dealer_region VARCHAR(100)
);
-- dealer_no đã bỏ (chỉ có 7 giá trị, suy ra được từ dealer_region); dọn DB tạo từ phiên bản cũ
ALTER TABLE dim_dealer DROP COLUMN IF EXISTS dealer_no;

-- 5. Bảng Fact Sales
CREATE TABLE IF NOT EXISTS fact_car_sales (
    car_id VARCHAR(50) PRIMARY KEY,       -- Degenerate Dim (Mã hóa đơn/xe)
    date_id INT NOT NULL,
    customer_id INT NOT NULL,
    car_key INT NOT NULL,
    dealer_id INT NOT NULL,
    price INT NOT NULL,                   -- Measure: Doanh thu bán xe
    quantity INT DEFAULT 1,               -- Measure: Số lượng xe (mỗi dòng = 1)
    
    FOREIGN KEY (date_id) REFERENCES dim_date(date_id),
    FOREIGN KEY (customer_id) REFERENCES dim_customer(customer_id),
    FOREIGN KEY (car_key) REFERENCES dim_car(car_key),
    FOREIGN KEY (dealer_id) REFERENCES dim_dealer(dealer_id)
);

-- Nhu cầu tổng hợp theo tháng, hãng và vùng.
-- Danh sách cấu hình xe xếp theo số xe bán từ cao xuống thấp (thứ tự bền vững, dùng ORDER BY trong view)
CREATE OR REPLACE VIEW v_dim_car_ranked AS
SELECT RANK() OVER (ORDER BY cars_sold DESC) AS sold_rank,
       car_key, company, model, engine, transmission, color, body_style, cars_sold
FROM dim_car
ORDER BY cars_sold DESC, car_key;

CREATE OR REPLACE VIEW v_monthly_demand AS
SELECT d.year * 100 + d.month AS month_id,
       d.year,
       d.month,
       make_date(d.year, d.month, 1) AS month_start,
       c.company,
       de.dealer_region,
       SUM(f.quantity) AS units,
       SUM(f.price) AS revenue
FROM fact_car_sales AS f
JOIN dim_date AS d ON f.date_id = d.date_id
JOIN dim_car AS c ON f.car_key = c.car_key
JOIN dim_dealer AS de ON f.dealer_id = de.dealer_id
GROUP BY d.year, d.month, c.company, de.dealer_region;

CREATE OR REPLACE VIEW v_monthly_calendar AS
WITH date_bounds AS (
    SELECT MIN(month_start) AS first_month,
           MAX(month_start) AS last_month
    FROM v_monthly_demand
)
SELECT generate_series(
    date_bounds.first_month,
    date_bounds.last_month,
    INTERVAL '1 month'
)::date AS month_start
FROM date_bounds;

-- Monthly sales by each slicer dimension used by KPIs D5-D6 and D12-D17.
CREATE OR REPLACE VIEW v_monthly_dimension_demand AS
WITH monthly_sales AS (
    SELECT make_date(d.year, d.month, 1) AS month_start,
           c.company,
           c.model,
           c.transmission,
           c.engine,
           c.body_style,
           c.color,
           de.dealer_region,
           de.dealer_name,
           cu.gender,
           SUM(f.quantity)::numeric AS units,
           SUM(f.price)::numeric AS revenue
    FROM fact_car_sales AS f
    JOIN dim_date AS d ON f.date_id = d.date_id
    JOIN dim_car AS c ON f.car_key = c.car_key
    JOIN dim_dealer AS de ON f.dealer_id = de.dealer_id
    JOIN dim_customer AS cu ON f.customer_id = cu.customer_id
    GROUP BY d.year, d.month,
             c.company, c.model, c.transmission, c.engine, c.body_style, c.color,
             de.dealer_region, de.dealer_name, cu.gender
)
SELECT month_start, 'company'::text AS dimension_name,
       COALESCE(company, 'Unknown')::text AS dimension_value, units, revenue
FROM monthly_sales
UNION ALL
SELECT month_start, 'model', COALESCE(model, 'Unknown')::text, units, revenue
FROM monthly_sales
UNION ALL
SELECT month_start, 'transmission', COALESCE(transmission, 'Unknown')::text, units, revenue
FROM monthly_sales
UNION ALL
SELECT month_start, 'engine', COALESCE(engine, 'Unknown')::text, units, revenue
FROM monthly_sales
UNION ALL
SELECT month_start, 'body_style', COALESCE(body_style, 'Unknown')::text, units, revenue
FROM monthly_sales
UNION ALL
SELECT month_start, 'color', COALESCE(color, 'Unknown')::text, units, revenue
FROM monthly_sales
UNION ALL
SELECT month_start, 'dealer_region', COALESCE(dealer_region, 'Unknown')::text, units, revenue
FROM monthly_sales
UNION ALL
SELECT month_start, 'dealer_name', COALESCE(dealer_name, 'Unknown')::text, units, revenue
FROM monthly_sales
UNION ALL
SELECT month_start, 'gender', COALESCE(gender, 'Unknown')::text, units, revenue
FROM monthly_sales;

-- Kết quả backtest và dự báo tương lai ở cấp tổng, hãng hoặc vùng.
CREATE TABLE IF NOT EXISTS fact_demand_forecast (
    forecast_id SERIAL PRIMARY KEY,
    month_id INT NOT NULL,
    month_start DATE NOT NULL,
    level VARCHAR(20) NOT NULL
        CHECK (level IN ('total', 'company', 'region')),
    member VARCHAR(100) NOT NULL,
    model_name VARCHAR(50) NOT NULL
        CHECK (model_name IN ('holt_winters', 'sarima', 'seasonal_naive')),
    forecast_units NUMERIC(12, 2) NOT NULL,
    lower_80 NUMERIC(12, 2),
    upper_80 NUMERIC(12, 2),
    actual_units NUMERIC(12, 2),
    is_backtest BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (month_id, level, member, model_name),
    CHECK (
        (is_backtest AND actual_units IS NOT NULL)
        OR (NOT is_backtest AND actual_units IS NULL)
    ),
    CHECK (lower_80 IS NULL OR lower_80 <= upper_80)
);

-- Thời điểm chạy dự báo (bảng cũ chưa có cột này thì được thêm vào).
ALTER TABLE fact_demand_forecast
    ADD COLUMN IF NOT EXISTS run_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE fact_demand_forecast
    DROP CONSTRAINT IF EXISTS fact_demand_forecast_model_name_check;

ALTER TABLE fact_demand_forecast
    ADD CONSTRAINT fact_demand_forecast_model_name_check
    CHECK (model_name IN ('holt_winters', 'sarima', 'seasonal_naive'));