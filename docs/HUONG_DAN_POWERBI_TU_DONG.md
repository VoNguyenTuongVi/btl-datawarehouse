# Tự động tạo và nạp mô hình Power BI

Một lệnh chạy toàn bộ chuỗi, từ PostgreSQL đến Power BI đã có dữ liệu KPI:

```
schema.sql → etl.py → test_quality.py → forecast.py → build_marts.py → build_pbip.py → mở Power BI + Refresh
```

Power BI **không nạp bảng thô** (`dim_*`, `fact_*`). Bước `build_marts.py` tính sẵn mọi KPI trong PostgreSQL, ghi vào schema `mart`. Power BI chỉ nạp các bảng `mart` này: mỗi bảng là một nhóm KPI ở đúng mức chi tiết để vẽ biểu đồ.

## Các bảng Power BI nhận được

Tỷ lệ lưu dạng thập phân (0,05 = 5%). Mỗi bảng kèm cột thành phần (`units_py`, `revenue_py`, ...) để measure tính lại tỷ lệ đúng khi gộp nhiều dòng.

| Bảng | 1 dòng là | Số dòng | KPI | Dùng để vẽ |
| --- | --- | --- | --- | --- |
| `kpi_monthly_overview` | 1 tháng | 24 | D1–D4, D7, D14, D16, mục tiêu +5% | Thẻ KPI, line sản lượng/doanh thu, % so mục tiêu |
| `kpi_quarterly` | 1 quý | 8 | D4 (QoQ, YoY theo quý) | Column chart theo quý |
| `kpi_daily` | 1 ngày có bán | 612 | D1 theo ngày | Line theo ngày, lịch nhiệt |
| `kpi_weekday` | thứ × năm | 21 | D8 | Bar chỉ số ngày trong tuần |
| `kpi_monthly_by_dimension` | tháng × thành viên của 1 chiều | ~5.700 | D5, D6, D11–D17 | Line/bar theo hãng, mẫu, hộp số, động cơ, kiểu thân, màu, vùng, đại lý, giới tính, nhóm thu nhập |
| `kpi_dimension_summary` | năm × thành viên | ~480 | D9, D10, D12–D17, Top 5 tăng/giảm | Bảng xếp hạng, bar Top N, scatter tăng trưởng × tỷ trọng |
| `kpi_customer_segment` | năm × nhóm thu nhập × giới tính | 16 | D11, D17 | Bar phân khúc, giá/thu nhập |
| `kpi_annual_summary` | 1 năm | 2 | Tổng hợp năm, HHI, Top 10 mẫu, tháng đỉnh/đáy | Thẻ KPI năm |
| `forecast_series` | tháng × chuỗi × mô hình | ~3.400 | F1 | Line thực tế nối dự báo, dải 80% |
| `forecast_accuracy` | chuỗi × mô hình | ~110 | F2–F8, đạt/không đạt | Bảng so sánh mô hình, bar WAPE |
| `dss_forecast_plan` | tháng tới × chuỗi (mô hình chính) | ~230 | S1, S3, S4 | Bar đề xuất nhập, doanh thu dự kiến |
| `dss_dealer_allocation` | tháng tới × đại lý | ~1.200 | S2 | Bản đồ/bar phân bổ theo vùng, đại lý |
| `dss_company_priority` | 1 hãng | ~30 | S5 | Bảng xếp hạng ưu tiên nhập |
| `dq_checks` | 1 kiểm tra | 6 | Q1–Q6 | Bảng chất lượng dữ liệu |
| `kpi_parameters` | 1 dòng | 1 | Mô hình chính, ngưỡng, trọng số | Hiển thị tham số |

Năm bảng chiều dùng chung để làm slicer và trục: `dim_year`, `dim_month` (01/2022–06/2024, có cột `period_type` Thực tế/Dự báo), `dim_member` (chiều phân tích), `dim_forecast_member` (cấp và chuỗi dự báo), `dim_forecast_model`.

Mô hình Power BI còn có 69 measure trong `_Measures`, chia 7 thư mục, và 2 bảng What-if: `Demand Change` từ −30% đến +30%, `Safety Factor` từ 0 đến 2.

## Chuẩn bị (một lần)

1. Tạo file `.env` từ `.env.example` và điền mật khẩu PostgreSQL. Mật khẩu có ký tự đặc biệt thì mã hóa URL, ví dụ `@` → `%40`. Giá trị trong `.env` luôn được ưu tiên hơn biến môi trường cùng tên, nên không cần `setx` hay `$env:DATABASE_URL`.
2. Cài thư viện: `pip install -r requirements.txt`.
3. (Tùy chọn, để tự Refresh) `Install-Module SqlServer -Scope CurrentUser` trong PowerShell.

## Chạy

```powershell
python src/run_pipeline.py
```

Lần đầu tiên Power BI hỏi thông tin đăng nhập PostgreSQL: chọn **Database**, nhập user và mật khẩu, rồi bấm **Refresh**. Nếu Power BI báo máy chủ không hỗ trợ mã hóa, chọn OK. Từ lần sau, script tự Refresh.

| Lệnh | Khi nào dùng |
| --- | --- |
| `python src/run_pipeline.py --only marts powerbi` | DW và dự báo không đổi, chỉ tính lại KPI và nạp lại Power BI |
| `python src/run_pipeline.py --only forecast marts powerbi` | Chạy lại dự báo rồi cập nhật Power BI |
| `python src/run_pipeline.py --main-model holt_winters` | Đổi mô hình dự báo chính (mặc định `sarima`) |
| `python src/run_pipeline.py --safety-factor 1.5` | Đổi hệ số đệm k của S3 |
| `python src/run_pipeline.py --weights 0.4 0.3 0.15 0.15` | Đổi trọng số S5 (tăng trưởng, tỷ trọng, ổn định, độ chính xác; tổng = 1) |
| `python src/build_marts.py --wape-threshold 0.25` | Đổi ngưỡng; tương tự `--bias-threshold`, `--target-growth` |
| `python src/run_pipeline.py --no-refresh` | Mở Power BI nhưng tự bấm Refresh |

Kiểm tra nhanh KPI ngay trong PostgreSQL (pgAdmin), không cần Power BI:

```sql
SELECT * FROM mart.kpi_monthly_overview;
SELECT * FROM mart.forecast_accuracy WHERE is_main_model ORDER BY level, wape_pct;
SELECT * FROM mart.dss_company_priority ORDER BY priority_rank;
```

## Dựng visual

Dashboard thiết kế một lần trong Power BI Desktop, Ctrl+S, rồi commit thư mục `powerbi/`. Các lần chạy sau chỉ thay mô hình và dữ liệu, visual vẫn còn.

- **Trục và slicer lấy từ bảng chiều**: thời gian dùng `dim_month` (hierarchy *Thời gian*), năm dùng `dim_year`. Cột khóa trong bảng KPI đã ẩn để tránh dùng nhầm.
- **Phân tích theo chiều**: thêm slicer `dim_member[dimension_label]` (chọn 1 giá trị, ví dụ *Hộp số*), rồi đặt `dim_member[dimension_value]` lên trục, kèm measure `Dim Units`, `Dim Units YoY %`, `Dim Units Share %`. Đổi slicer là cùng biểu đồ chuyển sang Hãng, Đại lý, Giới tính, ...
- **Dự báo**: line chart với trục `dim_month[year_month_label]`, giá trị `Actual Units`, `Forecast Units`, `Forecast Lower 80`, `Forecast Upper 80`. Chưa chọn gì thì measure tự dùng cấp tổng và mô hình chính. Thêm slicer `dim_forecast_member[member]` và `dim_forecast_model[model_label]` để xem từng hãng, vùng hoặc so sánh mô hình.
- **What-if**: thêm slicer cho `Demand Change[Value]` và `Safety Factor[Value]`. Các measure `Recommended Order`, `Projected Revenue`, `Allocated Units` đổi theo ngay.
- **Tô màu đạt/không đạt**: Format › màu › **fx** › *Field value* › chọn `Units Target Color`, `Revenue Target Color`, `WAPE Color` hoặc `Bias Color`.

## Xử lý sự cố

| Hiện tượng | Cách xử lý |
| --- | --- |
| `build_marts.py` báo `fact_demand_forecast đang trống` | Chạy `forecast.py` trước (hoặc chạy cả pipeline) |
| Power BI báo không tìm thấy bảng trong schema `mart` | Chạy `python src/build_marts.py`, kiểm tra trong pgAdmin có schema `mart` |
| Lỗi `column ... not found` khi Refresh | Cột trong `kpi_marts.sql` đã đổi tên; cập nhật `MART_TABLES` trong `build_pbip.py` cho khớp |
| Power BI báo lỗi TMDL khi mở, kèm tên file và dòng | Sửa `build_pbip.py`, không sửa tay file trong `definition/` vì sẽ bị ghi đè |
| Visual cũ báo lỗi sau khi đổi mô hình | Visual đang trỏ vào bảng thô đã bỏ; kéo lại trường từ bảng `mart` mới |
| Mở được nhưng mọi bảng trống | Bấm **Refresh**. Script cố ý xóa `cache.abf` để luôn nạp dữ liệu mới |
| Lỗi đăng nhập khi script tự Refresh | Bấm Refresh trong Power BI một lần và nhập tài khoản PostgreSQL |
| Cảnh báo `[!] DATABASE_URL: biến môi trường có MẬT KHẨU KHÁC với .env` | Còn biến cũ từ `$env:` hoặc `setx`; chương trình đã dùng `.env`. Xóa biến cũ để hết cảnh báo: `Remove-Item Env:DATABASE_URL` và `[Environment]::SetEnvironmentVariable('DATABASE_URL', $null, 'User')`, rồi mở terminal mới |
| Không thấy PBIP hay TMDL trong Preview features | Bình thường: hai tính năng đã có sẵn trong bản chính thức |
