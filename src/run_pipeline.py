"""
Chạy trọn chuỗi DW -> dự báo -> Power BI bằng một lệnh.

    schema.sql -> etl.py -> test_quality.py -> forecast.py
               -> build_pbip.py (sinh mô hình Power BI)
               -> mở Power BI Desktop + tự Refresh (Windows)

Cách dùng (từ thư mục gốc repo):
    set DATABASE_URL=postgresql+psycopg2://postgres:<mật khẩu>@localhost:5432/car_sales_dw
    python src/run_pipeline.py                 # chạy hết
    python src/run_pipeline.py --only powerbi  # chỉ sinh lại mô hình + mở Power BI
    python src/run_pipeline.py --skip test --no-open
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PBI_DIR = ROOT / "powerbi"
PBI_NAME = "CarSalesDSS"

STEPS = ["schema", "etl", "test", "forecast", "powerbi"]


def load_env(path: Path = ROOT / ".env") -> None:
    """Nạp biến từ file .env (KEY=VALUE) vào os.environ; biến đã có sẵn được ưu tiên."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


load_env()


def banner(text: str) -> None:
    print("\n" + "=" * 70 + f"\n{text}\n" + "=" * 70, flush=True)


def run(cmd: list[str]) -> None:
    print("$ " + " ".join(cmd), flush=True)
    res = subprocess.run(cmd, cwd=ROOT)
    if res.returncode != 0:
        sys.exit(f"[X] Lệnh thất bại (mã {res.returncode}): {' '.join(cmd)}")


def require_db_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("[X] Chưa đặt DATABASE_URL. Hãy tạo file .env (xem .env.example), ví dụ:\n"
                 "    postgresql+psycopg2://postgres:<mật khẩu>@localhost:5432/car_sales_dw")
    return url


def step_schema() -> None:
    from sqlalchemy import create_engine

    sql_file = SRC / "schema.sql"
    engine = create_engine(require_db_url())
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        # Gửi cả file một lần, không truyền tham số nên ký tự % không bị hiểu nhầm
        cur.execute(sql_file.read_text(encoding="utf-8"))
        raw.commit()
    finally:
        raw.close()
    print(f"-> Đã chạy {sql_file.relative_to(ROOT)}")


def step_etl() -> None:
    run([sys.executable, str(SRC / "etl.py")])


def step_test() -> None:
    test_file = SRC / "test_quality.py"
    # test_quality.py là script (assert ở cấp module, không có hàm test_*),
    # nên chạy trực tiếp; assert thất bại sẽ trả mã thoát khác 0.
    run([sys.executable, str(test_file)])


def step_forecast() -> None:
    f = SRC / "forecast.py"
    if not f.exists():
        sys.exit(f"[X] Không thấy {f.relative_to(ROOT)}")
    run([sys.executable, str(f)])


def step_powerbi(args) -> None:
    cmd = [sys.executable, str(SRC / "powerbi" / "build_pbip.py"),
           "--out", str(PBI_DIR), "--name", PBI_NAME, "--main-model", args.main_model]
    run(cmd)
    if args.no_open:
        return
    if platform.system() != "Windows":
        print("[!] Power BI Desktop chỉ chạy trên Windows; bỏ qua bước mở và refresh.")
        return
    pbip = PBI_DIR / f"{PBI_NAME}.pbip"
    _close_powerbi_if_open(pbip)
    print(f"-> Mở {pbip}")
    launched_at = time.time()
    os.startfile(pbip)  # type: ignore[attr-defined]
    if args.no_refresh:
        print("[i] Bấm Refresh trong Power BI Desktop để nạp dữ liệu.")
        return
    ps1 = SRC / "powerbi" / "refresh_powerbi.ps1"
    run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1),
         "-LaunchedAfter", str(int(launched_at)), "-TimeoutSec", str(args.refresh_timeout)])


def _close_powerbi_if_open(pbip: Path) -> None:
    """Power BI Desktop không tự nhận file đổi từ bên ngoài, nên phải mở lại."""
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq PBIDesktop.exe"],
                         capture_output=True, text=True).stdout
    if "PBIDesktop.exe" in out:
        ans = input("[?] Power BI Desktop đang mở. Đóng để nạp mô hình mới? (y/N) ").strip().lower()
        if ans == "y":
            subprocess.run(["taskkill", "/IM", "PBIDesktop.exe", "/F"], capture_output=True)
            time.sleep(3)
        else:
            sys.exit("[X] Hãy đóng Power BI Desktop rồi chạy lại.")


def _has_module(name: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(name) is not None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="+", choices=STEPS, help="chỉ chạy các bước này")
    ap.add_argument("--skip", nargs="+", choices=STEPS, default=[], help="bỏ qua các bước này")
    ap.add_argument("--main-model", default="sarima", choices=["sarima", "holt_winters", "seasonal_naive"])
    ap.add_argument("--no-open", action="store_true", help="không mở Power BI Desktop")
    ap.add_argument("--no-refresh", action="store_true", help="mở Power BI nhưng không tự refresh")
    ap.add_argument("--refresh-timeout", type=int, default=180)
    args = ap.parse_args()

    steps = [s for s in (args.only or STEPS) if s not in args.skip]
    actions = {
        "schema": step_schema, "etl": step_etl, "test": step_test,
        "forecast": step_forecast, "powerbi": lambda: step_powerbi(args),
    }
    t0 = time.time()
    for i, s in enumerate(steps, 1):
        banner(f"[{i}/{len(steps)}] {s}")
        actions[s]()
    banner(f"Hoàn tất {len(steps)} bước trong {time.time() - t0:.0f} giây")


if __name__ == "__main__":
    main()
