# Hướng dẫn chạy KPI – Demand Forecasting Car Sales

Tài liệu này hướng dẫn chạy toàn bộ chuỗi: tạo DW trên PostgreSQL → ETL → kiểm tra chất lượng (Q1–Q6) → dự báo (F1–F8) → truy vấn KPI (D, F, S) → Power BI. Định nghĩa KPI nằm ở [KPI_Demand_Forecasting_Car_Sales.md](KPI_Demand_Forecasting_Car_Sales.md).

## 1. Chuẩn bị

- Python 3.11+ (đã thử với 3.13), PostgreSQL ≥ 12 (có `psql`), Power BI Desktop.
- Chạy mọi lệnh từ thư mục gốc `btl-datawarehouse`.

```powershell
pip install -r requirements.txt
```

Tạo database rỗng và đặt biến môi trường (PowerShell; thay `USER`, `PASSWORD`):

```powershell
psql -U USER -h localhost -c "CREATE DATABASE car_sales_dw;"
$env:DATABASE_URL = "postgresql+psycopg2://USER:PASSWORD@localhost:5432/car_sales_dw"
```

> Nếu không đặt `DATABASE_URL`, `etl.py` và `test_quality.py` dùng SQLite `car_sales_dw.db`. SQLite **không** chạy được view/KPI SQL và `forecast.py` (cần PostgreSQL: `make_date`, `generate_series`, `ON CONFLICT`...). Muốn có KPI thì luôn đặt `DATABASE_URL`.

## 2. Các bước chạy

| Bước | Lệnh | Kết quả mong đợi |
| --- | --- | --- |
| 1. Tạo bảng, view | `psql -U USER -h localhost -d car_sales_dw -f src/schema.sql` | 5 bảng DW, `fact_demand_forecast`, view `v_monthly_demand`, `v_monthly_calendar`, `v_monthly_dimension_demand` |
| 2. ETL | `python src/etl.py` | Nạp 23.906 dòng fact; chạy lại được (tự TRUNCATE và đặt lại sequence) |
| 3. Kiểm tra chất lượng | `python src/test_quality.py` | In Q1–Q6, kết thúc "TẤT CẢ CÁC KIỂM TRA CHẤT LƯỢNG ĐỀU ĐẠT!" |
| 4. Dự báo | `python src/forecast.py` | `Upserted N forecast rows (M backtest rows)` |
| 5. KPI bằng SQL | `psql -U USER -h localhost -d car_sales_dw -f src/kpi_queries.sql` | Kết quả D1–D17, F2–F8, S1–S6, Q6 lần lượt |
| 6. Test code dự báo | `python -m pytest src/test_forecast.py -q` | 3 passed (không cần DB) |

Bước 1 phải chạy trước bước 2 (ETL cần bảng có sẵn để TRUNCATE).

### Ý nghĩa từng bước

- **Bước 3 – Q1–Q6**: Q1 khớp số dòng, Q2 khớp tổng doanh thu, Q3 khóa ngoại mồ côi, Q4 độ đầy đủ, Q5 trùng `car_id`, Q6 độ phủ chuỗi thời gian (phải ≥ 24 tháng). Script dừng bằng `assert` nếu có KPI sai. Dữ liệu tĩnh nên mọi KPI tương đối lấy mốc 31/12/2023, không dùng ngày chạy.
- **Bước 4 – forecast.py**: chạy Holt-Winters, SARIMA, seasonal naive ở 3 cấp (tổng, hãng, vùng). Backtest tháng 7–12/2023 (huấn luyện bằng 18 tháng đầu), dự báo 6 tháng 2024. Mỗi lần chạy TRUNCATE `fact_demand_forecast` rồi ghi lại, nên bảng chỉ có một bộ dự báo.
- **Bước 5**: `kpi_queries.sql` gồm nhiều truy vấn độc lập. Để xem từng KPI, mở file trong DBeaver/pgAdmin và chạy từng khối, hoặc xuất ra file: `psql ... -f src/kpi_queries.sql -o kpi_output.txt`.

## 3. Bản đồ KPI → nơi tính

| Nhóm | KPI | Nơi tính |
| --- | --- | --- |
| Chất lượng DW | Q1–Q6 | `src/test_quality.py` (Q6 còn ở khối cuối `kpi_queries.sql`) |
| Nhu cầu lịch sử | D1–D4 (ngày/tuần/tháng/quý/năm, MoM, QoQ, YoY, YTD) | `kpi_queries.sql` (4 khối đầu), DAX |
| | D5–D6, D8–D11 | `kpi_queries.sql`, DAX (D7 mùa vụ ở khối D1–D4 và DAX) |
| | D12–D17 | `kpi_queries.sql` (khối "D12–D17", "D13", "D16") |
| Độ chính xác dự báo | F2–F8 | `kpi_queries.sql` (khối "F2–F8", cấp hãng); DAX cho mọi cấp |
| | F1 | bảng `fact_demand_forecast` (`is_backtest = FALSE`) |
| Hỗ trợ quyết định | S1, S2, S3/S4/S6, S5 | `kpi_queries.sql` (khối cùng tên); DAX trong `powerbi/measures.dax` |

### Tham số có thể chỉnh

- **S3/S4/S6**: sửa `demand_change` (ví dụ `0.10` = nhu cầu +10%) và `safety_factor` (hệ số k) trong CTE `parameters` của khối "S3/S4/S6".
- **S5**: sửa 4 trọng số trong CTE `parameters` của khối S5 (hiện mặc định 0.25 mỗi cái, tổng = 1; trọng số chính thức do Người 3 chốt). S2 và S5 dùng mô hình `sarima`.

### Đọc nhanh kết quả dự báo

```sql
-- Dự báo tháng tới (tổng), 3 mô hình
SELECT month_start, model_name, forecast_units, lower_80, upper_80
FROM fact_demand_forecast
WHERE level = 'total' AND NOT is_backtest
ORDER BY month_start, model_name;
```

## 4. Power BI

1. Get Data → PostgreSQL (`localhost:5432`, database `car_sales_dw`), chế độ Import. Nạp `dim_date`, `dim_customer`, `dim_car`, `dim_dealer`, `fact_car_sales`, `fact_demand_forecast`.
2. Dán nội dung [powerbi/measures.dax](../powerbi/measures.dax) vào Power BI: bảng `Calendar` và 2 tham số What-if (New table), các measure vào bảng `_Measures`.
3. Quan hệ: mỗi dim 1–nhiều tới `fact_car_sales`; `Calendar[DateId]` → `fact_car_sales[date_id]`; `Calendar[Date]` → `fact_demand_forecast[month_start]`. Đánh dấu `Calendar` là Date Table.
4. Slicer bắt buộc cho các visual dự báo: `fact_demand_forecast[model_name]` (chọn 1 mô hình), và `level` (total/company/region). Nếu không lọc, measure dự báo sẽ cộng dồn nhiều mô hình.
5. Sau mỗi lần chạy lại `forecast.py`, bấm Refresh.

## 5. Xử lý sự cố

| Triệu chứng | Nguyên nhân / cách xử lý |
| --- | --- |
| `relation "fact_car_sales" does not exist` | Chưa chạy `schema.sql` (bước 1) |
| `Set DATABASE_URL to a PostgreSQL...` | Chưa đặt `$env:DATABASE_URL` trong cửa sổ PowerShell hiện tại |
| `duplicate key` khi nạp lại | ETL đã TRUNCATE trên PostgreSQL; nếu vẫn lỗi, kiểm tra đang trỏ đúng database |
| `forecast.py`: "DW must contain actual sales for every month from Jul-Dec 2023" | ETL chưa nạp đủ dữ liệu |
| `ConvergenceWarning` từ SARIMA | Cảnh báo, không chặn; xem mục hạn chế trong báo cáo |
