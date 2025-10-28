from __future__ import annotations
from datetime import datetime, timezone
from config import TICK_CONFIG

class Tick:
    def __init__(self, symbol: str, bid: float, ask: float,
                 last: float, volume: float, flags: int, time_msc: int):
        self.symbol = symbol
        self.bid = float(bid)
        self.ask = float(ask)
        self.last = float(last)
        self.volume = int(volume)
        self.flags = int(flags)
        self.time_msc = int(time_msc)
        self.time_utc = datetime.fromtimestamp(self.time_msc / 1000.0, tz=timezone.utc)

        self.point = TICK_CONFIG["point"]
        self.spread_round = TICK_CONFIG["spread_round"]
        if self.ask and self.bid:
            self.spread_value = round(self.ask - self.bid, self.spread_round)
            self.spread_pts = int(round(self.spread_value / self.point))
        else:
            self.spread_value = None
            self.spread_pts = None

    @classmethod
    def from_mt5_row(cls, row, symbol: str, offset_ms: int) -> "Tick | None":
        # numpy.void veya dict fark etmeksizin [] ile eriş
        tm = int(row["time_msc"]) - offset_ms
        if tm < 0:
            return None
        return cls(
            symbol=symbol,
            bid=float(row["bid"]),
            ask=float(row["ask"]),
            last=float(row["last"]),
            volume=int(row["volume"]),
            flags=int(row["flags"]),
            time_msc=tm,
        )

    def to_tuple(self):
        """DB insert tuple'ı. time_utc TIMESTAMPTZ olmalı."""
        dt = self.time_utc
        if dt.tzinfo is None:
            from datetime import timezone
            dt = dt.replace(tzinfo=timezone.utc)

        return (
            self.symbol,  # TEXT
            dt,  # TIMESTAMPTZ
            self.time_msc,  # BIGINT
            self.bid,  # DOUBLE PRECISION
            self.ask,  # DOUBLE PRECISION
            self.last,  # DOUBLE PRECISION
            self.volume,  # BIGINT/INT
            self.flags,  # INT
            self.spread_pts  # INT (nullable değilse 0 koyabilirsiniz)
        )
