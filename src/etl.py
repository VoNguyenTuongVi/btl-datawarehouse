import pandas as pd
from sqlalchemy import text

from database import PROJECT_ROOT, create_database_engine

DATA_PATH = PROJECT_ROOT / 'data' / 'car_sales_cleaned.csv'
engine = create_database_engine()

print("--- BẮT ĐẦU QUY TRÌNH ETL ---")
df = pd.read_csv(DATA_PATH)
df['date'] = pd.to_datetime(df['date'])

# Make repeated loads idempotent while retaining the existing SQLite workflow.
with engine.begin() as connection:
    if engine.dialect.name == 'postgresql':
        connection.execute(
            text(
                'TRUNCATE fact_car_sales, dim_customer, dim_car, dim_dealer, dim_date '
                'RESTART IDENTITY CASCADE'
            )
        )
    else:
        for table_name in (
            'fact_car_sales',
            'dim_customer',
            'dim_car',
            'dim_dealer',
            'dim_date',
        ):
            if engine.dialect.has_table(connection, table_name):
                connection.execute(text(f'DELETE FROM {table_name}'))

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
CAR_COLS = ['company', 'model', 'engine', 'transmission', 'color', 'body_style']
# cars_sold: mỗi dòng gốc xuất hiện 1 lần = bán 1 xe (đếm trên dữ liệu chưa lọc).
# Cấu hình nào chưa có dòng nào thì cars_sold = 0 (fillna), dù hiện tại mọi cấu hình đều có.
cars = df[CAR_COLS].drop_duplicates()
sold = df.groupby(CAR_COLS, dropna=False).size().rename('cars_sold').reset_index()
cars = cars.merge(sold, on=CAR_COLS, how='left')
cars['cars_sold'] = cars['cars_sold'].fillna(0).astype(int)
# Sắp xếp giảm dần theo cars_sold rồi gán car_key theo thứ tự đó, nên ORDER BY car_key
# cũng cho đúng thứ tự cao -> thấp. Thêm các cột còn lại để thứ tự ổn định giữa các lần chạy.
cars = cars.sort_values(['cars_sold'] + CAR_COLS, ascending=[False] + [True] * len(CAR_COLS)).reset_index(drop=True)
cars['car_key'] = cars.index + 1
cars.to_sql('dim_car', engine, if_exists='append', index=False)
print("-> Đã nạp dim_car!")

# -------------------------------------------------------------
# 5. XỬ LÝ & NẠP DIM_DEALER
# -------------------------------------------------------------
dealers = df[['dealer_name', 'dealer_region']].drop_duplicates().reset_index(drop=True)
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
df = df.merge(dealers, on=['dealer_name', 'dealer_region'], how='left')

# Tạo bảng Fact hoàn chỉnh
fact_sales = df[['car_id', 'date_id', 'customer_id', 'car_key', 'dealer_id', 'price']].copy()
fact_sales['quantity'] = 1

fact_sales.to_sql('fact_car_sales', engine, if_exists='append', index=False)
print("-> Đã nạp fact_car_sales thành công!")
print(f"Tổng số bản ghi fact đã nạp: {len(fact_sales)}")

if engine.dialect.name == 'postgresql':
    with engine.begin() as connection:
        for table_name, id_column in (
            ('dim_customer', 'customer_id'),
            ('dim_car', 'car_key'),
            ('dim_dealer', 'dealer_id'),
        ):
            connection.execute(
                text(
                    "SELECT setval(pg_get_serial_sequence(:table_name, :id_column), "
                    f"(SELECT MAX({id_column}) FROM {table_name}), TRUE)"
                ),
                {'table_name': table_name, 'id_column': id_column},
            )

engine.dispose()