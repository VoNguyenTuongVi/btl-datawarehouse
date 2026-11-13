-- Truy vấn hỗ trợ cột dim_car.cars_sold (số xe đã bán của mỗi cấu hình xe).
-- Chạy: psql -U postgres -h localhost -d car_sales_dw -f src/dim_car_queries.sql
-- Cột cars_sold được etl.py tính và nạp; dim_car nạp đã xếp giảm dần nên car_key 1 = bán nhiều nhất.

-- 1. Top 20 cấu hình xe bán chạy nhất
SELECT sold_rank, car_key, company, model, engine, transmission, color, body_style, cars_sold
FROM v_dim_car_ranked
LIMIT 20;

-- 2. Cấu hình chưa bán được xe nào (cars_sold = 0)
SELECT car_key, company, model, engine, transmission, color, body_style
FROM dim_car
WHERE cars_sold = 0
ORDER BY company, model;

-- 3. Tổng xe bán theo hãng (cộng cars_sold từ dim_car, không cần join fact)
SELECT company, SUM(cars_sold) AS cars_sold
FROM dim_car
GROUP BY company
ORDER BY cars_sold DESC;

-- 4. Đối chiếu cars_sold với fact_car_sales: kết quả phải trống (0 dòng)
SELECT d.car_key, d.cars_sold, COUNT(f.car_id) AS fact_cnt
FROM dim_car d
LEFT JOIN fact_car_sales f ON f.car_key = d.car_key
GROUP BY d.car_key, d.cars_sold
HAVING d.cars_sold <> COUNT(f.car_id);

-- 5. Tổng cars_sold phải bằng số dòng fact (23.906)
SELECT (SELECT SUM(cars_sold) FROM dim_car) AS sum_cars_sold,
       (SELECT COUNT(*) FROM fact_car_sales) AS fact_rows;
