from datetime import datetime, timezone
from config import TICK_CONFIG


class Tick:
    """MT5'ten gelen tek bir tick verisini temsil eder."""

    def __init__(self, symbol: str, bid: float, ask: float,
                 last: float, volume: float, flags: int,
                 time_msc: int):
        self.symbol = symbol
        self.bid = float(bid)
        self.ask = float(ask)
        self.last = float(last)
        self.volume = int(volume)
        self.flags = int(flags)
        self.time_msc = int(time_msc)
        self.time_utc = datetime.fromtimestamp(time_msc / 1000.0, tz=timezone.utc)

        self.point = TICK_CONFIG["point"]
        self.spread_round = TICK_CONFIG["spread_round"]

        if self.ask and self.bid:
            self.spread_value = round(self.ask - self.bid, self.spread_round)
            self.spread_pts = int(round(self.spread_value / self.point))
        else:
            self.spread_value = None
            self.spread_pts = None

    def to_tuple(self):
        """Veritabanına yazmak için tuple döner."""
        return (
            self.symbol,
            self.time_utc,
            self.time_msc,
            self.bid,
            self.ask,
            self.last,
            self.volume,
            self.flags,
            self.spread_pts
        )

    def __repr__(self):
        return (f"<Tick {self.symbol} {self.time_utc.isoformat()} "
                f"bid={self.bid} ask={self.ask} "
                f"spread={self.spread_pts}pts ({self.spread_value})>")
