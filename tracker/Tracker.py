# tracker/Tracker.py
import time
import MetaTrader5 as mt5
from tick.Tick import Tick
from database.PostgreSQL import PostgreSQL
from config import MT5_CONFIG, POSTGRES_CONFIG, TRACKER_CONFIG


class Tracker:
    """MetaTrader5 tick akışını dinler, PostgreSQL'e yazar."""

    def __init__(self, symbol: str | None = None):
        self.symbol = symbol or MT5_CONFIG.get("symbol", "XAUUSD")
        self.batch_size = TRACKER_CONFIG["batch_size"]
        self.poll_ms = TRACKER_CONFIG["poll_ms"]
        self.retention_days = TRACKER_CONFIG["retention_days"]
        self.precreate_days = TRACKER_CONFIG["precreate_days"]
        self.enable_partition_mgmt = TRACKER_CONFIG.get("enable_partition_mgmt", True)
        self.buf = []
        self.last_msc: int | None = None
        self.db = None

    # ---- DB & MT5 setup ----
    def _init_db(self):
        self.db = PostgreSQL()
        self.db.connect()
        self.db.ensure_tick_parent()
        if self.enable_partition_mgmt:
            self.db.install_manage_partitions()
            self.db.call_manage_partitions(self.retention_days, self.precreate_days)
        print(f"[INIT] DB connected host={POSTGRES_CONFIG.get('host')} db={POSTGRES_CONFIG.get('dbname')}")

    def _init_mt5(self):
        ok = mt5.initialize(
            path=MT5_CONFIG.get("path"),
            login=MT5_CONFIG.get("login", 0),
            password=MT5_CONFIG.get("password", ""),
            server=MT5_CONFIG.get("server", "")
        )
        if not ok:
            code, msg = mt5.last_error()
            raise RuntimeError(f"MT5 init failed ({code}): {msg}")

        si = mt5.symbol_info(self.symbol)
        if not si or not si.visible:
            if not mt5.symbol_select(self.symbol, True):
                raise RuntimeError(f"symbol_select failed: {self.symbol}")

        print(f"[INIT] MT5 ready symbol={self.symbol} path={MT5_CONFIG.get('path')!r}")

    # ---- Tick collection ----
    def _fetch_ticks(self):
        if self.last_msc is None:
            start_ms = int((time.time() - 3) * 1000)
            return mt5.copy_ticks_from(self.symbol, start_ms / 1000.0, 100000, mt5.COPY_TICKS_ALL)
        return mt5.copy_ticks_from(self.symbol, self.last_msc / 1000.0, 100000, mt5.COPY_TICKS_ALL)

    # ---- Database write ----
    def _flush(self):
        n = len(self.buf)
        if n == 0:
            return
        self.db.insert_ticks(self.buf)
        self.db.commit()
        self.buf.clear()
        print(f"[FLUSH] wrote {n} ticks")

    # ---- Main loop ----
    def run(self):
        """Sürekli tick akışı başlatır."""
        print(f"[START] symbol={self.symbol} batch_size={self.batch_size} poll_ms={self.poll_ms} "
              f"retention={self.retention_days} precreate={self.precreate_days}")
        self._init_db()
        self._init_mt5()
        print("[RUN] tracking live ticks...")

        try:
            while True:
                ticks = self._fetch_ticks()
                if ticks is not None and ticks.size > 0:
                    ticks = sorted(ticks, key=lambda x: x.time_msc)
                    if self.last_msc is not None:
                        ticks = [t for t in ticks if t.time_msc > self.last_msc]
                    if len(ticks) > 0:
                        self.last_msc = ticks[-1].time_msc
                        for t in ticks:
                            tk = Tick(
                                self.symbol,
                                t.bid, t.ask, t.last,
                                t.volume_real or t.volume,
                                t.flags, t.time_msc
                            )
                            self.buf.append(tk.to_tuple())

                if len(self.buf) >= self.batch_size:
                    self._flush()

                time.sleep(self.poll_ms / 1000.0)

        except KeyboardInterrupt:
            print("[EXIT] stopping by user")
        finally:
            self._flush()
            if self.db:
                self.db.close()
            mt5.shutdown()
            print("[EXIT] shutdown complete")
