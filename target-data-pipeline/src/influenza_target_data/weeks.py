"""ISO-week and influenza-season helpers."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import SEASON_END_WEEK, SEASON_START_WEEK

WEEK_PATTERN = re.compile(r"^(?P<year>\d{4})W(?P<week>\d{2})$")
STOCKHOLM = ZoneInfo("Europe/Stockholm")


def parse_week(value: str) -> tuple[int, int]:
    match = WEEK_PATTERN.fullmatch(value)
    if not match:
        raise ValueError(f"Invalid ISO week {value!r}; expected YYYYWww")
    year = int(match.group("year"))
    week = int(match.group("week"))
    date.fromisocalendar(year, week, 1)
    return year, week


def format_week(year: int, week: int) -> str:
    date.fromisocalendar(year, week, 1)
    return f"{year:04d}W{week:02d}"


def week_sunday(value: str) -> date:
    year, week = parse_week(value)
    return date.fromisocalendar(year, week, 7)


def previous_week(now: datetime | None = None) -> str:
    if now is None:
        now = datetime.now(timezone.utc)
    local_date = now.astimezone(STOCKHOLM).date() - timedelta(days=7)
    iso = local_date.isocalendar()
    return format_week(iso.year, iso.week)


def season_start_year(value: str) -> int | None:
    year, week = parse_week(value)
    if week >= SEASON_START_WEEK:
        return year
    if week <= SEASON_END_WEEK:
        return year - 1
    return None


def season_weeks_through(value: str) -> list[str]:
    """Return the configured season start through an in-season ISO week."""
    start_year = season_start_year(value)
    if start_year is None:
        return []
    start = date.fromisocalendar(start_year, SEASON_START_WEEK, 1)
    end = week_sunday(value)
    result: list[str] = []
    cursor = start
    while cursor <= end:
        iso = cursor.isocalendar()
        week_value = format_week(iso.year, iso.week)
        if season_start_year(week_value) != start_year:
            break
        result.append(week_value)
        cursor += timedelta(days=7)
    return result


def previous_iso_week(value: str) -> str:
    previous = week_sunday(value) - timedelta(days=7)
    iso = previous.isocalendar()
    return format_week(iso.year, iso.week)
