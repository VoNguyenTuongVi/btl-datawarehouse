# Testcase 

## Chạy trong Power BI

1. Dùng bản dự án đã cập nhật mới nhất, giữ file `.env` đang dùng trên máy.
2. Nếu đã chạy đủ DW, dự báo và mart, chỉ cần đóng Power BI rồi chạy `py -3 src/run_pipeline.py --only powerbi --no-open`. Nếu mở bản ZIP mới giải nén thì mô hình có sẵn các measure testcase; chỉ cần Refresh.
3. Mở `powerbi/CarSalesDSS.pbip`, bấm **Refresh**.
4. Chọn trang **Testcase S5 - Báo cáo** hoặc **Testcase S6 - Báo cáo**.
5. Chọn tháng `202401`, model `sarima`, sau đó đổi tham số theo từng dòng dưới đây.

| Mã trong mục 5.6.2 | Thao tác | Điều kiện đạt |
| --- | --- | --- |
| TC-S5-01 | Xem một hãng, ví dụ Mercedes-B, ở 01/2024 và SARIMA | `Priority Growth Raw` bằng `TC S5 01 Expected Growth = (F - PY) / PY`; `TC S5 01 Status` = PASS |
| TC-S5-02 | Xem các hãng có `Priority Eligible = 1` | Bốn điểm chuẩn hóa đều có dữ liệu và nằm trong [0,1]; `TC S5 02 Status` = PASS |
| TC-S5-03 | Chọn trọng số 50/25/25/25 | Bốn Card có trọng số thực 40/20/20/20%; `TC S5 03 Status` = PASS; quan sát Score/Rank tính lại |
| TC-S5-04 | Chọn cả bốn trọng số bằng 0 | Bốn trọng số thực trở về 25%; `TC S5 04 Status` = PASS |
| TC-S6-01 | Demand Change = 0%, Safety Factor = 1 | Order/Revenue Scenario bằng Baseline; hai Delta bằng 0; `TC S6 01 Status` = PASS |
| TC-S6-02 | Demand Change = +20%, Safety Factor = 1 | Doanh thu Scenario bằng 1,2 lần Baseline, số xe nhập không giảm; `TC S6 02 Status` = PASS |
| TC-S6-03 | Demand Change = -20%, Safety Factor = 1 | Doanh thu Scenario bằng 0,8 lần Baseline, số xe nhập không tăng; `TC S6 03 Status` = PASS |
| TC-S6-04 | Demand Change = 0%, Safety Factor = 2 | Số xe nhập không giảm; doanh thu bằng Baseline; `TC S6 04 Status` = PASS |
| TC-S6-05 | Giữ d=0, k=2; đổi 01/2024-02/2024 và SARIMA-Holt-Winters | Forecast đúng hãng/tháng/model, cấp company, không backtest; bằng `TC S6 05 Expected Forecast`; `TC S6 05 Status` = PASS |

## Đọc trạng thái

| Trạng thái | Ý nghĩa |
| --- | --- |
| PASS | Đạt điều kiện của case trên dữ liệu và bộ lọc hiện tại |
| FAIL | Không đạt điều kiện; cần đối chiếu giá trị actual/expected |
| N/A | Chưa chọn đúng bộ trọng số hoặc d/k của case; đổi slicer theo hướng dẫn |
| NO DATA | Không có đúng một hãng, thiếu forecast/lịch sử, hoặc không đủ điều kiện S6 |

S6 cho phép sai số tối đa 1 USD khi đối chiếu doanh thu, phù hợp lưu ý về làm tròn ở trang in 65 của báo cáo. Growth, trọng số và forecast dùng dung sai 0,000001. Các dòng tổng nhiều hãng hiện NO DATA cho những case cần một hãng.

TC-S5-02 kiểm tra miền điểm ở hãng hợp lệ. Việc xác nhận cả bốn tiêu chí dùng cùng tập Candidates cần đối chiếu công thức trong `src/powerbi/dss_measures.py`, đúng giới hạn được nêu trong báo cáo.

## Chạy query và kiểm thử Python

Để chạy cả 9 case với thiết lập được áp sẵn, mở **DAX query view** trong Power BI, dán toàn bộ `powerbi/tests/DSS_TestCases.dax` và bấm **Run**. Kết quả thứ nhất là 9 case; kết quả thứ hai đối chiếu bốn lựa chọn Chevrolet của Bảng 11. Query trả SKIP nếu thiếu dữ liệu để kiểm tra.

Kiểm tra cấu trúc/tham chiếu và khả năng tái sinh mô hình bằng thư viện chuẩn Python:

```powershell
py -3 tests/test_dss_static.py
```

Kiểm tra thêm các hàm dự báo sau khi cài `requirements.txt`:

```powershell
py -3 -m pytest -q src/test_forecast.py tests
```

Kiểm thử Python không thực thi DAX; kết quả PASS/FAIL trong Power BI cần xác nhận sau Refresh.

Hướng dẫn DAX query view: https://learn.microsoft.com/en-us/power-bi/transform-model/dax-query-view
