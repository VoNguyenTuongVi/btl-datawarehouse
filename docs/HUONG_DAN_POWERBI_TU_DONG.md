# Tự động tạo và nạp mô hình Power BI

Một lệnh chạy toàn bộ chuỗi, từ PostgreSQL đến Power BI đã có dữ liệu:

```
schema.sql → etl.py → test_quality.py → forecast.py → build_pbip.py → mở Power BI + Refresh
```

Dự án Power BI được lưu ở dạng **PBIP** (Power BI Project): mô hình là các file văn bản TMDL, nên script sinh ra được từ code thay vì làm tay trong Power BI Desktop.

## Script sinh ra những gì

`src/powerbi/build_pbip.py` ghi lại toàn bộ `powerbi/CarSalesDSS.SemanticModel/` mỗi lần chạy:

| Thành phần | Nội dung |
| --- | --- |
| Bảng nguồn (Import từ PostgreSQL) | `dim_customer`, `dim_car`, `dim_dealer`, `fact_car_sales`, `fact_demand_forecast` |
| Bảng tạo bằng DAX | `Calendar` 01/2022–12/2024 (đã đánh dấu Date Table, có Date Hierarchy), `Demand Change` −30%…+30%, `Safety Factor` 0–2, `_Measures` |
| Quan hệ | 4 dim → `fact_car_sales`; `Calendar[Date]` → `fact_demand_forecast[month_start]` |
| Hierarchy | `Product` (company › model), `Geography` (dealer_region › dealer_name) |
| Tham số kết nối | `PgServer`, `PgDatabase`, `PgSchema` (lấy từ `DATABASE_URL`) |
| 67 measure, chia 5 thư mục | Nhu cầu lịch sử (D1–D17), Dự báo (F1–F8), Hỗ trợ quyết định (S1–S6), What-if, Mục tiêu & ngưỡng |

Thư mục `CarSalesDSS.Report/` (các trang dashboard) chỉ được tạo trống ở lần chạy đầu. Các lần sau script **không đụng tới**, nên dashboard thiết kế trong Power BI Desktop được giữ nguyên.

## Chuẩn bị (một lần)

1. Đặt biến môi trường (PowerShell):
   ```powershell
   setx DATABASE_URL "postgresql+psycopg2://postgres:<mật khẩu>@localhost:5432/car_sales_dw"
   ```
   Mở cửa sổ terminal mới sau khi chạy `setx`.
2. để tự Refresh, cài module PowerShell:
   ```powershell
   Install-Module SqlServer -Scope CurrentUser
   ```

## Chạy

```powershell
python src/run_pipeline.py
```

Lần đầu tiên Power BI hỏi thông tin đăng nhập PostgreSQL: chọn **Database**, nhập user và mật khẩu, rồi bấm **Refresh**. Nếu Power BI báo máy chủ không hỗ trợ mã hóa, chọn OK để kết nối không mã hóa (bình thường với PostgreSQL chạy trên máy). Power BI lưu thông tin đăng nhập này trên máy, nên từ lần sau script tự Refresh, không cần nhập lại.

Các tùy chọn hay dùng:

| Lệnh | Khi nào dùng |
| --- | --- |
| `python src/run_pipeline.py --only powerbi` | Chỉ sửa measure hoặc mô hình, DW không đổi |
| `python src/run_pipeline.py --only forecast powerbi` | Chạy lại dự báo rồi cập nhật Power BI |
| `python src/run_pipeline.py --main-model holt_winters` | Đổi mô hình dự báo chính (mặc định `sarima`) |
| `python src/run_pipeline.py --no-refresh` | Mở Power BI nhưng tự bấm Refresh |
| `python src/powerbi/build_pbip.py --wape-threshold 0.25` | Đổi ngưỡng; tương tự `--bias-threshold`, `--target-growth` |

## Dashboard: thiết kế một lần, giữ mãi

1. Chạy pipeline lần đầu. Power BI mở với trang trống "Tổng quan" và đủ bảng, measure.
2. Kéo thả visual theo bố cục trong tài liệu KPI, rồi **Ctrl+S**: Power BI lưu vào `CarSalesDSS.Report/`.
3. Commit thư mục `powerbi/` lên Git. Các lần sau, `run_pipeline.py` chỉ thay mô hình và nạp lại dữ liệu; visual vẫn còn.

Lưu ý khi dựng visual:

- **Trục thời gian luôn dùng cột của `Calendar`** (`YearMonth`, `Date Hierarchy`), không dùng `month_start` của bảng dự báo, vì các measure so sánh cùng kỳ cần lọc theo `Calendar`.
- Các measure dự báo mặc định dùng mô hình chính và cấp tổng. Đặt `fact_demand_forecast[member]` lên trục là tự chuyển sang cấp hãng hoặc vùng. Thêm slicer `model_name` để so sánh mô hình.
- Tô màu đạt/không đạt: chọn visual › Format › màu chữ hoặc nền › **fx** › Format style = *Field value* › chọn `Units Target Color`, `Revenue Target Color`, `WAPE Color` hoặc `Bias Color`.

## Xử lý sự cố

| Hiện tượng | Cách xử lý |
| --- | --- |
| Không thấy mục PBIP hay TMDL trong Preview features | Bình thường: hai tính năng đã ra bản chính thức nên không còn ở đó. Chỉ cần mở file `CarSalesDSS.pbip` |
| Power BI báo lỗi TMDL khi mở, kèm tên file và dòng | Gửi thông báo lỗi để sửa `build_pbip.py`; không sửa tay file trong `definition/` vì sẽ bị ghi đè |
| Mở được nhưng mọi bảng trống | Bấm **Refresh**. Script cố ý xóa `cache.abf` để luôn nạp dữ liệu mới |
| Lỗi đăng nhập khi script tự Refresh | Bấm Refresh trong Power BI một lần và nhập tài khoản PostgreSQL |
| `refresh_powerbi.ps1` báo chưa có module SqlServer | Chạy `Install-Module SqlServer -Scope CurrentUser`, hoặc dùng `--no-refresh` |
| Sửa code nhưng Power BI không thay đổi | Power BI không tự nhận file đổi từ bên ngoài; script sẽ hỏi đóng Power BI rồi mở lại |
| Measure dự báo trống | Kiểm tra `forecast.py` đã ghi `fact_demand_forecast` và có dòng của mô hình chính đang chọn |
