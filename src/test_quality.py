import pandas as pd
from sqlalchemy import text

from database import PROJECT_ROOT, create_database_engine

DATA_PATH = PROJECT_ROOT / 'data' / 'car_sales_cleaned.csv'
engine = create_database_engine()
raw_df = pd.read_csv(DATA_PATH)

print("=== KIỂM TRA CHẤT LƯỢNG DATA WAREHOUSE ===")

# Test 1: Khớp số lượng bản ghi Fact
db_fact_count = pd.read_sql(text("SELECT COUNT(*) AS cnt FROM fact_car_sales"), engine)['cnt'][0]
csv_count = len(raw_df)
print(f"[1] Số dòng - CSV: {csv_count} | DW: {db_fact_count}")
assert csv_count == db_fact_count, "LỖI: Số dòng không khớp!"

# Test 2: Khớp tổng doanh thu (Total Revenue)
db_revenue = pd.read_sql(text("SELECT SUM(price) AS total FROM fact_car_sales"), engine)['total'][0]
csv_revenue = raw_df['price'].sum()
print(f"[2] Tổng doanh thu - CSV: ${csv_revenue:,.0f} | DW: ${db_revenue:,.0f}")
assert csv_revenue == db_revenue, "LỖI: Tổng tiền không khớp!"

# Test 3: Kiểm tra khóa ngoại mồ côi (Orphan FKs)
orphan_check = pd.read_sql(text("""
SELECT COUNT(*) AS orphans
FROM fact_car_sales f
LEFT JOIN dim_date d ON f.date_id = d.date_id
LEFT JOIN dim_customer c ON f.customer_id = c.customer_id
LEFT JOIN dim_car ca ON f.car_key = ca.car_key
LEFT JOIN dim_dealer de ON f.dealer_id = de.dealer_id
WHERE d.date_id IS NULL OR c.customer_id IS NULL OR ca.car_key IS NULL OR de.dealer_id IS NULL
"""), engine)['orphans'][0]
print(f"[3] Khóa ngoại mồ côi: {orphan_check}")
assert orphan_check == 0, "LỖI: Có bản ghi Fact không map được vào Dimension!"

completeness = pd.read_sql(
    text(
        """
        SELECT COUNT(*) AS row_count,
               COALESCE(SUM(
                   CASE WHEN f.car_id IS NULL THEN 1 ELSE 0 END
                 + CASE WHEN f.date_id IS NULL THEN 1 ELSE 0 END
                 + CASE WHEN f.customer_id IS NULL THEN 1 ELSE 0 END
                 + CASE WHEN f.car_key IS NULL THEN 1 ELSE 0 END
                 + CASE WHEN f.dealer_id IS NULL THEN 1 ELSE 0 END
                 + CASE WHEN f.price IS NULL THEN 1 ELSE 0 END
                 + CASE WHEN d.full_date IS NULL THEN 1 ELSE 0 END
               ), 0) AS null_count
        FROM fact_car_sales AS f
        LEFT JOIN dim_date AS d ON f.date_id = d.date_id
        """
    ),
    engine,
).iloc[0]
checked_cells = int(completeness['row_count']) * 7
completeness_pct = (
    100 * (1 - int(completeness['null_count']) / checked_cells)
    if checked_cells
    else 0
)
print(f"[4] Độ đầy đủ khóa, ngày, giá: {completeness_pct:.2f}%")
assert completeness_pct == 100, "LỖI: Có giá trị khóa, ngày hoặc giá bị thiếu!"

duplicate_count = pd.read_sql(
    text(
        """
        SELECT COUNT(*) - COUNT(DISTINCT car_id) AS duplicates
        FROM fact_car_sales
        """
    ),
    engine,
)['duplicates'][0]
print(f"[5] Số car_id trùng: {duplicate_count}")
assert duplicate_count == 0, "LỖI: Fact có car_id trùng!"

loaded_dates = pd.read_sql(
    text("SELECT full_date FROM dim_date"),
    engine,
)['full_date']
month_periods = pd.to_datetime(loaded_dates).dt.to_period('M')
if month_periods.empty:
    months_with_sales = 0
    months_in_range = 0
else:
    months_with_sales = int(month_periods.nunique())
    months_in_range = len(
        pd.period_range(month_periods.min(), month_periods.max(), freq='M')
    )

coverage_pct = (
    100 * months_with_sales / months_in_range
    if months_in_range
    else 0
)
print(
    f"[6] Độ phủ chuỗi thời gian: {months_with_sales}/{months_in_range} tháng "
    f"({coverage_pct:.2f}%)"
)
assert months_with_sales >= 24, "LỖI: Cần ít nhất 24 tháng lịch sử cho dự báo mùa vụ!"

# Test 7: cars_sold của dim_car khớp fact và được sắp từ cao xuống thấp theo car_key
car_sold = pd.read_sql(
    text(
        """
        SELECT d.car_key, d.cars_sold, COUNT(f.car_id) AS fact_cnt
        FROM dim_car d
        LEFT JOIN fact_car_sales f ON f.car_key = d.car_key
        GROUP BY d.car_key, d.cars_sold
        ORDER BY d.car_key
        """
    ),
    engine,
)
sold_mismatch = int((car_sold['cars_sold'] != car_sold['fact_cnt']).sum())
sold_sorted = bool(car_sold['cars_sold'].is_monotonic_decreasing)
print(
    f"[7] dim_car.cars_sold - tổng: {int(car_sold['cars_sold'].sum())} | "
    f"dòng lệch fact: {sold_mismatch} | đã xếp giảm dần: {sold_sorted}"
)
assert car_sold['cars_sold'].sum() == db_fact_count, "LỖI: Tổng cars_sold khác số dòng fact!"
assert sold_mismatch == 0, "LỖI: cars_sold lệch so với fact_car_sales!"
assert sold_sorted, "LỖI: dim_car không xếp theo cars_sold giảm dần!"

print("\n=> TẤT CẢ CÁC KIỂM TRA CHẤT LƯỢNG ĐỀU ĐẠT!")
engine.dispose()