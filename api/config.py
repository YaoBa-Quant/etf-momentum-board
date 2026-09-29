from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env.local")


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass
class Settings:
    tushare_token: str
    sqlite_path: str = "data/etf_dashboard.db"
    realtime_enabled: bool = False
    realtime_source: str = "tencent"
    realtime_refresh_window_seconds: int = 300
    realtime_stale_threshold_seconds: int = 300

    @property
    def database_path(self) -> Path:
        return BASE_DIR / self.sqlite_path

    @property
    def exports_dir(self) -> Path:
        return BASE_DIR / "exports"


settings = Settings(
    tushare_token=os.getenv("TUSHARE_TOKEN", ""),
    sqlite_path=os.getenv("SQLITE_PATH", "data/etf_dashboard.db"),
    realtime_enabled=_parse_bool(os.getenv("REALTIME_ENABLED"), default=False),
    realtime_source=os.getenv("REALTIME_SOURCE", "tencent").strip().lower() or "tencent",
    realtime_refresh_window_seconds=_parse_int(os.getenv("REALTIME_REFRESH_WINDOW_SECONDS"), default=300),
    realtime_stale_threshold_seconds=_parse_int(os.getenv("REALTIME_STALE_THRESHOLD_SECONDS"), default=300),
)
