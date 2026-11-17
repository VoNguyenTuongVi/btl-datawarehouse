# Hướng dẫn kiểm thử DSS theo báo cáo

## Điều kiện chạy

Cần có DW, dự báo và mart trong PostgreSQL, rồi Refresh `powerbi/CarSalesDSS.pbip`. Nếu đã có dữ liệu, đóng Power BI và chạy `py -3 src/run_pipeline.py --only powerbi --no-open` để sinh thêm các measure kiểm thử từ mã nguồn.

N/A nghĩa là chưa chọn đúng bộ tham số của testcase; NO DATA nghĩa là thiếu dữ liệu hoặc chưa chọn một hãng. Chỉ PASS mới là đạt điều kiện.
