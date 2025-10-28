from tick.Tick import Tick

def normalize_ticks(raw, offset_ms: int, symbol: str, last_msc: int | None):
    ticks = []
    for r in raw:
        t = Tick.from_mt5_row(r, symbol, offset_ms)
        if t is None:
            continue
        ticks.append(t)
    ticks.sort(key=lambda x: x.time_msc)
    if last_msc is not None:
        ticks = [t for t in ticks if t.time_msc > last_msc]
    return ticks
