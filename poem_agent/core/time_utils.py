"""Time helpers. The database stores UTC as 'YYYY-MM-DD HH:MM:SS'."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

DB_FMT = "%Y-%m-%d %H:%M:%S"
_DIGITS = str.maketrans("၀၁၂၃၄၅၆၇၈၉", "0123456789")
_COUNT_WORDS = {"တစ်": 1, "နှစ်": 2, "သုံး": 3, "လေး": 4, "ငါး": 5,
                "ခြောက်": 6, "ခုနစ်": 7, "ရှစ်": 8, "ကိုး": 9, "ဆယ်": 10}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_db(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime(DB_FMT)


def from_db(value: str) -> datetime:
    return datetime.strptime(value[:19].replace("T", " "), DB_FMT).replace(tzinfo=timezone.utc)


def to_local(dt: datetime, offset_minutes: int) -> datetime:
    return dt.astimezone(timezone(timedelta(minutes=offset_minutes)))


def local_to_utc(year: int, month: int, day: int, hour: int, minute: int, offset_minutes: int) -> datetime:
    local = datetime(year, month, day, hour, minute, tzinfo=timezone(timedelta(minutes=offset_minutes)))
    return local.astimezone(timezone.utc)


def burmese_digits_to_ascii(text: str) -> str:
    return text.translate(_DIGITS)


def parse_hhmm_list(value: str) -> list[tuple[int, int]]:
    """'09:00,19:30' -> [(9, 0), (19, 30)] (invalid items are ignored)."""
    out: list[tuple[int, int]] = []
    for part in value.split(","):
        m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", part)
        if m and int(m.group(1)) < 24 and int(m.group(2)) < 60:
            out.append((int(m.group(1)), int(m.group(2))))
    return sorted(set(out))


def parse_count(text: str, default: int | None = None) -> int | None:
    """Find 'N ပုဒ်' (digits or Burmese number words) in text."""
    t = burmese_digits_to_ascii(text)
    m = re.search(r"(\d+)\s*ပုဒ်", t)
    if m:
        return int(m.group(1))
    for word, n in _COUNT_WORDS.items():
        if word + "ပုဒ်" in t or word + " ပုဒ်" in t:
            return n
    return default


def parse_clock_hint(text: str) -> tuple[int, int] | None:
    """Understand 'ည ၇ နာရီ' / 'မနက် 9 နာရီ' / '19:30'. Returns local (hour, minute)."""
    t = burmese_digits_to_ascii(text.replace("မနက်ဖြန်", " ").replace("နက်ဖြန်", " "))
    m = re.search(r"(\d{1,2}):(\d{2})", t)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d{1,2})\s*နာရီ", t)
    if not m:
        return None
    hour = int(m.group(1)) % 24
    if "ညနေ" in t or "ည" in t:
        hour = hour + 12 if hour < 12 else hour
    elif "နေ့လည်" in t:
        hour = hour + 12 if 1 <= hour <= 6 else hour
    return hour, 0


def resolve_when(params: Mapping[str, Any], now_utc: datetime, offset_minutes: int,
                 default_times: Sequence[tuple[int, int]]) -> datetime | None:
    """Turn {'day_offset', 'hour', 'minute'} (local time) into a UTC datetime."""
    if "iso" in params:
        try:
            return from_db(str(params["iso"]))
        except ValueError:
            return None
    day_offset = int(params.get("day_offset", 0))
    local_now = to_local(now_utc, offset_minutes)
    target_day = (local_now + timedelta(days=day_offset)).date()
    if params.get("hour") is not None:
        hour, minute = int(params["hour"]), int(params.get("minute", 0))
    elif default_times:
        hour, minute = default_times[0]
    else:
        hour, minute = 9, 0
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    return local_to_utc(target_day.year, target_day.month, target_day.day, hour, minute, offset_minutes)

