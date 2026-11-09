# Thiết kế KPI – Demand Forecasting cho Car Sales (DW & DSS)

Nov 9, 2026 · @Navy

## Bối cảnh & câu hỏi nghiệp vụ

Đề tài là dự báo nhu cầu xe theo tháng cho một chuỗi đại lý, dựa trên 23.906 giao dịch năm 2022–2023 trong DW. Bộ KPI chia 4 nhóm: chất lượng DW, nhu cầu lịch sử, độ chính xác dự báo và hỗ trợ quyết định (DSS). Dữ liệu chỉ có xe đã bán, nên 1 xe bán ra được dùng làm 1 đơn vị nhu cầu (proxy, không tính nhu cầu bị mất do hết hàng).

| Người ra quyết định | Quyết định | Câu hỏi KPI phải trả lời |
| --- | --- | --- |
| Ban giám đốc | Đặt mục tiêu sản lượng, ngân sách quý tới | Quý tới bán được bao nhiêu xe, tăng hay giảm so với cùng kỳ? |
| Mua hàng, cung ứng | Số lượng xe nhập theo hãng, kiểu thân, hộp số | Tháng tới cần bao nhiêu xe mỗi nhóm? |
| Quản lý vùng | Phân bổ xe về vùng, đại lý | Vùng nào nhu cầu tăng, cần bao nhiêu xe? |
| Marketing | Thời điểm, phân khúc khuyến mãi | Tháng nào thấp điểm, phân khúc nào tiềm năng? |~
| Nhóm phân tích | Chọn và tin dùng mô hình dự báo | Dự báo sai bao nhiêu, lệch về phía nào, có tốt hơn cách đơn giản không? |


## Danh mục KPI

Bộ KPI gồm 38 chỉ số trong 4 nhóm, tất cả tính được từ DW hiện có (nhóm 3 cần thêm bảng dự báo, đề xuất ở phần SQL). Cột cuối đánh dấu KPI nằm trên dashboard chính. Ký hiệu: A = sản lượng thực tế, F = sản lượng dự báo, t = tháng.

### Nhóm 1 – Chất lượng Data Warehouse

| Mã | KPI | Công thức | Hỗ trợ quyết định | Tần suất | Dashboard chính |
| --- | --- | --- | --- | --- | --- |
| Q1 | Tỷ lệ khớp số dòng | Số dòng fact / số dòng CSV × 100 | Có tin dùng số liệu DW để dự báo không | Mỗi lần chạy ETL | — |
| Q2 | Sai lệch doanh thu đối soát | ABS(SUM price fact − SUM price CSV) / SUM price CSV | Phát hiện lỗi nạp, lỗi ép kiểu | Mỗi lần chạy ETL | — |
| Q3 | Tỷ lệ khóa ngoại mồ côi | Số dòng fact không khớp dim / tổng dòng fact | Bảo đảm drill-down không mất dữ liệu | Mỗi lần chạy ETL | — |
| Q4 | Tỷ lệ đầy đủ dữ liệu | 1 − số ô null / tổng số ô (các cột khóa, price, date) | Biết cột nào dùng được làm biến dự báo | Mỗi lần chạy ETL | — |
| Q5 | Tỷ lệ trùng lặp | Số car_id trùng / tổng dòng | Tránh nhu cầu bị đếm đôi | Mỗi lần chạy ETL | — |
| Q6 | Độ tươi dữ liệu | Ngày chạy − MAX(full_date) đã nạp | Dự báo có dựa trên dữ liệu mới nhất không | Ngày | ✓ (dạng thẻ nhỏ) |
| Q7 | Độ phủ chuỗi thời gian | Số tháng có giao dịch / số tháng trong khoảng; tổng số tháng lịch sử | Đủ ≥ 24 tháng để mô hình bắt được mùa vụ chưa | Mỗi lần chạy ETL | — |


### Nhóm 2 – Nhu cầu lịch sử (Demand Analytics)

| Mã | KPI | Công thức | Hỗ trợ quyết định | Tần suất | Dashboard chính |
| --- | --- | --- | --- | --- | --- |
| D1 | Sản lượng bán (nhu cầu thực hiện) | SUM(quantity) = COUNT(car_id), theo ngày, tuần, tháng, quý, năm | Biến mục tiêu của mô hình dự báo; quy mô nhu cầu | Tuần, tháng | ✓ |
| D2 | Doanh thu | SUM(price) theo cùng các kỳ | Quy đổi nhu cầu ra giá trị, đặt mục tiêu doanh số | Tháng | ✓ |
| D3 | Giá bán bình quân (ASP) | D2 / D1 | Quy đổi dự báo sản lượng ra doanh thu | Tháng | — |
| D4 | Tăng trưởng sản lượng và doanh thu | MoM = (X_t − X_t−1) / X_t−1; QoQ theo quý; YoY dùng X_t−12; YTD = lũy kế từ đầu năm so với cùng kỳ; áp dụng cho X = D1 và X = D2 | Xu hướng tăng hay giảm, đầu vào cho thành phần trend của mô hình | Tháng, quý | ✓ (YoY sản lượng, YoY doanh thu) |
| D5 | Tỷ trọng nhu cầu theo kiểu thân xe, màu | D1 nhóm / D1 tổng | Nhập kiểu thân, màu nào | Tháng | — |
| D6 | Nhu cầu theo vùng | D1, D2, YoY theo dealer_region; D1 vùng / D1 tổng | Phân bổ xe về vùng | Tháng | ✓ |
| D7 | Chỉ số mùa vụ | A tháng m / trung bình tháng của năm (lấy trung bình 2 năm) | Tháng cao, thấp điểm để nhập trước và khuyến mãi | Tháng (cập nhật mỗi quý) | ✓ |
| D8 | Chỉ số ngày trong tuần | A ngày thứ k / trung bình ngày | Bố trí nhân sự bán hàng theo ngày | Tuần | — |
| D9 | Độ biến động nhu cầu (CV) | Độ lệch chuẩn A tháng / trung bình A tháng, theo nhóm | Nhóm nào khó dự báo, cần đệm an toàn lớn hơn | Quý | — |
| D10 | Mức tập trung nhu cầu | Tỷ trọng Top 10 mẫu; HHI = tổng bình phương thị phần hãng | Rủi ro phụ thuộc vào ít mẫu xe | Quý | — |
| D11 | Nhu cầu theo phân khúc thu nhập | D1, D2, ASP theo tứ phân vị annual_income; AVG(price / annual_income) | Nhắm phân khúc, chọn tầm giá xe | Quý | — |
| D12 | Sản lượng, doanh thu, tăng trưởng theo hãng (company) | D1, D2, thị phần, YoY theo company | Hãng nào đang tăng, nên nhập thêm | Tháng | ✓ |
| D13 | Sản lượng, doanh thu, tăng trưởng theo mẫu xe (model) | D1, D2, YoY theo model; Top 5 mẫu tăng mạnh nhất và giảm mạnh nhất theo chênh lệch D1 − D1 cùng kỳ | Mẫu nào nên tăng hoặc cắt nhập | Tháng | — |
| D14 | Cơ cấu và tăng trưởng theo hộp số (transmission) | D1, D2, YoY của Auto và Manual; tỷ trọng Auto và thay đổi tỷ trọng (điểm %) so với cùng kỳ | Tỷ lệ xe số tự động, số sàn khi đặt hàng | Tháng | — |
| D15 | Cơ cấu và tăng trưởng theo động cơ (engine) | D1, D2, YoY và tỷ trọng của từng loại động cơ (DOHC, OHC) | Cấu hình động cơ nào nên ưu tiên | Tháng | — |
| D16 | Hiệu suất đại lý (dealer_name) | D1, D2, YoY theo đại lý; xếp hạng; số xe / đại lý / tháng; % đại lý có YoY dương | Đại lý nào cần thêm xe, đại lý nào cần hỗ trợ | Tháng | — |
| D17 | Nhu cầu theo giới tính (gender) | D1, D2, ASP, tỷ trọng và YoY theo gender | Định hướng thông điệp marketing, cấu hình xe | Quý | — |


Sản lượng, doanh thu và tăng trưởng đều tính được trực tiếp: mỗi dòng fact là 1 xe có `price` và `date_id`, nên D1 = số dòng, D2 = tổng price. MoM và QoQ có đủ 23 tháng và 7 quý để so sánh; YoY chỉ có cho 12 tháng của 2023 (so với 2022), nên các ô YoY năm 2022 để trống. D12–D17 áp dụng cùng bộ ba sản lượng, doanh thu, tăng trưởng cho từng cột của dataset (Company, Model, Transmission, Engine, Dealer_Name, Gender), và cũng là các chuỗi có thể dự báo riêng ở cấp hãng.

### Nhóm 3 – Độ chính xác dự báo (Forecast Accuracy)

| Mã | KPI | Công thức | Hỗ trợ quyết định | Tần suất | Dashboard chính |
| --- | --- | --- | --- | --- | --- |
| F1 | Sản lượng dự báo kỳ tới | Đầu ra mô hình (Holt-Winters, SARIMA hoặc Prophet) theo tháng × hãng và tháng × vùng, kèm khoảng tin cậy 80% | Con số kế hoạch cho nhập hàng và phân bổ | Tháng | ✓ |
| F2 | MAPE | Trung bình ABS(A − F) / A × 100 | Báo cáo sai số dễ hiểu (méo khi A nhỏ) | Tháng | — |
| F3 | WAPE và Forecast Accuracy | WAPE = tổng ABS(A − F) / tổng A × 100; Accuracy = 100% − WAPE | Thước đo chính để tin dùng dự báo ở mọi cấp | Tháng | ✓ |
| F4 | MAE, RMSE | Trung bình ABS(A − F); căn bậc hai trung bình (A − F)² | So sánh, chọn mô hình khi backtest | Tháng | — |
| F5 | Forecast Bias | Tổng (F − A) / tổng A × 100; dương = dự báo dư | Biết dự báo đang thiên dư (tồn kho) hay thiếu (mất doanh số) | Tháng | ✓ |
| F6 | Tracking Signal | Tổng (A − F) / MAD; ngoài ±4 là cảnh báo | Khi nào phải huấn luyện lại mô hình | Tháng | — |
| F7 | Forecast Value Added (FVA) | WAPE seasonal naive − WAPE mô hình | Mô hình có tốt hơn cách "lấy cùng tháng năm trước" không | Quý | — |
| F8 | Độ phủ khoảng dự báo | % kỳ có A nằm trong [lower, upper] (mục tiêu ≈ 80%) | Khoảng tin cậy có đáng tin để đặt mức đệm không | Quý | — |


### Nhóm 4 – Hỗ trợ quyết định (DSS)

| Mã | KPI | Công thức | Hỗ trợ quyết định | Tần suất | Dashboard chính |
| --- | --- | --- | --- | --- | --- |
| S1 | Tăng trưởng nhu cầu dự báo | (F_t+1 − A cùng tháng năm trước) / A cùng tháng năm trước | Mở rộng hay thu hẹp kế hoạch nhập | Tháng | ✓ |
| S2 | Đề xuất phân bổ theo vùng, đại lý | F tổng × tỷ trọng D6 của 6 tháng gần nhất | Mỗi vùng, đại lý nhận bao nhiêu xe | Tháng | ✓ |
| S3 | Đề xuất số lượng nhập theo nhóm xe | F nhóm × (1 + k × CV nhóm), k do người dùng chọn | Đặt hàng nhập có đệm theo độ biến động | Tháng | ✓ |
| S4 | Doanh thu dự kiến | F × ASP (D3) của nhóm | Lập ngân sách, mục tiêu doanh thu | Tháng, quý | ✓ |
| S5 | Điểm ưu tiên nhu cầu | w1·S1 + w2·thị phần + w3·(1 − CV) + w4·Accuracy (đã chuẩn hóa 0–1) | Xếp hạng hãng, mẫu nên ưu tiên nhập; trọng số do Người 3 chốt | Quý | ✓ (bảng xếp hạng) |
| S6 | Kịch bản What-if | S3, S4 tính lại khi nhu cầu thay đổi ±x% hoặc đổi hệ số k | So sánh phương án trước khi quyết định | Theo yêu cầu | ✓ (trang DSS) |


Chỉ tiêu mục tiêu: dữ liệu không có số kế hoạch, nên đề xuất lấy mục tiêu = cùng kỳ năm trước + 5% cho D1, D2 và tô màu đạt/không đạt khi so 2023 với 2022. Với dự báo, đề xuất ngưỡng WAPE ≤ 20% và |Bias| ≤ 5% ở cấp tháng × hãng.

## Dashboard chính của DSS

Trang chính giữ 9 thẻ KPI và 4 visual, trả lời một câu: tháng tới cần bao nhiêu xe, ở đâu, và dự báo đáng tin đến mức nào. Các KPI còn lại nằm ở trang drill-down.

Hàng thẻ KPI (so với mục tiêu, tô xanh/đỏ): D1 sản lượng tháng, D4 YoY sản lượng, D4 YoY doanh thu, F1 dự báo tháng tới, S1 tăng trưởng dự báo, S4 doanh thu dự kiến, F3 Forecast Accuracy, F5 Bias, Q6 độ tươi dữ liệu.

| Vị trí | Visual | KPI | Câu hỏi trả lời |
| --- | --- | --- | --- |
| Giữa, lớn nhất | Line thực tế 2022–2023 nối tiếp dự báo 3–6 tháng, có dải khoảng tin cậy 80% | D1, F1, F8 | Nhu cầu đi về đâu, chắc chắn đến mức nào? |
| Trái dưới | Bar dự báo tháng tới theo hãng, kèm cột đề xuất nhập | F1, S3, D12 | Nhập bao nhiêu xe mỗi hãng? |
| Phải dưới | Bản đồ hoặc bar theo vùng: đề xuất phân bổ và tăng trưởng | S2, D6 | Mỗi vùng nhận bao nhiêu xe? |
| Đáy | Heatmap tháng × năm theo chỉ số mùa vụ | D7 | Khi nào cao điểm, thấp điểm? |


Slicer chung: Năm, Quý, Vùng, Hãng, Kiểu thân xe, Hộp số.

Các trang drill-down:

1. Phân tích nhu cầu: D2–D17 (sản lượng, doanh thu, tăng trưởng theo hãng, mẫu, hộp số, động cơ, đại lý, giới tính, phân khúc thu nhập; mùa vụ, biến động).
2. Độ chính xác dự báo: F2–F8, so sánh mô hình với seasonal naive, biểu đồ sai số theo tháng.
3. DSS và What-if: bảng xếp hạng S5, thanh trượt tỷ lệ thay đổi nhu cầu và hệ số đệm k cho S3, S4, S6.
4. Chất lượng DW: Q1–Q7, dành cho phần trình bày và kiểm thử.

## KPI nâng cao (khi có thêm dữ liệu)

Các KPI này biến dự báo nhu cầu thành quyết định tồn kho và lợi nhuận, nhưng dataset hiện tại không có đủ dữ liệu. Nên đưa vào báo cáo ở phần hướng phát triển.

| Mã | KPI | Công thức | Hỗ trợ quyết định | Tần suất | Dữ liệu cần thêm |
| --- | --- | --- | --- | --- | --- |
| A1 | Số ngày cung ứng (Days of Supply) | Tồn kho hiện tại / nhu cầu dự báo bình quân ngày | Đủ hàng bao lâu, khi nào phải nhập | Ngày, tuần | Tồn kho theo đại lý, mẫu xe |
| A2 | Vòng quay tồn kho | Giá vốn hàng bán / tồn kho bình quân | Vốn có bị đọng ở xe tồn không | Tháng | Tồn kho, giá vốn |
| A3 | Tồn kho an toàn | z × σ nhu cầu ngày × căn bậc hai lead time | Mức đệm theo mức phục vụ mong muốn | Tháng | Lead time nhập xe |
| A4 | Điểm đặt hàng lại (Reorder Point) | Nhu cầu bình quân ngày × lead time + tồn kho an toàn | Khi nào đặt đơn nhập | Ngày | Lead time, tồn kho |
| A5 | Tỷ lệ hết hàng, Fill rate | Số ngày/mẫu hết hàng / tổng; số xe giao được / số xe được đặt | Đo nhu cầu bị mất, hiệu chỉnh dự báo | Tuần | Đơn đặt hàng, tồn kho |
| A6 | Biên lợi nhuận gộp | (Doanh thu − giá vốn) / doanh thu | Ưu tiên nhập mẫu có lãi, không chỉ bán chạy | Tháng | Giá vốn |
| A7 | Chi phí tồn kho và chi phí thiếu hàng | Tồn kho × chi phí lưu kho/ngày; nhu cầu mất × lãi gộp/xe | Cân bằng nhập dư và nhập thiếu trong What-if | Tháng | Chi phí lưu kho, giá vốn |
| A8 | Độ co giãn nhu cầu theo giá, khuyến mãi | % thay đổi D1 / % thay đổi giá | Định giá, khuyến mãi dựa trên dự báo | Quý | Lịch sử giá niêm yết, khuyến mãi |
| A9 | Tỷ lệ chuyển đổi khách tiềm năng | Số xe bán / số lead hoặc lượt lái thử | Dự báo sớm từ nhu cầu ở đầu phễu | Tuần | Dữ liệu CRM, lead |
| A10 | ROI marketing | (Doanh thu tăng thêm − chi phí chiến dịch) / chi phí chiến dịch | Phân bổ ngân sách quảng cáo theo mùa vụ | Chiến dịch | Chi phí, lịch chiến dịch |
| A11 | Độ chính xác dự báo có biến ngoại sinh | WAPE mô hình có biến kinh tế vĩ mô, lãi suất, giá xăng | Cải thiện dự báo dài hạn | Quý | Dữ liệu vĩ mô theo tháng |


## Công thức SQL tham chiếu

DW trên PostgreSQL cần các view tổng hợp nhu cầu theo tháng, lịch tháng đầy đủ và chiều phân tích, cùng bảng fact lưu kết quả dự báo. Các đối tượng này được khai báo trong `src/schema.sql`; các truy vấn KPI được lưu trong `src/kpi_queries.sql` để đối chiếu với DAX trong Power BI. Truy vấn viết cho PostgreSQL ≥ 12.

View nhu cầu theo tháng (grain: tháng × hãng × vùng):

```sql
CREATE OR REPLACE VIEW v_monthly_demand AS
SELECT d.year * 100 + d.month AS month_id, d.year, d.month,
       make_date(d.year, d.month, 1) AS month_start,
       c.company, de.dealer_region,
       SUM(f.quantity) AS units, SUM(f.price) AS revenue
FROM fact_car_sales f
JOIN dim_date d    ON f.date_id   = d.date_id
JOIN dim_car c     ON f.car_key   = c.car_key
JOIN dim_dealer de ON f.dealer_id = de.dealer_id
GROUP BY d.year, d.month, c.company, de.dealer_region;
```
Bảng lưu dự báo (`forecast.py` ghi vào, Power BI đọc ra). Dự báo ở 3 cấp riêng (tổng, hãng, vùng) vì cấp hãng × vùng quá thưa để dự báo ổn định. Dùng NUMERIC thay vì REAL vì `ROUND(x, 2)` trong PostgreSQL không nhận kiểu double precision:

```sql
CREATE TABLE IF NOT EXISTS fact_demand_forecast (
    forecast_id    SERIAL PRIMARY KEY,
    month_id       INT  NOT NULL,           -- YYYYMM của kỳ được dự báo
    month_start    DATE NOT NULL,           -- ngày 1 của kỳ, để nối Calendar trong Power BI
    level          VARCHAR(20)  NOT NULL CHECK (level IN ('total', 'company', 'region')),
    member         VARCHAR(100) NOT NULL,   -- tên hãng / vùng, 'ALL' cho total
    model_name     VARCHAR(50)  NOT NULL,   -- 'holt_winters' | 'sarima' | 'seasonal_naive'
    forecast_units NUMERIC(12,2) NOT NULL,
    lower_80       NUMERIC(12,2),
    upper_80       NUMERIC(12,2),
    actual_units   NUMERIC(12,2),           -- sản lượng thực tế, chỉ có khi is_backtest = TRUE
    is_backtest    BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (month_id, level, member, model_name)
);
```
D4, D7, D9 – tăng trưởng, mùa vụ và biến động:

```sql
WITH m AS (SELECT month_id, year, SUM(units) AS units
           FROM v_monthly_demand GROUP BY month_id, year)
SELECT month_id, units,
       ROUND(100.0 * (units - LAG(units) OVER w)     / NULLIF(LAG(units) OVER w, 0), 2)     AS mom_pct,
       ROUND(100.0 * (units - LAG(units, 12) OVER w) / NULLIF(LAG(units, 12) OVER w, 0), 2) AS yoy_pct,
       ROUND(units / AVG(units) OVER (PARTITION BY year), 2)                               AS seasonality_index
FROM m
WINDOW w AS (ORDER BY month_id)
ORDER BY month_id;

-- D9: hệ số biến thiên nhu cầu tháng theo hãng
WITH m AS (SELECT company, month_id, SUM(units) AS u
           FROM v_monthly_demand GROUP BY company, month_id)
SELECT company, ROUND(AVG(u), 1) AS mean_units,
       ROUND(STDDEV_POP(u) / NULLIF(AVG(u), 0), 3) AS cv
FROM m GROUP BY company ORDER BY cv DESC;
```
D12–D17 – sản lượng, doanh thu và tăng trưởng theo một chiều bất kỳ (ví dụ hộp số; đổi `c.transmission` thành `c.company`, `c.model`, `c.engine`, `de.dealer_name` hoặc `cu.gender`):

```sql
WITH m AS (
  SELECT d.year, d.quarter, d.month, c.transmission AS grp,
         SUM(f.quantity) AS units, SUM(f.price) AS revenue
  FROM fact_car_sales f
  JOIN dim_date d      ON f.date_id     = d.date_id
  JOIN dim_car c       ON f.car_key     = c.car_key
  JOIN dim_dealer de   ON f.dealer_id   = de.dealer_id
  JOIN dim_customer cu ON f.customer_id = cu.customer_id
  GROUP BY d.year, d.quarter, d.month, c.transmission)
SELECT year, month, grp, units, revenue,
       ROUND(revenue::numeric / units, 0)                                              AS asp,
       ROUND(100.0 * units / SUM(units) OVER (PARTITION BY year, month), 2)            AS units_share_pct,
       ROUND(100.0 * (units - LAG(units) OVER g) / NULLIF(LAG(units) OVER g, 0), 2)     AS units_mom_pct,
       ROUND(100.0 * (units - LAG(units, 12) OVER g) / NULLIF(LAG(units, 12) OVER g, 0), 2)       AS units_yoy_pct,
       ROUND(100.0 * (revenue - LAG(revenue, 12) OVER g) / NULLIF(LAG(revenue, 12) OVER g, 0), 2) AS revenue_yoy_pct,
       SUM(revenue) OVER (PARTITION BY grp, year ORDER BY month)                       AS revenue_ytd
FROM m
WINDOW g AS (PARTITION BY grp ORDER BY year, month)
ORDER BY grp, year, month;
```
`LAG(…, 12)` chỉ đúng khi nhóm có giao dịch ở mọi tháng; với mẫu xe (D13) có tháng trống, nên nối với danh sách tháng đầy đủ từ `generate_series` trước, hoặc so sánh theo năm.

F3, F5, F7 – WAPE, Accuracy, Bias trên kỳ backtest (FVA = WAPE của seasonal_naive − WAPE của mô hình chính):

```sql
SELECT model_name,
       ROUND(100 * SUM(ABS(actual_units - forecast_units)) / SUM(actual_units), 2)       AS wape_pct,
       ROUND(100 - 100 * SUM(ABS(actual_units - forecast_units)) / SUM(actual_units), 2) AS accuracy_pct,
       ROUND(100 * SUM(forecast_units - actual_units) / SUM(actual_units), 2)            AS bias_pct,
       ROUND(100.0 * COUNT(*) FILTER (WHERE actual_units BETWEEN lower_80 AND upper_80)
             / COUNT(*), 1)                                                              AS coverage_pct  -- F8
FROM fact_demand_forecast
WHERE level = 'company' AND is_backtest
GROUP BY model_name
ORDER BY wape_pct;
```
S2 – đề xuất phân bổ theo vùng cho tháng dự báo kế tiếp:

```sql
WITH last6 AS (
  SELECT DISTINCT month_id FROM v_monthly_demand ORDER BY month_id DESC LIMIT 6),
share AS (
  SELECT dealer_region,
         SUM(units)::numeric / SUM(SUM(units)) OVER () AS share_6m
  FROM v_monthly_demand
  WHERE month_id IN (SELECT month_id FROM last6)
  GROUP BY dealer_region),
nxt AS (
  SELECT forecast_units FROM fact_demand_forecast
  WHERE level = 'total' AND NOT is_backtest AND model_name = 'sarima'
  ORDER BY month_id ASC LIMIT 1)
SELECT s.dealer_region, ROUND(s.share_6m * 100, 2) AS share_pct,
       ROUND(s.share_6m * n.forecast_units) AS allocated_units
FROM share s CROSS JOIN nxt n
ORDER BY allocated_units DESC;
```
Q7 – độ phủ chuỗi thời gian (số tháng thiếu trong khoảng):

```sql
SELECT MIN(full_date) AS first_date, MAX(full_date) AS last_date,
       COUNT(DISTINCT date_trunc('month', full_date)) AS months_with_sales,
       (SELECT COUNT(*) FROM generate_series(date_trunc('month', MIN(full_date)),
                                             date_trunc('month', MAX(full_date)),
                                             interval '1 month')) AS months_in_range
FROM dim_date;
```
Mô hình dự báo (gợi ý `src/forecast.py`): đọc `v_monthly_demand` qua SQLAlchemy (`postgresql+psycopg2://…`), giữ 6 tháng cuối 2023 làm backtest, chạy Holt-Winters (statsmodels) và seasonal naive, ghi cả hai vào `fact_demand_forecast`, rồi dự báo 6 tháng của 2024 với `is_backtest = FALSE`.

Đã triển khai trong `src/forecast.py`: chạy Holt-Winters, SARIMA mùa vụ và seasonal naive ở cấp tổng, hãng, vùng; backtest tháng 7–12/2023 và ghi dự báo 6 tháng tiếp theo. Cấu hình `DATABASE_URL` bằng URL SQLAlchemy của PostgreSQL trước khi chạy. Cài dependencies bằng `pip install -r requirements.txt`, tạo các bảng/view bằng `src/schema.sql`, sau đó chạy `python src/forecast.py`. Kết quả backtest và dự báo được upsert theo ngày chạy, kỳ, cấp, thành viên và mô hình.

## Ma trận KPI × Dimension (OLAP)

Ma trận quyết định thao tác OLAP cần hỗ trợ: roll-up/drill-down Năm → Quý → Tháng → Ngày, Vùng → Đại lý, Hãng → Mẫu; slice/dice theo mọi ô có ✓. KPI dự báo chỉ đi được tới cấp tháng và theo hãng hoặc vùng, đúng grain của `fact_demand_forecast`.

| KPI | Thời gian | Hãng → Mẫu | Thuộc tính xe | Vùng → Đại lý | Khách hàng |
| --- | --- | --- | --- | --- | --- |
| D1–D4 Sản lượng, doanh thu, ASP, tăng trưởng | ✓ | ✓ | ✓ | ✓ | ✓ |
| D5 Tỷ trọng kiểu thân, màu | ✓ | ✓ | ✓ (bắt buộc) | ✓ | ✓ |
| D6 Nhu cầu vùng | ✓ | ✓ | ✓ | ✓ (bắt buộc) | — |
| D7–D8 Mùa vụ, ngày trong tuần | ✓ (bắt buộc) | ✓ | — | ✓ | — |
| D9–D10 Biến động, tập trung | ✓ (tháng) | ✓ | — | ✓ | — |
| D11 Phân khúc thu nhập | ✓ | ✓ | ✓ | ✓ | ✓ (bắt buộc) |
| D12–D13 Theo hãng, mẫu | ✓ | ✓ (bắt buộc) | ✓ | ✓ | ✓ |
| D14–D15 Theo hộp số, động cơ | ✓ | ✓ | ✓ (bắt buộc) | ✓ | ✓ |
| D16 Hiệu suất đại lý | ✓ | ✓ | ✓ | ✓ (bắt buộc) | — |
| D17 Theo giới tính | ✓ | ✓ | ✓ | ✓ | ✓ (bắt buộc) |
| F1–F8 Dự báo, độ chính xác | ✓ (tháng) | Chỉ cấp hãng | — | Chỉ cấp vùng | — |
| S1–S6 Hỗ trợ quyết định | ✓ (tháng, quý) | Chỉ cấp hãng | — | Vùng; đại lý qua tỷ trọng | — |
| Q1–Q7 Chất lượng DW | Theo lần chạy ETL | — | — | — | — |


Hierarchy khai báo trong Power BI: `Date` (Year › Quarter › Month › Date), `Product` (company › model), `Geography` (dealer_region › dealer_name).

## DAX measures cho Power BI

Power BI cần 6 bảng (4 dim, `fact_car_sales`, `fact_demand_forecast`) cộng một bảng `Calendar` liên tục và 2 tham số What-if. Mọi measure để trong bảng rỗng `_Measures` để Người 3 tham chiếu lại khi viết DSS Measures.

1. Kết nối: Get Data › PostgreSQL database, Server `localhost:5432`, Database là tên DW; chọn chế độ Import (khoảng 24 nghìn dòng, nhẹ và dùng được đầy đủ time intelligence). Power BI Desktop đã kèm driver Npgsql. Nạp 4 dim, `fact_car_sales` và `fact_demand_forecast`; view `v_monthly_demand` chỉ dùng cho SQL và Python, không cần nạp.
2. Bảng ngày: `dim_date` chỉ có ngày có giao dịch và không có 2024, nên time intelligence sẽ sai và không vẽ được dự báo. Tạo `Calendar` đến hết 2024 và Mark as Date Table.
3. Quan hệ: mỗi dim 1-nhiều tới `fact_car_sales`; `Calendar[DateId]` → `fact_car_sales[date_id]`; `Calendar[Date]` → `fact_demand_forecast[month_start]`.
4. Cập nhật: mỗi lần `forecast.py` ghi dự báo mới vào PostgreSQL, bấm Refresh trong Power BI.

```dax
Calendar =
ADDCOLUMNS (
    CALENDAR ( DATE ( 2022, 1, 1 ), DATE ( 2024, 12, 31 ) ),
    "Year", YEAR ( [Date] ),
    "Quarter", "Q" & QUARTER ( [Date] ),
    "MonthNo", MONTH ( [Date] ),
    "Month", FORMAT ( [Date], "MMM" ),
    "YearMonth", YEAR ( [Date] ) * 100 + MONTH ( [Date] ),
    "DateId", YEAR ( [Date] ) * 10000 + MONTH ( [Date] ) * 100 + DAY ( [Date] )
)

Demand Change = GENERATESERIES ( -0.30, 0.30, 0.05 )   -- What-if: thay đổi nhu cầu
Safety Factor = GENERATESERIES ( 0, 2, 0.1 )          -- What-if: hệ số đệm k
```
Nhóm 2 – nhu cầu lịch sử:

```dax
Units Sold    = SUM ( fact_car_sales[quantity] )                                   -- D1
Revenue       = SUM ( fact_car_sales[price] )                                      -- D2
ASP           = DIVIDE ( [Revenue], [Units Sold] )                                 -- D3
Units PM      = CALCULATE ( [Units Sold], DATEADD ( Calendar[Date], -1, MONTH ) )
Units PY      = CALCULATE ( [Units Sold], SAMEPERIODLASTYEAR ( Calendar[Date] ) )
Units MoM %   = DIVIDE ( [Units Sold] - [Units PM], [Units PM] )                   -- D4
Units YoY %   = DIVIDE ( [Units Sold] - [Units PY], [Units PY] )                   -- D4
Revenue PM    = CALCULATE ( [Revenue], DATEADD ( Calendar[Date], -1, MONTH ) )
Revenue PY    = CALCULATE ( [Revenue], SAMEPERIODLASTYEAR ( Calendar[Date] ) )
Revenue MoM % = DIVIDE ( [Revenue] - [Revenue PM], [Revenue PM] )                  -- D4
Revenue YoY % = DIVIDE ( [Revenue] - [Revenue PY], [Revenue PY] )                  -- D4
Units PQ      = CALCULATE ( [Units Sold], DATEADD ( Calendar[Date], -1, QUARTER ) )
Units QoQ %   = DIVIDE ( [Units Sold] - [Units PQ], [Units PQ] )                   -- D4
Units YTD     = TOTALYTD ( [Units Sold], Calendar[Date] )
Revenue YTD   = TOTALYTD ( [Revenue], Calendar[Date] )
Revenue YTD YoY % =
    DIVIDE ( [Revenue YTD] - CALCULATE ( [Revenue YTD], SAMEPERIODLASTYEAR ( Calendar[Date] ) ),
             CALCULATE ( [Revenue YTD], SAMEPERIODLASTYEAR ( Calendar[Date] ) ) )   -- D4
Units YoY Delta = [Units Sold] - [Units PY]                                         -- D13: mẫu tăng, giảm mạnh nhất
Auto Share %  = DIVIDE ( CALCULATE ( [Units Sold], dim_car[transmission] = "Auto" ), [Units Sold] )  -- D14
Auto Share Change pp =
    [Auto Share %] - CALCULATE ( [Auto Share %], SAMEPERIODLASTYEAR ( Calendar[Date] ) )  -- D14
Dealer Rank   = RANKX ( ALLSELECTED ( dim_dealer[dealer_name] ), [Units Sold] )     -- D16
Dealers Growing % =
    DIVIDE ( COUNTROWS ( FILTER ( VALUES ( dim_dealer[dealer_name] ), [Units YoY %] > 0 ) ),
             COUNTROWS ( VALUES ( dim_dealer[dealer_name] ) ) )                    -- D16
Units Share % = DIVIDE ( [Units Sold], CALCULATE ( [Units Sold], ALLSELECTED ( dim_car ) ) )     -- D5
Region Share %= DIVIDE ( [Units Sold], CALCULATE ( [Units Sold], ALLSELECTED ( dim_dealer ) ) )  -- D6
Seasonality Index =
    DIVIDE ( [Units Sold],
             AVERAGEX ( ALLSELECTED ( Calendar[MonthNo], Calendar[Month] ), [Units Sold] ) )      -- D7
Demand CV =
    VAR t = ADDCOLUMNS ( VALUES ( Calendar[YearMonth] ), "u", [Units Sold] )
    RETURN DIVIDE ( STDEVX.P ( FILTER ( t, [u] > 0 ), [u] ), AVERAGEX ( FILTER ( t, [u] > 0 ), [u] ) ) -- D9
Top10 Model Share % =
    DIVIDE ( SUMX ( TOPN ( 10, ALLSELECTED ( dim_car[model] ), [Units Sold] ), [Units Sold] ),
             CALCULATE ( [Units Sold], ALLSELECTED ( dim_car[model] ) ) )                   -- D10
Price to Income =
    AVERAGEX ( fact_car_sales,
               DIVIDE ( fact_car_sales[price], RELATED ( dim_customer[annual_income] ) ) )      -- D11
```
Nhóm 3 – dự báo và độ chính xác (lọc `model_name` bằng slicer, `level` ở từng visual):

```dax
Forecast Units = SUM ( fact_demand_forecast[forecast_units] )                         -- F1
Forecast Lower = SUM ( fact_demand_forecast[lower_80] )
Forecast Upper = SUM ( fact_demand_forecast[upper_80] )

WAPE % =
    VAR bt = FILTER ( fact_demand_forecast, fact_demand_forecast[is_backtest] = TRUE () )
    RETURN DIVIDE ( SUMX ( bt, ABS ( [actual_units] - [forecast_units] ) ), SUMX ( bt, [actual_units] ) )  -- F3
Forecast Accuracy % = 1 - [WAPE %]                                                    -- F3
MAPE % =
    AVERAGEX ( FILTER ( fact_demand_forecast, [is_backtest] = TRUE () ),
               DIVIDE ( ABS ( [actual_units] - [forecast_units] ), [actual_units] ) )   -- F2
Bias % =
    VAR bt = FILTER ( fact_demand_forecast, [is_backtest] = TRUE () )
    RETURN DIVIDE ( SUMX ( bt, [forecast_units] - [actual_units] ), SUMX ( bt, [actual_units] ) )      -- F5
Tracking Signal =
    VAR bt = FILTER ( fact_demand_forecast, [is_backtest] = TRUE () )
    RETURN DIVIDE ( SUMX ( bt, [actual_units] - [forecast_units] ),
                    AVERAGEX ( bt, ABS ( [actual_units] - [forecast_units] ) ) )         -- F6
FVA = CALCULATE ( [WAPE %], fact_demand_forecast[model_name] = "seasonal_naive" ) - [WAPE %]  -- F7
Interval Coverage % =
    VAR bt = FILTER ( fact_demand_forecast, [is_backtest] = TRUE () )
    RETURN DIVIDE ( COUNTROWS ( FILTER ( bt, [actual_units] >= [lower_80] && [actual_units] <= [upper_80] ) ),
                    COUNTROWS ( bt ) )                                                   -- F8
```
Nhóm 4 – hỗ trợ quyết định:

```dax
Forecast Growth % = DIVIDE ( [Forecast Units] - [Units PY], [Units PY] )             -- S1
Region Share 6M % =
    VAR lastDay = CALCULATE ( MAX ( fact_car_sales[date_id] ), ALL ( fact_car_sales ) )
    VAR lastDate = DATE ( INT ( lastDay / 10000 ), MOD ( INT ( lastDay / 100 ), 100 ), MOD ( lastDay, 100 ) )
    VAR win = DATESINPERIOD ( Calendar[Date], lastDate, -6, MONTH )
    RETURN DIVIDE ( CALCULATE ( [Units Sold], win, REMOVEFILTERS ( Calendar ) ),
                    CALCULATE ( [Units Sold], win, REMOVEFILTERS ( Calendar ), ALL ( dim_dealer ) ) )
Allocated Units =
    CALCULATE ( [Forecast Units], fact_demand_forecast[level] = "total" ) * [Region Share 6M %]  -- S2
Recommended Order =
    [Forecast Units] * ( 1 + SELECTEDVALUE ( 'Demand Change'[Value], 0 ) )
        * ( 1 + SELECTEDVALUE ( 'Safety Factor'[Value], 1 ) * [Demand CV] )           -- S3, S6
Projected Revenue =
    [Forecast Units] * ( 1 + SELECTEDVALUE ( 'Demand Change'[Value], 0 ) ) * [ASP]    -- S4, S6
```
S5 (điểm ưu tiên) do Người 3 xây trên các measure Forecast Growth %, Units Share %, Demand CV và Forecast Accuracy %. Lưu ý ASP và Demand CV trong tháng dự báo phải lấy từ dữ liệu lịch sử (bọc thêm `CALCULATE(..., DATESINPERIOD(...))` như Region Share 6M %).

## Lưu ý dữ liệu, hạn chế & bàn giao

Dữ liệu đủ để làm dự báo cấp tháng theo hãng hoặc vùng, nhưng có 3 giới hạn ảnh hưởng trực tiếp tới KPI dự báo và 2 lỗi ETL cần sửa trước.

Giới hạn cho dự báo:

- Chỉ có 24 tháng (2 chu kỳ mùa vụ): Holt-Winters và SARIMA mùa vụ 12 tháng chạy được nhưng khoảng tin cậy rộng; F7 và F8 cần nêu rõ chỉ backtest trên 6 tháng.
- Dữ liệu thưa ở cấp chi tiết: khoảng 1.000 xe/tháng chia cho khoảng 30 hãng và 7 vùng, nên dự báo theo mẫu xe hoặc hãng × vùng sẽ rất nhiễu. Dự báo ở cấp tổng, hãng, vùng rồi phân bổ xuống bằng tỷ trọng (S2).
- Nhu cầu là proxy: chỉ có xe đã bán, không có nhu cầu bị mất do hết hàng, nên dự báo phản ánh doanh số chứ không phải nhu cầu thật. Đây là lý do nhóm KPI nâng cao cần dữ liệu tồn kho.
Lỗi ETL và dữ liệu:

- `etl.py` và `test_quality.py` vẫn dùng `create_engine('sqlite:///…')`, nên dữ liệu đang được nạp vào SQLite chứ không phải PostgreSQL. Cần đổi sang `postgresql+psycopg2://user:password@localhost:5432/car_sales_dw` (đặt mật khẩu trong biến môi trường) để Power BI đọc đúng DW.
- Chạy `schema.sql` trên PostgreSQL trước rồi mới chạy ETL, để các bảng có PRIMARY KEY và FOREIGN KEY. Vì ETL tự gán `customer_id`, `car_key`, `dealer_id`, sequence của cột SERIAL không tăng theo; sau khi nạp, chạy `SELECT setval(pg_get_serial_sequence('dim_customer','customer_id'), MAX(customer_id)) FROM dim_customer;` (tương tự cho 2 dim còn lại).
- `if_exists='append'` sẽ nhân đôi dữ liệu nếu chạy lại; thêm bước `TRUNCATE fact_car_sales, dim_customer, dim_car, dim_dealer, dim_date RESTART IDENTITY CASCADE;` ở đầu ETL.
- `dim_customer` gần như 1 khách = 1 giao dịch, và thu nhập 13.500 USD lặp lại nhiều lần (có thể là giá trị giữ chỗ); kiểm tra trước khi chốt D11.
