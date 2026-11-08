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
    body_style VARCHAR(50)
);

-- 4. Bảng Dim Dealer
CREATE TABLE IF NOT EXISTS dim_dealer (
    dealer_id SERIAL PRIMARY KEY,         -- Surrogate Key tự tăng
    dealer_no VARCHAR(50) NOT NULL,
    dealer_name VARCHAR(255) NOT NULL,
    dealer_region VARCHAR(100)
);

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