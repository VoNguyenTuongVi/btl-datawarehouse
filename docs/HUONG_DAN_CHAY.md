# Hướng dẫn chạy từ đầu đến cuối

Từ file CSV đến dashboard Power BI. Mọi lệnh chạy ở **PowerShell**, tại thư mục gốc `btl-datawarehouse`.

```
CSV → schema.sql → etl.py → test_quality.py → forecast.py → build_marts.py → build_pbip.py → Power BI
```

## 1. Cài đặt một lần

| Cần có | Ghi chú |
| --- | --- |
| Python 3.11+ | Đã thử với 3.13 |
| PostgreSQL ≥ 12 | Có `psql` trong PATH |
| Power BI Desktop | Chỉ chạy trên Windows |
| Module PowerShell `SqlServer` | Để tự Refresh (không bắt buộc) |

```powershell
pip install -r requirements.txt
Install-Module SqlServer -Scope CurrentUser      # tùy chọn
```

## 2. Cấu hình kết nối

Tạo file `.env` từ mẫu `.env.example`rồi sửa mật khẩu. File này đã nằm sẵn trong `.gitignore`, không bị commit lộ mật khẩu.

Giá trị trong `.env` đã được cài đặt luôn thắng biến môi trường cùng tên. Tuy nhiên, nếu thấy cảnh báo "biến môi trường có MẬT KHẨU KHÁC", xóa biến cũ: `Remove-Item Env:DATABASE_URL`.

Tạo database rỗng (một lần):

```powershell
psql -U postgres -h localhost -c "CREATE DATABASE car_sales_dw;"
```

## 3. Cách nhanh: một lệnh chạy tất cả

```powershell
python src/run_pipeline.py
```

Lệnh này chạy lần lượt `schema → etl → test → forecast → marts → powerbi`, sau đó mở Power BI Desktop và tự Refresh.

| Mục đích | Lệnh |
| --- | --- |
| Chỉ sinh lại mô hình và mở Power BI | `python src/run_pipeline.py --only powerbi` |
| Dự báo lại rồi cập nhật mart và Power BI | `python src/run_pipeline.py --only forecast marts powerbi` |
| Bỏ bước kiểm tra | `python src/run_pipeline.py --skip test` |
| Không mở Power BI | `python src/run_pipeline.py --no-open` |
| Mở Power BI nhưng không tự Refresh | `python src/run_pipeline.py --no-refresh` |
| Đổi mô hình chính | `--main-model sarima` (hoặc `holt_winters`, `seasonal_naive`) |

## 4. Cách từng bước (khi cần tìm lỗi)

| Bước | Lệnh | Kết quả mong đợi |
| --- | --- | --- |
| 1. Tạo bảng, view | `psql -U postgres -h localhost -d car_sales_dw -f src/schema.sql` | 4 bảng chiều, `fact_car_sales`, `fact_demand_forecast`, các view |
| 2. ETL | `python src/etl.py` | Nạp 23.906 dòng; chạy lại được |
| 3. Kiểm tra chất lượng | `python src/test_quality.py` | Q1–Q6 đạt |
| 4. Dự báo | `python src/forecast.py` | 3 mô hình × 3 cấp; backtest 07–12/2023, dự báo 01–06/2024 |
| 5. Tạo mart KPI | `python src/build_marts.py` | Tạo schema `mart` (18 bảng; 6 bảng DW trong schema `public` được Power BI nạp trực tiếp) |
| 6. Sinh mô hình Power BI | `python src/powerbi/build_pbip.py` | Sinh TMDL (18 bảng mart, 6 bảng DW, 1 bảng measure, 23 quan hệ, 70 measure) |
| 7. Mở và Refresh | Mở `powerbi/CarSalesDSS.pbip` | Xem mục 5 |

Thứ tự bắt buộc: bước 1 trước bước 2; bước 4 trước bước 5; bước 5 trước bước 6.

Đổi ngưỡng khi tạo mart:

```powershell
python src/build_marts.py --target-growth 0.05 --wape-threshold 0.20 --bias-threshold 0.05
```

Nếu console báo lỗi mã hóa tiếng Việt, đặt trước: `$env:PYTHONUTF8 = "1"`.

## 5. Mở và Refresh trong Power BI

1. **Đóng** Power BI Desktop nếu đang mở (bắt buộc sau mỗi lần sinh lại mô hình).
2. Mở `powerbi/CarSalesDSS.pbip`.
3. Lần đầu: nhập tài khoản PostgreSQL (Database → user `postgres` và mật khẩu).
4. Bấm **Refresh** trên thanh Home. Hoặc tự động:

```powershell
powershell -ExecutionPolicy Bypass -File src\powerbi\refresh_powerbi.ps1
```

5. Kiểm tra: kéo `Units`, `WAPE %`, `MAPE %`, `Units` vào Card. Measure chỉ hiện số khi nằm trong visual, panel Fields không hiện số.

Report trong `CarSalesDSS.Report` do người thiết kế, script không ghi đè. Sau khi chỉnh dashboard, bấm Ctrl+S.

## 6. Kiểm tra kết quả

```powershell
python -m pytest -q src                              # 3 test đạt
psql -U postgres -h localhost -d car_sales_dw -c "SELECT * FROM mart.kpi_monthly_overview;"
```

Đối chiếu số trên visual với `mart.*` và `kpi_output.txt`.

## 7. Xử lý sự cố

| Triệu chứng | Cách xử lý |
| --- | --- |
| `relation "fact_car_sales" does not exist` | Chưa chạy `schema.sql` |
| Cảnh báo mật khẩu khác nhau | `Remove-Item Env:DATABASE_URL`; dùng giá trị trong `.env` |
| `pytest -q src` báo `No module named 'src'` | Dùng `python -m pytest -q src` |
| Power BI báo "Unexpected character… T" khi mở `.pbip` | File `.pbip` có `True` viết hoa; sửa thành `true` |
| Power BI báo lỗi cột khi Refresh | Thêm cột ở `kpi_marts.sql` mà chưa cập nhật `MART_TABLES` trong `build_pbip.py`; chạy lại bước 5 và 6 |
| Measure không có số | Chưa Refresh, hoặc chưa kéo vào visual |
| `refresh_powerbi.ps1` báo thiếu module | `Install-Module SqlServer -Scope CurrentUser`, hoặc bấm Refresh tay |
| Mô hình vừa sinh lại không thấy thay đổi | Đóng hẳn Power BI rồi mở lại `.pbip` |
| `ConvergenceWarning` từ SARIMA | Chỉ là cảnh báo, không chặn |

**Không sửa tay** các file trong `powerbi/CarSalesDSS.SemanticModel/definition/`: mỗi lần chạy `build_pbip.py` chúng bị xóa và sinh lại. Sửa ở `src/powerbi/build_pbip.py` hoặc `src/kpi_marts.sql`.

## 8. Tài liệu liên quan

- [KPI_Demand_Forecasting_Car_Sales.md](KPI_Demand_Forecasting_Car_Sales.md): danh mục KPI đầy đủ
- [HUONG_DAN_POWERBI_TU_DONG.md](HUONG_DAN_POWERBI_TU_DONG.md): bảng mart, dựng visual, sự cố Power BI

## 9. Kiểm tra bảng riêng
psql -U postgres -h localhost -d car_sales_dw
SELECT * FROM fact_car_sales LIMIT 5;