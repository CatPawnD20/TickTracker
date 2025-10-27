"""Datetime helpers for broker/UTC conversions."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta


def _ensure_utc(dt: datetime) -> datetime:
    """Return a timezone-aware datetime in UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_broker_offset(server_epoch: int, utc_now: datetime) -> timedelta:
    """Return the broker offset relative to UTC.

    Parameters
    ----------
    server_epoch:
        Broker server time expressed as seconds since epoch.
    utc_now:
        Current UTC time.
    """

    utc_now = _ensure_utc(utc_now)
    server_dt = datetime.fromtimestamp(server_epoch, tz=timezone.utc)
    return server_dt - utc_now


def to_broker_time(utc_dt: datetime, offset: timedelta) -> datetime:
    """Convert a UTC datetime to broker-local time using the offset."""

    return _ensure_utc(utc_dt) + offset


def to_utc_millis(broker_millis: int, offset: timedelta) -> int:
    """Convert broker milliseconds to UTC milliseconds."""

    broker_dt = datetime.fromtimestamp(broker_millis / 1000.0, tz=timezone.utc)
    utc_dt = broker_dt - offset
    return int(round(utc_dt.timestamp() * 1000))


def format_offset(offset: timedelta) -> str:
    """Format offset as ±HH:MM:SS string."""

    total_seconds = int(offset.total_seconds())
    sign = "+" if total_seconds >= 0 else "-"
    total_seconds = abs(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{sign}{hours:02d}:{minutes:02d}:{seconds:02d}"
