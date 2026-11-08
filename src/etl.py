import os
import pandas as pd
from sqlalchemy import create_engine

# Tạo đường dẫn động lưu file database car_sales_dw.db ngay tại thư mục dự án
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, '../car_sales_dw.db')

# Dùng SQLite: không cần cài phần mềm, không cần mật khẩu, tự động tạo file
engine = create_engine(f'sqlite:///{DB_PATH}')

print("--- BẮT ĐẦU QUY TRÌNH ETL ---")
df = pd.read_csv('data/car_sales_cleaned.csv')
df['date'] = pd.to_datetime(df['date'])

# -------------------------------------------------------------
# 2. XỬ LÝ & NẠP DIM_DATE
# -------------------------------------------------------------
dates = pd.DataFrame({'full_date': df['date'].drop_duplicates()})
dates['date_id'] = dates['full_date'].dt.strftime('%Y%m%d').astype(int)
dates['day'] = dates['full_date'].dt.day
dates['month'] = dates['full_date'].dt.month
dates['quarter'] = dates['full_date'].dt.quarter
dates['year'] = dates['full_date'].dt.year
dates['day_of_week'] = dates['full_date'].dt.day_name()

dates.to_sql('dim_date', engine, if_exists='append', index=False)
print("-> Đã nạp dim_date!")

# -------------------------------------------------------------
# 3. XỬ LÝ & NẠP DIM_CUSTOMER
# -------------------------------------------------------------
customers = df[['customer_name', 'gender', 'annual_income', 'phone']].drop_duplicates().reset_index(drop=True)
customers['customer_id'] = customers.index + 1
customers.to_sql('dim_customer', engine, if_exists='append', index=False)
print("-> Đã nạp dim_customer!")

# -------------------------------------------------------------
# 4. XỬ LÝ & NẠP DIM_CAR
# -------------------------------------------------------------
cars = df[['company', 'model', 'engine', 'transmission', 'color', 'body_style']].drop_duplicates().reset_index(drop=True)
cars['car_key'] = cars.index + 1
cars.to_sql('dim_car', engine, if_exists='append', index=False)
print("-> Đã nạp dim_car!")

# -------------------------------------------------------------
# 5. XỬ LÝ & NẠP DIM_DEALER
# -------------------------------------------------------------
dealers = df[['dealer_no', 'dealer_name', 'dealer_region']].drop_duplicates().reset_index(drop=True)
dealers['dealer_id'] = dealers.index + 1
dealers.to_sql('dim_dealer', engine, if_exists='append', index=False)
print("-> Đã nạp dim_dealer!")

# -------------------------------------------------------------
# 6. MAP KHÓA VÀ NẠP FACT_CAR_SALES
# -------------------------------------------------------------
# Map date_id
df['date_id'] = df['date'].dt.strftime('%Y%m%d').astype(int)

# Map customer_id
df = df.merge(customers, on=['customer_name', 'gender', 'annual_income', 'phone'], how='left')

# Map car_key
df = df.merge(cars, on=['company', 'model', 'engine', 'transmission', 'color', 'body_style'], how='left')

# Map dealer_id
df = df.merge(dealers, on=['dealer_no', 'dealer_name', 'dealer_region'], how='left')

# Tạo bảng Fact hoàn chỉnh
fact_sales = df[['car_id', 'date_id', 'customer_id', 'car_key', 'dealer_id', 'price']].copy()
fact_sales['quantity'] = 1

fact_sales.to_sql('fact_car_sales', engine, if_exists='append', index=False)
print("-> Đã nạp fact_car_sales thành công!")
print(f"Tổng số bản ghi fact đã nạp: {len(fact_sales)}")