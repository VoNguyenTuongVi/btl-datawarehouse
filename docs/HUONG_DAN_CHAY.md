# Hướng dẫn chạy từ đầu đến cuối

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
py -3 -m pip install -r requirements.txt
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
py -3 src/run_pipeline.py
```

Lệnh này chạy lần lượt `schema → etl → test → forecast → marts → powerbi`, sau đó mở Power BI Desktop và tự Refresh. Không cần xuất JSON để chạy frontend.

| Mục đích | Lệnh |
| --- | --- |
| Chỉ sinh lại mô hình và mở Power BI | `py -3 src/run_pipeline.py --only powerbi` |
| Dự báo lại rồi cập nhật mart và Power BI | `py -3 src/run_pipeline.py --only forecast marts powerbi` |
| Bỏ bước kiểm tra | `py -3 src/run_pipeline.py --skip test` |
| Không mở Power BI | `py -3 src/run_pipeline.py --no-open` |
| Mở Power BI nhưng không tự Refresh | `py -3 src/run_pipeline.py --no-refresh` |
| Đổi mô hình chính | `--main-model sarima` (hoặc `holt_winters`, `seasonal_naive`) |

## 4. Cách từng bước (khi cần tìm lỗi)

| Bước | Lệnh | Kết quả mong đợi |
| --- | --- | --- |
| 1. Tạo bảng, view | `psql -U postgres -h localhost -d car_sales_dw -f src/schema.sql` | 4 bảng chiều, `fact_car_sales`, `fact_demand_forecast`, các view |
| 2. ETL | `py -3 src/etl.py` | Nạp 23.906 dòng; chạy lại được |
| 3. Kiểm tra chất lượng | `py -3 src/test_quality.py` | Q1–Q6 đạt |
| 4. Dự báo | `py -3 src/forecast.py` | 3 mô hình × 3 cấp; backtest 07–12/2023, dự báo 01–06/2024 |
| 5. Tạo mart KPI | `py -3 src/build_marts.py` | Tạo schema `mart` (20 bảng; 6 bảng DW trong schema `public` được Power BI nạp trực tiếp), gồm cột `dim_month.has_forecast_data` cho DSS |
| 6. Sinh mô hình Power BI | `py -3 src/powerbi/build_pbip.py` | Sinh TMDL (20 bảng mart, 6 bảng DW, 6 bảng tham số, 1 bảng measure, 26 quan hệ, 131 measure gồm 12 measure testcase và 2 measure ở bảng tham số) |
| 7. Mở và Refresh | Mở `powerbi/CarSalesDSS.pbip` | Xem mục 5 |

Thứ tự bắt buộc: bước 1 trước bước 2; bước 4 trước bước 5; bước 5 trước bước 6.

Sau khi DB sẵn sàng, chạy frontend bằng hai Terminal: gốc dự án chạy `py -3 src/api.py`; Terminal khác vào `frontend`, chạy `npm ci` rồi `npm run dev`. Mở `http://127.0.0.1:5173`. Nút **Nạp lại dữ liệu** truy vấn lại DB; có tùy chọn tự cập nhật mỗi 30 giây.

Đổi ngưỡng khi tạo mart:

```powershell
py -3 src/build_marts.py --target-growth 0.05 --wape-threshold 0.20 --bias-threshold 0.05
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
py -3 -m pytest -q src/test_forecast.py tests        # dự báo + tích hợp DSS; không cần DB
psql -U postgres -h localhost -d car_sales_dw -c "SELECT * FROM mart.kpi_monthly_overview;"
```

Đối chiếu số trên visual với `mart.*` và `kpi_output.txt`.

## 7. Xử lý sự cố

| Triệu chứng | Cách xử lý |
| --- | --- |
| `relation "fact_car_sales" does not exist` | Chưa chạy `schema.sql` |
| Cảnh báo mật khẩu khác nhau | `Remove-Item Env:DATABASE_URL`; dùng giá trị trong `.env` |
| `pytest -q src` báo `No module named 'src'` | Dùng `py -3 -m pytest -q src` |
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
