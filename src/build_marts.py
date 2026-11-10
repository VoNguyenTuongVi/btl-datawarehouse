"""
Tạo lớp mart KPI (schema "mart") trong PostgreSQL cho Power BI.

    1. Ghi tham số (mô hình chính, mục tiêu, ngưỡng, trọng số S5) vào mart.kpi_parameters
    2. Chạy src/kpi_marts.sql: tạo lại toàn bộ bảng mart.* (một transaction)
    3. Thêm kiểm tra Q1–Q2 (đối chiếu với CSV) vào mart.dq_checks
    4. In số dòng từng bảng

Cách dùng:
    python src/build_marts.py
    python src/build_marts.py --main-model holt_winters --safety-factor 1.5
    python src/build_marts.py --weights 0.4 0.3 0.15 0.15   # growth share stability accuracy
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
SQL_FILE = ROOT / "src" / "kpi_marts.sql"
CSV_FILE = ROOT / "data" / "car_sales_cleaned.csv"


def load_env(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--main-model", default="sarima", choices=["sarima", "holt_winters", "seasonal_naive"])
    ap.add_argument("--target-growth", type=float, default=0.05)
    ap.add_argument("--wape-threshold", type=float, default=0.20)
    ap.add_argument("--bias-threshold", type=float, default=0.05)
    ap.add_argument("--safety-factor", type=float, default=1.0, help="hệ số đệm k cho S3")
    ap.add_argument("--weights", type=float, nargs=4, default=[0.25, 0.25, 0.25, 0.25],
                    metavar=("GROWTH", "SHARE", "STABILITY", "ACCURACY"), help="trọng số S5")
    args = ap.parse_args(argv)

    if abs(sum(args.weights) - 1) > 1e-6:
        sys.exit(f"[X] Tổng trọng số S5 phải bằng 1 (đang là {sum(args.weights):.2f}).")

    load_env()
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith(("postgresql://", "postgresql+psycopg2://")):
        sys.exit("[X] DATABASE_URL phải là PostgreSQL (xem .env.example).")

    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            n_fc = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_name = 'fact_demand_forecast'")).scalar()
            if not n_fc or not conn.execute(text("SELECT COUNT(*) FROM fact_demand_forecast")).scalar():
                sys.exit("[X] fact_demand_forecast đang trống. Chạy forecast.py trước.")

        # 1 + 2: tham số và SQL trong cùng một transaction
        raw = engine.raw_connection()
        try:
            cur = raw.cursor()
            sql = SQL_FILE.read_text(encoding="utf-8")
            # Tạo schema + bảng tham số trước để ghi tham số, rồi mới tính các bảng KPI
            cur.execute(sql.split("-- @@END_PARAMETERS")[0])
            w = args.weights
            cur.execute(
                """UPDATE mart.kpi_parameters
                   SET main_model = %s, target_growth = %s, wape_threshold = %s,
                       bias_threshold = %s, safety_factor = %s,
                       w_growth = %s, w_share = %s, w_stability = %s, w_accuracy = %s,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = 1""",
                (args.main_model, args.target_growth, args.wape_threshold, args.bias_threshold,
                 args.safety_factor, w[0], w[1], w[2], w[3]),
            )
            cur.execute(sql)
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            raw.close()
        print(f"-> Đã tạo lại schema mart (mô hình chính: {args.main_model})")

        # 3: Q1–Q2 cần file CSV gốc
        with engine.begin() as conn:
            if CSV_FILE.exists():
                csv = pd.read_csv(CSV_FILE, usecols=["price"])
                n_dw, rev_dw = conn.execute(text(
                    "SELECT COUNT(*), COALESCE(SUM(price), 0) FROM fact_car_sales")).one()
                n_csv, rev_csv = len(csv), float(csv["price"].sum())
                diff = abs(float(rev_dw) - rev_csv) / rev_csv if rev_csv else None
                rows = [
                    ("Q1", "Tỷ lệ khớp số dòng (DW / CSV)", n_dw / n_csv if n_csv else None, "= 100%",
                     n_dw == n_csv, f"{n_dw:,} / {n_csv:,} dòng"),
                    ("Q2", "Sai lệch doanh thu đối soát", diff, "= 0",
                     diff == 0, f"DW {float(rev_dw):,.0f} | CSV {rev_csv:,.0f}"),
                ]
            else:
                rows = [(c, n, None, "-", None, f"Không thấy {CSV_FILE.relative_to(ROOT)}")
                        for c, n in (("Q1", "Tỷ lệ khớp số dòng (DW / CSV)"),
                                     ("Q2", "Sai lệch doanh thu đối soát"))]
            for r in rows:
                conn.execute(text(
                    "INSERT INTO mart.dq_checks (check_code, check_name, metric_value, threshold, passed, detail) "
                    "VALUES (:c, :n, :v, :t, :p, :d)"),
                    dict(zip("cnvtpd", r)))

        # 4: tóm tắt
        with engine.connect() as conn:
            tables = [r[0] for r in conn.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'mart' AND table_type = 'BASE TABLE' ORDER BY 1"))]
            for t in tables:
                n = conn.execute(text(f'SELECT COUNT(*) FROM mart."{t}"')).scalar()
                print(f"   mart.{t:<26} {n:>6,} dòng")
            failed = conn.execute(text(
                "SELECT string_agg(check_code, ', ') FROM mart.dq_checks WHERE passed = FALSE")).scalar()
            if failed:
                print(f"[!] Kiểm tra chất lượng chưa đạt: {failed} (xem mart.dq_checks)")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
