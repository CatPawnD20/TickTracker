from datetime import datetime, timedelta, timezone

IST = datetime.now().astimezone().tzinfo  # yerel tz

def get_server_offset(mt5, symbol: str) -> tuple[datetime, int]:
    si = mt5.symbol_info_tick(symbol)
    if not si:
        return datetime.now(timezone.utc), 0
    broker_last_utc = datetime.fromtimestamp(si.time, tz=timezone.utc)
    now_utc = datetime.now(timezone.utc)
    srv_offset = broker_last_utc - now_utc
    offset_ms = int(srv_offset.total_seconds() * 1000)
    return srv_offset, offset_ms

def prepare_time_window(mt5, last_msc: int | None, symbol: str):
    now_utc = datetime.now(timezone.utc)
    start_utc = (
        now_utc - timedelta(milliseconds=500)
        if last_msc is None
        else datetime.fromtimestamp(last_msc / 1000.0, tz=timezone.utc)
    )
    srv_offset, offset_ms = get_server_offset(mt5, symbol)
    start_utc_adj = start_utc + srv_offset
    start_local_naive = start_utc_adj.astimezone(IST).replace(tzinfo=None)
    return now_utc, start_local_naive, offset_ms
