# CLAUDE.md – Bối cảnh dự án cho Claude

Bài tập lớn môn **Data Warehouse (CO4031, HK261)**: xây dựng **Data Warehouse + Decision Support System** cho chủ đề **Demand Forecasting** trên dataset [Car Sales Report (Kaggle)](https://www.kaggle.com/datasets/missionjee/car-sales-report). Công cụ: **PostgreSQL** (DW) và **Power BI Desktop** (DSS), code Python trên Windows/PowerShell. Trả lời người dùng bằng **tiếng Việt**.

## Vai trò của chúng ta: Người 2 (KPI, OLAP/DAX, Power BI, Dashboard)

| Giai đoạn | Người 1 | **Người 2 (chúng ta)** | Người 3 |
| --- | --- | --- | --- |
| 06/11 | EDA, làm sạch | **Thiết kế KPI** ✅ | Thiết kế DSS |
| 07/11 | Star Schema, SQL | **Chuẩn bị Power BI** ✅ | Công thức, trọng số |
| 08–09/11 | ETL, nạp DW | **OLAP, DAX** ✅ | DSS Measures |
| 10–12/11 | Kiểm tra dữ liệu | **Dashboard** ⏳ | DSS + What-if |
| 13–14/11 | Test ETL | **Test dashboard** | Test DSS |
| 15/11 | Tích hợp, nộp | Tích hợp, nộp | Tích hợp, nộp |

Mục tiêu của Người 2: biến DW thành **KPI tính sẵn** và một **mô hình Power BI sinh tự động**, để dashboard trả lời được: *tháng tới cần bao nhiêu xe, ở hãng/vùng/đại lý nào, và dự báo đáng tin đến mức nào.* Người 3 dùng lại measure/bảng DSS của chúng ta, không viết lại.

## Kiến trúc và luồng chạy

```
data/car_sales_cleaned.csv
  → schema.sql (star schema: dim_date, dim_customer, dim_car, dim_dealer, fact_car_sales,
                 fact_demand_forecast, view v_monthly_demand, v_monthly_dimension_demand)
  → etl.py → test_quality.py → forecast.py (Holt-Winters, SARIMA, seasonal naive)
  → build_marts.py + kpi_marts.sql  (schema "mart": KPI đã tổng hợp)
  → powerbi/build_pbip.py            (sinh TMDL, Power BI CHỈ nạp bảng mart.*)
  → refresh_powerbi.ps1              (mở Power BI Desktop + Refresh qua XMLA)
```

Một lệnh chạy tất cả: `python src/run_pipeline.py`
- Chỉ một phần: `--only marts powerbi`, `--only forecast marts powerbi`, `--skip test`
- Tham số DSS: `--main-model sarima|holt_winters|seasonal_naive`, `--safety-factor 1.5`, `--weights 0.25 0.25 0.25 0.25` (S5: tăng trưởng, tỷ trọng, ổn định, độ chính xác; tổng = 1)
- Ngưỡng: `python src/build_marts.py --target-growth 0.05 --wape-threshold 0.20 --bias-threshold 0.05`
- Test: `pytest -q src`

## Bản đồ file

| File | Vai trò |
| --- | --- |
| `src/env_config.py` | Đọc `.env`; **`.env` luôn ghi đè biến môi trường cùng tên** (cảnh báo nếu khác) |
| `src/database.py` | `create_database_engine()` dùng chung cho ETL/test |
| `src/schema.sql`, `src/etl.py`, `src/test_quality.py` | DW và kiểm thử (phần của Người 1) |
| `src/forecast.py`, `src/test_forecast.py` | Dự báo 3 cấp (total/company/region) × 3 mô hình; backtest 07–12/2023, dự báo 01–06/2024; TRUNCATE trước khi ghi |
| `src/kpi_queries.sql`, `kpi_output.txt` | Truy vấn KPI tham chiếu và kết quả để đối chiếu |
| `src/kpi_marts.sql` | **Nguồn sự thật của KPI**: tạo lại toàn bộ schema `mart` |
| `src/build_marts.py` | Ghi `mart.kpi_parameters`, chạy `kpi_marts.sql`, thêm Q1–Q2 (so CSV) |
| `src/powerbi/build_pbip.py` | Sinh `powerbi/CarSalesDSS.SemanticModel/definition/*.tmdl` (bảng, quan hệ, 69 measure) |
| `src/powerbi/refresh_powerbi.ps1` | Tìm cổng Analysis Services của Power BI Desktop, gửi TMSL refresh (cần module SqlServer) |
| `src/run_pipeline.py` | Điều phối các bước trên |
| `powerbi/CarSalesDSS.pbip`, `.Report/` | Dự án Power BI; **report do người thiết kế, script không ghi đè** |
| `docs/KPI_Demand_Forecasting_Car_Sales.md` | Danh mục KPI đầy đủ |
| `docs/HUONG_DAN_POWERBI_TU_DONG.md` | Hướng dẫn pipeline, bảng mart, dựng visual, xử lý sự cố |
| `docs/HUONG_DAN_CHAY_KPI.md` | Hướng dẫn chạy KPI |

## Bộ KPI (37 chỉ số, 4 nhóm)

- **Q1–Q6 Chất lượng DW**: khớp số dòng, sai lệch doanh thu, khóa ngoại mồ côi, đầy đủ, trùng car_id, độ phủ ≥ 24 tháng. (Đã bỏ "độ tươi dữ liệu" vì dữ liệu tĩnh.)
- **D1–D17 Nhu cầu lịch sử**: sản lượng, doanh thu, ASP, tăng trưởng MoM/QoQ/YoY/YTD; tỷ trọng kiểu thân/màu; vùng; mùa vụ; ngày trong tuần; CV; tập trung (Top 10, HHI); phân khúc thu nhập; và sản lượng/doanh thu/tăng trưởng theo hãng (D12), mẫu (D13), hộp số (D14), động cơ (D15), đại lý (D16), giới tính (D17).
- **F1–F8 Độ chính xác dự báo**: dự báo + khoảng 80%, MAPE, WAPE/Accuracy, MAE/RMSE, Bias, Tracking Signal, FVA (so seasonal naive), độ phủ khoảng.
- **S1–S6 Hỗ trợ quyết định**: tăng trưởng dự báo, phân bổ theo vùng/đại lý (dự báo tổng × tỷ trọng 6 tháng cuối), đề xuất nhập `F × (1 + k × CV)`, doanh thu dự kiến `F × ASP`, điểm ưu tiên hãng (4 thành phần min-max), What-if.
- **Mục tiêu và ngưỡng**: mục tiêu = cùng kỳ năm trước +5%; dự báo đạt khi WAPE ≤ 20% và |Bias| ≤ 5% (cấp tháng × hãng).
- **A1–A11 Nâng cao** (cần thêm tồn kho, giá vốn, CRM...): chỉ đưa vào phần hướng phát triển.

## Lớp mart (Power BI chỉ nạp các bảng này)

- **Chiều dùng chung**: `dim_year`, `dim_month` (01/2022–06/2024, `period_type` Thực tế/Dự báo), `dim_member` (chiều phân tích dạng dài, khóa `member_key`), `dim_forecast_member` (`series_key` = level|member), `dim_forecast_model`.
- **KPI lịch sử**: `kpi_monthly_overview`, `kpi_quarterly`, `kpi_daily`, `kpi_weekday`, `kpi_monthly_by_dimension`, `kpi_dimension_summary`, `kpi_customer_segment`, `kpi_annual_summary`.
- **Dự báo**: `forecast_series`, `forecast_accuracy`. **DSS**: `dss_forecast_plan`, `dss_dealer_allocation`, `dss_company_priority`. **Khác**: `kpi_parameters`, `dq_checks`.

Quy ước bắt buộc khi sửa KPI:
1. Tỷ lệ lưu dạng thập phân (0.05 = 5%); luôn kèm **cột thành phần** (`units_py`, `abs_error_total`, ...) để measure **tính lại tỷ lệ từ tổng**, không bao giờ cộng/trung bình phần trăm.
2. Thêm/đổi cột trong `kpi_marts.sql` thì **phải cập nhật `MART_TABLES`** (và nếu cần `RELATIONSHIPS`, `TEXT_COLS`/`INT_COLS`...) trong `build_pbip.py`, nếu không Power BI báo lỗi cột khi Refresh.
3. Lịch tháng phải **dày đủ 24 tháng** cho mỗi thành viên trước khi dùng `LAG(..., 12)`.
4. Measure dự báo mặc định **cấp tổng + mô hình chính** khi chưa có slicer (`level_default`, `main_model` trong `build_pbip.py`); accuracy mặc định **cấp hãng**.
5. Trục thời gian trong Power BI dùng `dim_month`/`dim_year`; khóa ngoại trong bảng KPI đã ẩn.

## Quyết định đã chốt

- Dataset **tĩnh** 01/2022–12/2023 (23.906 giao dịch, tổng ~671,5 triệu USD), không cập nhật thêm. Mọi mốc "gần nhất" tính từ 31/12/2023; không dùng KPI đo khoảng cách tới ngày hiện tại.
- Nhu cầu = xe đã bán (proxy, không có nhu cầu bị mất). Dự báo chỉ ở cấp tổng/hãng/vùng vì dữ liệu thưa (~1.000 xe/tháng, ~30 hãng); đại lý nhận qua phân bổ tỷ trọng.
- Mô hình chính mặc định **SARIMA** (backtest thật: cấp tổng WAPE 6,3%, Bias −0,6%; Holt-Winters 21,5%). Ở cấp hãng chưa mô hình nào đạt ngưỡng (HW 22,1%, SARIMA 27,5%) → ghi là hạn chế của dữ liệu.
- Dự án Power BI dạng **PBIP/TMDL** (đã có sẵn trong bản Power BI hiện tại, không cần bật preview). Import mode qua connector PostgreSQL.
- Bí mật chỉ nằm trong `.env` (đã gitignore); `.env.example` là mẫu.

## Lưu ý khi làm việc trong repo

- **Không sửa tay** file trong `powerbi/CarSalesDSS.SemanticModel/definition/`: mỗi lần chạy `build_pbip.py` xóa và sinh lại. Sửa ở `build_pbip.py` hoặc `kpi_marts.sql`.
- `powerbi/measures.dax` là bản cũ, tham chiếu bảng thô đã bỏ; không dùng.
- Power BI Desktop chỉ chạy trên Windows; sau khi sinh lại mô hình phải đóng và mở lại `.pbip`. Lần đầu phải nhập tài khoản PostgreSQL trong Power BI.
- Kiểm tra KPI nhanh trong pgAdmin: `SELECT * FROM mart.kpi_monthly_overview;`, đối chiếu với `kpi_output.txt`.
- Dữ liệu cần để ý: `dim_customer` gần như 1 khách/1 giao dịch; thu nhập 13.500 lặp nhiều (có thể là giá trị giữ chỗ); mỗi tên đại lý xuất hiện ở nhiều vùng (196 cặp đại lý × vùng).
- Git: tạo nhánh cho mỗi thay đổi, merge vào `main` sau khi người dùng xác nhận chạy ổn.

## Việc còn mở

- [ ] Thiết kế các trang dashboard trong `CarSalesDSS.Report` (Tổng quan, Phân tích theo chiều, Dự báo, DSS & What-if, Chất lượng DW), rồi Ctrl+S và commit.
- [ ] Test dashboard: số trên visual khớp `mart.*` và `kpi_output.txt`; slicer, What-if, tô màu đạt/không đạt hoạt động.
- [ ] Người 3 chốt trọng số S5 (đang 0,25 mỗi thành phần) và danh sách measure DSS cần dùng.
- [ ] Chạy end-to-end trên máy Windows: `python src/run_pipeline.py` không lỗi.
