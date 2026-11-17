# Frontend 

Frontend gọi `GET /api/dashboard` khi mở trang, bấm **Nạp lại dữ liệu**, và mỗi 30 giây khi bật tự cập nhật, trang đang hiển thị. Mỗi yêu cầu truy vấn lại PostgreSQL; giao diện không đọc file JSON mẫu. Khi tải lại thất bại, trang báo lỗi và ghi rõ thời điểm của dữ liệu còn đang hiển thị.

## 1. Chuẩn bị DB và thư viện

Cần Python, PostgreSQL, Node.js và npm. Các lệnh dưới đây dùng PowerShell, bắt đầu tại thư mục gốc dự án (có `requirements.txt`).

```powershell
py -3 -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

Sửa `DATABASE_URL` trong `.env`, thay `YOUR_PASSWORD` bằng mật khẩu PostgreSQL thật:

```dotenv
DATABASE_URL=postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/car_sales_dw
```

Mật khẩu có `@`, `#`, `%`, `/` phải mã hóa lần lượt thành `%40`, `%23`, `%25`, `%2F`. `.env` nằm ở gốc dự án, không nằm trong thư mục `frontend`. Không đưa URL kết nối vào biến Vite hoặc mã JavaScript.

Nếu DB đã có DW và forecast của bản main, cập nhật mart một lần:

```powershell
py -3 src/run_pipeline.py --only marts --no-open
```

Nếu bắt đầu với DB rỗng, tạo database `car_sales_dw`, rồi chạy toàn bộ pipeline:

```powershell
py -3 src/run_pipeline.py --no-open
```

## 2. Chạy backend và frontend

**Terminal 1**, tại gốc dự án:

```powershell
py -3 src/api.py
```

Giữ Terminal này mở. Kiểm tra `http://127.0.0.1:8000/api/health`: thành công trả `{"status":"ok","database":"connected"}`. Health chỉ kiểm tra kết nối; `/api/dashboard` còn kiểm tra dữ liệu DW, forecast, mart.

**Terminal 2**, cũng bắt đầu từ gốc dự án:

```powershell
cd frontend
npm ci
npm run dev
```

Mở `http://127.0.0.1:5173` hoặc địa chỉ Vite in trong Terminal. Vite chuyển `/api` tới backend tại `127.0.0.1:8000`, nên không cần cấu hình CORS. Backend mặc định chỉ lắng nghe trên máy đang chạy.

## 3. Dữ liệu mới được lấy thế nào?

| Thay đổi | Việc cần làm |
| --- | --- |
| Dữ liệu trong DB đã cập nhật và commit | Bấm **Nạp lại dữ liệu** hoặc đợi lượt tự cập nhật |
| Vừa sửa dữ liệu bán hàng trong DW | Lịch sử DSS đọc lại ngay; chạy `forecast` và `marts` để tính lại dự báo và KPI tổng hợp |
| Đã chạy lại forecast | Chạy `marts`, rồi nạp lại web |
| Vừa đổi file CSV nguồn | Chạy ETL, kiểm tra, forecast và marts theo quy trình dự án; chỉ sửa CSV chưa thay dữ liệu DB |
| Muốn Power BI nhận thay đổi DB | Refresh trong Power BI; việc nạp lại web không refresh Power BI |

Để tính lại dự báo và mart từ DW đang có, chạy tại gốc dự án:

```powershell
py -3 src/run_pipeline.py --only forecast marts --no-open
```

API chỉ đọc DB: không tự ETL, train mô hình hay cập nhật mart. Lịch sử DSS lấy từ `fact_car_sales` + `dim_date` + `dim_car`; dự báo/backtest DSS lấy từ `fact_demand_forecast` cấp `company`; dashboard chính lấy từ `mart.*`. Tháng/hãng/model được lấy từ DB, năm tổng quan là năm mới nhất, mô hình mặc định lấy từ `mart.kpi_parameters.main_model` khi có forecast tương ứng.

Các truy vấn một lần tải dùng cùng giao dịch PostgreSQL `REPEATABLE READ`, `READ ONLY`; API trả `Cache-Control: no-store`. Thời điểm “Đọc DB lúc” là thời điểm đọc, không phải thời điểm huấn luyện dự báo. Tài khoản/mật khẩu, tên khách hàng và số điện thoại không được gửi ra frontend.

## 4. S5/S6 và testcase

- Chọn tháng, model và tập hãng; bộ lọc dùng chung cho S5/S6.
- S5: chỉnh bốn trọng số, xem điểm chuẩn hóa và hạng Dense. Bốn trọng số 0 trở về 25% mỗi tiêu chí. Hãng thiếu dữ liệu không được xếp hạng.
- S6: đổi nhu cầu và hệ số dự phòng; xem lượng nhập, doanh thu và chênh lệch. Hệ số dự phòng chỉ ảnh hưởng lượng nhập.
- Testcase: giữ đủ 9 case từ mục 5.6.2 báo cáo Nhóm 6, có nút áp dụng tham số và đối chiếu bốn lựa chọn Chevrolet. Các con số PDF được ghi rõ là tham chiếu, kết quả hiện tại tính từ DB.
- Có thể tải bảng xếp hạng/kế hoạch nhập xe thành CSV.

## 5. Kiểm tra, build và chạy bản build

Tại `frontend`:

```powershell
npm test
npm run build
```

Build tạo `frontend/dist`. Sau khi build, khởi động lại `py -3 src/api.py` từ gốc dự án rồi mở `http://127.0.0.1:8000`. Backend phục vụ cả giao diện build và API; không cần giữ Vite khi dùng cách này. Nếu dùng `npm run preview`, vẫn giữ backend chạy ở cổng 8000.

Tại gốc dự án, kiểm tra Python:

```powershell
py -3 -m pytest -q src/test_forecast.py tests
```

Test API dùng DB SQLite riêng: gọi HTTP, thay dữ liệu, commit rồi gọi lại để kiểm tra giá trị mới; không kết nối hoặc sửa DB của bạn. Cần kiểm tra thêm trên PostgreSQL thực tế của máy bạn. Test frontend dùng fixture cố định trong `frontend/test-fixtures/data.json` để đối chiếu PDF; fixture không được đưa vào bundle chạy web và không đổi khi dữ liệu DB đổi.

## 6. Lỗi thường gặp

| Lỗi | Cách xử lý |
| --- | --- |
| Không kết nối được API | Chạy `py -3 src/api.py` tại gốc; giữ Terminal mở |
| `DATABASE_UNAVAILABLE` / HTTP 503 | Kiểm tra PostgreSQL đang chạy, `.env` đúng; DW/mart có đủ bảng |
| `DATA_NOT_READY` / HTTP 409 | Chạy ETL/forecast/marts còn thiếu; kiểm tra dữ liệu trùng hoặc số không hợp lệ |
| Health OK nhưng dashboard lỗi | Health không kiểm tra bảng; chạy `/api/dashboard` và đọc hướng dẫn trong lỗi |
| Thiếu FastAPI/Uvicorn | Chạy `py -3 -m pip install -r requirements.txt` |
| Cổng 8000 bận | Đóng API cũ hoặc chạy `py -3 src/api.py --port 8001`, sửa đích proxy trong `frontend/vite.config.js` tương ứng |

Lệnh `py -3 src/export_frontend_data.py` vẫn có để xuất riêng `exports/dashboard.json` phục vụ đối soát. Web không sử dụng file này. Pipeline mặc định có 6 bước; `--only frontend` chỉ là lệnh xuất snapshot tùy chọn cũ, không khởi động web.
