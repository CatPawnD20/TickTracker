# tracker/Tracker.py
import time
from zoneinfo import ZoneInfo
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5
from tick.Tick import Tick
from database.PostgreSQL import PostgreSQL
from config import MT5_CONFIG, POSTGRES_CONFIG, TRACKER_CONFIG
from utils import datetime_manager
from utils.tick_utils import normalize_ticks

IST = ZoneInfo("Europe/Istanbul")


class Tracker:
    """MetaTrader5 tick akışını dinler, PostgreSQL'e yazar."""

    def __init__(self, symbol: str | None = None):
        self.symbol = symbol or MT5_CONFIG.get("symbol", "XAUUSD")
        self.batch_size = TRACKER_CONFIG["batch_size"]
        self.poll_ms = TRACKER_CONFIG["poll_ms"]
        self.retention_days = TRACKER_CONFIG["retention_days"]
        self.precreate_days = TRACKER_CONFIG["precreate_days"]
        self.enable_partition_mgmt = TRACKER_CONFIG.get("enable_partition_mgmt", True)
        self.enable_pg_cron = TRACKER_CONFIG.get("enable_pg_cron", False)
        self.pg_cron_schedule = TRACKER_CONFIG.get("pg_cron_schedule", "15 02 * * *")
        self.buf = []
        self.last_msc: int | None = None
        self.db = None

    # ---- DB & MT5 setup ----
    def _init_db(self):
        """Veritabanını hazırlar, partisyon fonksiyonunu kurar ve çalıştırır."""
        self.db = PostgreSQL()
        self.db.connect()

        # Ana tablo ve default partisyonu garanti et
        self.db.ensure_tick_parent()

        # Partisyon yönetimi etkinse fonksiyonu kur ve çalıştır
        if self.enable_partition_mgmt:
            print(f"[PART] installing and managing partitions "
                  f"(retention={self.retention_days}d, precreate={self.precreate_days}d)")
            self.db.install_manage_partitions()
            self.db.call_manage_partitions(self.retention_days, self.precreate_days)
            if self.enable_pg_cron:
                job_name = self.db.ensure_pg_cron_job(
                    self.retention_days,
                    self.precreate_days,
                    self.pg_cron_schedule,
                )
                print(f"[PART] pg_cron job ensured name={job_name} schedule={self.pg_cron_schedule}")
        else:
            print("[PART] partition management disabled by config")

        print(f"[INIT] DB connected host={POSTGRES_CONFIG.get('host')} "
              f"db={POSTGRES_CONFIG.get('dbname')}")

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
        _, start_local_naive, offset_ms = datetime_manager.prepare_time_window(mt5, self.last_msc, self.symbol)
        raw = mt5.copy_ticks_from(self.symbol, start_local_naive, 100000, mt5.COPY_TICKS_ALL)
        if raw is None or len(raw) == 0:
            return []
        return normalize_ticks(raw, offset_ms, self.symbol, self.last_msc)

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
                ticks = self._fetch_ticks() or []
                if ticks:
                    ticks.sort(key=lambda x: x.time_msc)
                    if self.last_msc is not None:
                        ticks = [t for t in ticks if t.time_msc > self.last_msc]
                    if ticks:
                        self.last_msc = ticks[-1].time_msc
                        for t in ticks:
                            self.buf.append(t.to_tuple())

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
