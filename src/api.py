"""API đọc PostgreSQL cho frontend. Chạy từ gốc dự án: py -3 src/api.py."""
from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from env_config import get_database_url
from export_frontend_data import json_default, read_dashboard

logger = logging.getLogger("car_sales_api")


def database_engine():
    url = get_database_url()
    if not url:
        raise ValueError("Thiếu DATABASE_URL trong .env. Xem .env.example.")
    if make_url(url).get_backend_name() != "postgresql":
        raise ValueError("DATABASE_URL phải là kết nối PostgreSQL.")
    return create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=2,
                         pool_timeout=10, connect_args={"connect_timeout": 5})


def create_app(engine=None, *, dist_dir=None):
    """Engine được tiêm vào khi test; runtime luôn lấy PostgreSQL từ .env."""
    @asynccontextmanager
    async def lifespan(app):
        app.state.engine = engine if engine is not None else database_engine()
        try:
            yield
        finally:
            if engine is None:
                app.state.engine.dispose()

    app = FastAPI(title="Car Sales DSS API", lifespan=lifespan)

    @app.middleware("http")
    async def no_api_cache(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health")
    def health():
        try:
            with app.state.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return JSONResponse({"code": "DATABASE_UNAVAILABLE", "message": "Không kết nối được PostgreSQL. Kiểm tra dịch vụ và .env."}, status_code=503)
        return {"status": "ok", "database": "connected"}

    @app.get("/api/dashboard")
    def dashboard():
        try:
            payload = read_dashboard(app.state.engine)
            # Chuẩn hóa Decimal/date, từ chối NaN thay vì xuất JSON sai chuẩn.
            return JSONResponse(json.loads(json.dumps(payload, default=json_default, allow_nan=False)))
        except SQLAlchemyError as error:
            # Chỉ ghi loại lỗi; không đưa URL, SQL, mật khẩu hay tham số ra trình duyệt/log.
            logger.warning("Không đọc được dashboard (%s)", type(error).__name__)
            return JSONResponse({"code": "DATABASE_UNAVAILABLE", "message": "Không đọc được PostgreSQL. Kiểm tra .env, dịch vụ DB và các bảng DW/mart."}, status_code=503)
        except (ValueError, TypeError, KeyError) as error:
            logger.warning("Dữ liệu dashboard chưa hợp lệ (%s)", type(error).__name__)
            return JSONResponse({"code": "DATA_NOT_READY", "message": "DW, forecast hoặc mart chưa đủ dữ liệu hợp lệ. Chạy các bước ETL, forecast, marts phù hợp rồi thử lại."}, status_code=409)

    dist = Path(dist_dir) if dist_dir is not None else ROOT / "frontend/dist"
    if (dist / "index.html").is_file():
        # API đăng ký trước static mount; không phục vụ thư mục gốc chứa .env.
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    else:
        @app.get("/")
        def index():
            return {"message": "API đang chạy. Chạy npm run dev trong frontend, hoặc npm run build rồi khởi động lại API.", "health": "/api/health"}
    return app


app = create_app()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=args.port)
