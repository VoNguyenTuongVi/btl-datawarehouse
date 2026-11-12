HƯỚNG DẪN CHẠY VÀ KIỂM THỬ DSS S5/S6

## I. Chuẩn bị

1. Cài PostgreSQL, chạy pipeline DW + dự báo.
2. Giải nén toàn bộ ZIP; **mở file `powerbi/CarSalesDSS.pbip`**, không mở riêng `.tmdl`.
3. Trong Power BI Desktop, đăng nhập nguồn PostgreSQL, chọn `Home > Refresh`, chờ hoàn tất.
4. Mở trang `DSS S5 – Priority Ranking`; nếu trang chưa hiển thị dữ liệu, kiểm tra mô hình `sarima`, tháng `202401` và dữ liệu `is_backtest=False, level=company` trong Data view.

## II. Kiểm thử S5

| Mã | Thao tác | Kết quả đúng |
|---|---|---|
| S5-01 | Không chọn tháng/mô hình | S5 dùng mặc định `202401 / sarima` |
| S5-02 | Chọn `202401`, `sarima` | Mỗi `dim_car[company]` có forecast riêng, không lặp dự báo tổng |
| S5-03 | Đối soát Growth bằng SQL/Python: `(F_202401−Actual_202301)/Actual_202301` | `Priority Growth Raw` đúng theo từng hãng, hãng không có năm trước thì BLANK |
| S5-04 | Chọn tháng dự báo 2024 | `Priority Accuracy Raw` vẫn dùng **backtest lịch sử**, không bị BLANK do lọc 2024 |
| S5-05 | Tạo Table `dim_car[company]`, 4 Raw, `Priority Eligible` | Hãng thiếu 1 Raw có `Eligible=0`, không xếp hạng |
| S5-06 | Đưa 4 `Priority ... Score` vào Table | Mỗi giá trị hợp lệ trong `[0,1]`; mỗi tiêu chí Min/Max trên cùng tập hãng đủ dữ liệu |
| S5-07 | Chọn Weight `25/25/25/25` | Bốn `Priority Weight ...` bằng 25% |
| S5-08 | Chọn Weight `50/25/25/25` | Bốn Weight bằng `40/20/20/20%` |
| S5-09 | Chọn Weight `100/0/0/0` | `Priority Score = Priority Growth Score` cho từng hãng hợp lệ |
| S5-10 | Chọn Weight `0/0/0/0` | Bốn Weight tự về 25% |
| S5-11 | Sắp xếp `Priority Rank` tăng dần | Điểm cao nhất Rank=1; bằng điểm cùng hạng (Dense) |
| S5-12 | Chọn nhiều tháng/mô hình nếu slicer cho phép | Không cộng lẫn; measure DSS mục tiêu trống, cần chọn lại một giá trị |

## III. Kiểm thử S6

| Mã | Thao tác | Kết quả đúng |
|---|---|---|
| S6-01 | Chọn tháng `202401`, model `sarima` | Bảng `fact_demand_forecast[member]` hiển thị forecast cấp hãng |
| S6-02 | Demand Change = 0%, Safety Factor = 1 | Order/Revenue Baseline = Scenario; hai Delta = 0 |
| S6-03 | Demand Change = +20%, Safety Factor = 1 | Order Scenario ≥ Order Baseline; Revenue Scenario = 1,2× Revenue Baseline |
| S6-04 | Demand Change = 0%, tăng Safety Factor 1 → 2 | Order Scenario không giảm; Revenue Scenario = Revenue Baseline |
| S6-05 | Demand Change = −20% | Doanh thu Scenario giảm 20% so Baseline |
| S6-06 | Công thức số xe nhập | `OrderBaseline` và `OrderScenario` không âm, làm tròn lên đến số nguyên |
| S6-07 | Không có CV, ASP hoặc Forecast | `DSS S6 Eligible = 0`, chỉ số cơ sở/kịch bản để trống |
| S6-08 | Kiểm tra tổng | Không cộng hai cấp forecast `company` và `total`/`region` khi dùng table theo hãng |