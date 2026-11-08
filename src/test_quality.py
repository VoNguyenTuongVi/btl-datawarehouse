import os
import pandas as pd
from sqlalchemy import create_engine

DATA_PATH = os.path.join(os.path.dirname(__file__), '../data/car_sales_cleaned.csv')
DB_PATH = os.path.join(os.path.dirname(__file__), '../car_sales_dw.db')

engine = create_engine(f'sqlite:///{DB_PATH}')
raw_df = pd.read_csv(DATA_PATH)

print("=== KIỂM TRA CHẤT LƯỢNG DATA WAREHOUSE ===")

# Test 1: Khớp số lượng bản ghi Fact
db_fact_count = pd.read_sql("SELECT COUNT(*) AS cnt FROM fact_car_sales", engine)['cnt'][0]
csv_count = len(raw_df)
print(f"[1] Số dòng - CSV: {csv_count} | DW: {db_fact_count}")
assert csv_count == db_fact_count, "LỖI: Số dòng không khớp!"

# Test 2: Khớp tổng doanh thu (Total Revenue)
db_revenue = pd.read_sql("SELECT SUM(price) AS total FROM fact_car_sales", engine)['total'][0]
csv_revenue = raw_df['price'].sum()
print(f"[2] Tổng doanh thu - CSV: ${csv_revenue:,.0f} | DW: ${db_revenue:,.0f}")
assert csv_revenue == db_revenue, "LỖI: Tổng tiền không khớp!"

# Test 3: Kiểm tra khóa ngoại mồ côi (Orphan FKs)
orphan_check = pd.read_sql("""
SELECT COUNT(*) AS orphans
FROM fact_car_sales f
LEFT JOIN dim_date d ON f.date_id = d.date_id
LEFT JOIN dim_customer c ON f.customer_id = c.customer_id
LEFT JOIN dim_car ca ON f.car_key = ca.car_key
LEFT JOIN dim_dealer de ON f.dealer_id = de.dealer_id
WHERE d.date_id IS NULL OR c.customer_id IS NULL OR ca.car_key IS NULL OR de.dealer_id IS NULL
""", engine)['orphans'][0]
print(f"[3] Khóa ngoại mồ côi: {orphan_check}")
assert orphan_check == 0, "LỖI: Có bản ghi Fact không map được vào Dimension!"

print("\n=> TẤT CẢ CÁC BƯỚC TEST ĐỀU ĐẠT CHUẨN 100%!")