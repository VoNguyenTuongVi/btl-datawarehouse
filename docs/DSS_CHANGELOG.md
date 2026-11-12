# DSS: NHẬT KÝ CHỈNH SỬA (S5 / S6)

**Phạm vi:** Các thành phần DSS

## 1. Các thay đổi chính

| Hạng mục | Trước | Sau |
|---|---|---|
| S5 Growth | Tăng trưởng của tháng bán thực tế cuối cùng | Tăng trưởng **dự báo một tháng** so với số xe thực bán **cùng hãng, cùng tháng năm trước** (`DSS Forecast Units Company`, `Priority Growth Raw`) |
| S5 Share | Thị phần sản lượng lịch sử | Giữ định nghĩa thị phần lịch sử, thêm kiểm tra thiếu dữ liệu và tập hãng được chọn |
| S5 Stability | `1 - COALESCE(CV,0)` khiến thiếu CV thành điểm tối đa | `BLANK()` khi thiếu CV; còn đủ dữ liệu thì `1 - CV` |
| S5 Accuracy | Cố định mô hình SARIMA, ép thiếu thành 0 | Tính `1-WAPE` trên **backtest** của đúng hãng và mô hình đang chọn; bỏ lọc tháng dự báo |
| S5 eligibility | Chưa có | `Priority Eligible`: hãng phải đủ 4 tiêu chí |
| S5 Min–Max | Mỗi tiêu chí xét toàn tập, thiếu dữ liệu có thể sai lệch | Cả 4 tiêu chí Min–Max trên **cùng tập hãng Eligible=1**; nếu min=max, cho 0,5 |
| S5 Weight | Cố định 0,25 cho mỗi tiêu chí | 4 Slicer rời `Param_Growth/Share/Stability/Accuracy` (0..100, bước 5), tự chuẩn hóa tổng về 1; tất cả 0 → 25% mỗi tiêu chí |
| S5 Score/Rank | Score cộng thẳng; Rank không loại hãng thiếu | Chỉ cho điểm hãng hợp lệ; Rank DESC/DENSE; thêm điểm hiển thị `Priority Score 100` |
| S6 Baseline/Scenario | Có KPI `Recommended Order`, `Projected Revenue` nhưng chưa có so sánh trực diện | Thêm measure S6 chuyên biệt theo hãng: Forecast, Eligibility, số xe nhập và doanh thu trước/sau, chênh lệch |
| Giao diện Power BI | Chỉ trang `Tổng quan` trống từ ZIP gốc | Thêm `DSS S5 – Priority Ranking` và `DSS S6 – What-if & Ordering`; vẫn giữ trang cũ |
| Đồng bộ mã nguồn | Chạy lại `build_pbip.py` sẽ thay mọi công thức sửa tay | S5/S6 định nghĩa tại `src/powerbi/dss_measures.py` và được `build_pbip.py` dùng khi sinh lại semantic model |

## 2. Mô hình tính

### S5 – Đánh giá đa tiêu chí theo hãng

Tập phương án: các hãng có dữ liệu dự báo tháng/mô hình đang chọn, có bán hàng cùng tháng năm trước, có thị phần, CV và backtest. Không dự báo trực tiếp từng `company | model`.

* **Growth** = `forecast_units(company, tháng t, model)` / `actual_units(company, tháng t−12)` − 1.
* **Share** = sản lượng lịch sử của hãng / sản lượng lịch sử các hãng đang được chọn.
* **Stability** = 1 − hệ số biến thiên (CV) của sản lượng tháng lịch sử.
* **Accuracy** = 1 − WAPE của hãng và mô hình trên các tháng **backtest**.
* **Min–Max** = `(x − min)/(max − min)` trên **cùng tập hãng Eligible=1**, xếp càng lớn càng tốt. Nếu tất cả bằng nhau, giá trị chuẩn hóa = 0,5.
* **Weights** `w_i = raw_i / sum(raw)`; nếu tổng = 0 thì `w_i = 0,25`.
* **Score** = `w_G*N_G + w_S*N_S + w_St*N_St + w_A*N_A` (0..1), `Score 100` = Score × 100; **Rank** giảm dần, Dense.

**Mặc định nếu chưa lọc:** tháng `202401`, mô hình `sarima`, bốn trọng số 25/25/25/25. Nếu lọc nhiều tháng/mô hình qua đúng hai Slicer, các measure mục tiêu trả về BLANK để tránh cộng lẫn kịch bản. Với tháng khác không có dữ liệu, điểm có thể trống.

### S6 – What-if ở cấp hãng

* Baseline nhu cầu = 0%, hệ số dự phòng `k=1`.
* `OrderBaseline = ROUNDUP(F * (1+CV), 0)`.
* `OrderScenario = ROUNDUP(F * (1+DemandChange) * (1+k*CV), 0)`.
* `RevenueBaseline = F * ASP lịch sử`.
* `RevenueScenario = F * (1+DemandChange) * ASP lịch sử`.
* `Delta = Scenario − Baseline`.

> **Giới hạn:** k ảnh hưởng số xe đề xuất nhập nhưng không tự động làm tăng doanh thu. Đây là mô hình hỗ trợ quyết định dựa trên **nhu cầu dự báo**, không tính chi phí nhập, tồn kho hay lợi nhuận. `Forecast Units` trong S6 sử dụng forecast cấp `company` với một `member`, một tháng và một mô hình; không cộng các cấp dự báo `total`/`region` với `company`.

## 3. Cấu trúc các file thuộc phạm vi DSS

**Đã sửa:**

- `powerbi/CarSalesDSS.SemanticModel/definition/tables/_Measures.tmdl` – sửa các measure S5 có sẵn và thêm measure S5/S6; các measure D/F và KPI chung giữ nguyên từng khối.
- `src/powerbi/build_pbip.py` – thay phân đoạn sinh S5 bằng import `DSS_MEASURES`, thêm sinh bốn bảng Slicer S5.
- `powerbi/CarSalesDSS.Report/definition/pages/pages.json` – nối thêm 2 trang DSS vào danh sách trang.

**Đã thêm:**

- `src/powerbi/dss_measures.py` – cho S5/S6 nếu chạy lại generator.
- `powerbi/dss_measures.dax` – bản DAX đọc/copy thủ công.
- `powerbi/CarSalesDSS.SemanticModel/definition/tables/Param_*.tmdl` – 4 bảng tham số độc lập.
- `powerbi/CarSalesDSS.Report/definition/pages/DSS_Priority/` – trang S5 và các visual.
- `powerbi/CarSalesDSS.Report/definition/pages/DSS_WhatIf/` – trang S6 và các visual.
- `tests/test_dss_static.py` – kiểm thử tĩnh không cần PostgreSQL.
- `docs/DSS_CHANGELOG.md` và `docs/DSS_HUONG_DAN_KIEM_THU.md`.

