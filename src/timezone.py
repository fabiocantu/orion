from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

APP_TZ = ZoneInfo("America/Sao_Paulo")


def now_local() -> datetime:
    return datetime.now(APP_TZ)


def today_local():
    return now_local().date()


def local_time_from_timestamp(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp, APP_TZ)
