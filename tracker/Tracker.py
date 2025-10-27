# tracker/Tracker.py
import time
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5
from tick.Tick import Tick
from database.PostgreSQL import PostgreSQL
from config import MT5_CONFIG, POSTGRES_CONFIG, TRACKER_CONFIG
from utils import datetime_manager


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
        self.broker_offset: timedelta | None = None

        utc_now = datetime.now(timezone.utc)
        try:
            si = mt5.symbol_info_tick(self.symbol)
        except Exception as exc:  # pragma: no cover - MT5 runtime dependency
            print(f"[WARN] broker offset read failed during init symbol={self.symbol} err={exc}")
            si = None

        if si:
            self.broker_offset = datetime_manager.compute_broker_offset(si.time, utc_now)
        else:
            print(f"[WARN] broker offset unavailable during init for symbol={self.symbol}")

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
        now_utc = datetime.now(timezone.utc)

        try:
            server_tick = mt5.symbol_info_tick(self.symbol)
        except Exception as exc:  # pragma: no cover - MT5 runtime dependency
            print(f"[WARN] symbol_info_tick failed symbol={self.symbol} err={exc}")
            return []

        if not server_tick:
            print(f"[WARN] symbol_info_tick empty for symbol={self.symbol}; skipping fetch")
            return []

        new_offset = datetime_manager.compute_broker_offset(server_tick.time, now_utc)
        if self.broker_offset is None:
            self.broker_offset = new_offset
        else:
            drift = abs((new_offset - self.broker_offset).total_seconds())
            if drift >= 1:
                try:
                    refreshed_tick = mt5.symbol_info_tick(self.symbol)
                except Exception as exc:  # pragma: no cover - MT5 runtime dependency
                    print(f"[WARN] symbol_info_tick refresh failed symbol={self.symbol} err={exc}")
                    refreshed_tick = None
                if refreshed_tick:
                    server_tick = refreshed_tick
                    now_utc = datetime.now(timezone.utc)
                    new_offset = datetime_manager.compute_broker_offset(server_tick.time, now_utc)

                old_label = datetime_manager.format_offset(self.broker_offset)
                new_label = datetime_manager.format_offset(new_offset)
                self.broker_offset = new_offset
                print(
                    f"[INFO] broker offset updated symbol={self.symbol} "
                    f"old={old_label} new={new_label} drift={drift:.3f}s"
                )

        offset = self.broker_offset
        if offset is None:
            print(f"[WARN] broker offset missing after update symbol={self.symbol}")
            return []

        last_utc_ms = datetime_manager.to_utc_millis(server_tick.time_msc, offset)
        broker_last_utc = datetime.fromtimestamp(last_utc_ms / 1000.0, tz=timezone.utc)

        if self.last_msc is None:
            start_utc = broker_last_utc - timedelta(milliseconds=500)
        else:
            start_utc = datetime.fromtimestamp(self.last_msc / 1000.0, tz=timezone.utc)

        start_broker = datetime_manager.to_broker_time(start_utc, offset)
        raw = mt5.copy_ticks_from(
            self.symbol,
            start_broker.replace(tzinfo=None),
            100000,
            mt5.COPY_TICKS_ALL,
        )
        if raw is None or len(raw) == 0:
            return []

        ticks = []
        offset_label = datetime_manager.format_offset(offset)
        for t in raw:
            broker_ms = int(t['time_msc'])
            utc_ms = datetime_manager.to_utc_millis(broker_ms, offset)
            utc_dt = datetime.fromtimestamp(utc_ms / 1000.0, tz=timezone.utc)
            broker_dt = datetime.fromtimestamp(broker_ms / 1000.0, tz=timezone.utc)
            print(
                f"[TICK] [UTC] {utc_dt.isoformat()} "
                f"[BROKER{offset_label}] {broker_dt.isoformat()} "
                f"bid={t['bid']} ask={t['ask']} vol={t['volume']}"
            )
            ticks.append(
                Tick(
                    symbol=self.symbol,
                    bid=t['bid'],
                    ask=t['ask'],
                    last=t['last'],
                    volume=t['volume'],
                    flags=t['flags'],
                    time_msc=utc_ms,
                )
            )

        ticks.sort(key=lambda x: x.time_msc)
        if self.last_msc is not None:
            ticks = [tk for tk in ticks if tk.time_msc > self.last_msc]

        return ticks

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
