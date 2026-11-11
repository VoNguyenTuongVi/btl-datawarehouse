"""
Đọc cấu hình từ file .env ở thư mục gốc repo, dùng chung cho mọi script.

Quy tắc: giá trị trong .env LUÔN được ưu tiên hơn biến môi trường đã có sẵn
(ví dụ biến còn sót từ `$env:DATABASE_URL=...` hoặc `setx` trước đây).
Khi hai giá trị khác nhau, in cảnh báo (che mật khẩu) để biết biến cũ đang tồn tại.

Không có .env thì dùng biến môi trường như bình thường.
Không phụ thuộc thư viện ngoài (không cần python-dotenv).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"

_warned: set[str] = set()


def parse_env_file(path: Path = ENV_FILE) -> dict[str, str]:
    """Đọc các dòng KEY=VALUE; bỏ dòng trống, dòng # và dấu nháy bao quanh giá trị."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.lower().startswith("export "):
            key = key[7:].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def mask_url(url: str) -> str:
    """Che mật khẩu trong URL kết nối: postgres:***@localhost..."""
    try:
        parts = urlsplit(url)
        if parts.password is None:
            return url
        netloc = parts.netloc.replace(f":{parts.password}@", ":***@", 1)
        return urlunsplit(parts._replace(netloc=netloc))
    except ValueError:
        return "<URL không hợp lệ>"


def _describe_difference(key: str, old: str, new: str) -> str:
    if "://" in old and "://" in new:
        if mask_url(old) == mask_url(new):
            return f"{key}: biến môi trường có MẬT KHẨU KHÁC với .env"
        return f"{key}: biến môi trường là {mask_url(old)}"
    return f"{key}: biến môi trường có giá trị khác"


def load_env(path: Path = ENV_FILE, override: bool = True, quiet: bool = False) -> dict[str, str]:
    """
    Nạp .env vào os.environ. Mặc định ghi đè biến đã có (override=True).
    Trả về các cặp đã đọc từ .env.
    """
    values = parse_env_file(path)
    for key, value in values.items():
        old = os.environ.get(key)
        if old is not None and old != value:
            if not override:
                continue
            if not quiet and key not in _warned:
                _warned.add(key)
                print(
                    f"[!] {_describe_difference(key, old, value)}\n"
                    f"    -> Dùng giá trị trong .env. Xóa biến cũ để hết cảnh báo:\n"
                    f"       Remove-Item Env:{key}                                   (cửa sổ hiện tại)\n"
                    f"       [Environment]::SetEnvironmentVariable('{key}', $null, 'User')  (biến tạo bằng setx)",
                    file=sys.stderr,
                    flush=True,
                )
        os.environ[key] = value
    return values


def get_database_url(default: str | None = None) -> str | None:
    """Nạp .env rồi trả về DATABASE_URL (hoặc default nếu chưa đặt)."""
    load_env()
    return os.environ.get("DATABASE_URL", default)
