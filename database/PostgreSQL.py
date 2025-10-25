# database/PostgreSQL.py
from typing import Iterable, Sequence, Optional, Any
import psycopg2
from psycopg2.extras import execute_values
from config import POSTGRES_CONFIG


class PostgreSQL:
    """PostgreSQL bağlantı yöneticisi ve tick verisi işlem sınıfı."""

    def __init__(self):
        # Config verilerini al
        self.cfg = {
            "host": POSTGRES_CONFIG["host"],
            "port": POSTGRES_CONFIG.get("port", 5432),
            "user": POSTGRES_CONFIG["user"],
            "password": POSTGRES_CONFIG["password"],
            "dbname": POSTGRES_CONFIG["dbname"],
            "sslmode": POSTGRES_CONFIG.get("sslmode", "prefer"),
            "connect_timeout": POSTGRES_CONFIG.get("connect_timeout", 10)
        }
        # Diğer parametreler
        self.schema = POSTGRES_CONFIG.get("schema", "public")
        self.table = POSTGRES_CONFIG.get("table_name", "tick_log")
        self.page_size = POSTGRES_CONFIG.get("page_size", 1000)

        self.conn = None
        self.cur = None

    # ---- lifecycle ----
    def connect(self):
        """Veritabanı bağlantısını kurar."""
        if self.conn:
            return
        self.conn = psycopg2.connect(**self.cfg)
        self.conn.autocommit = False
        self.cur = self.conn.cursor()

    def close(self):
        """Bağlantıyı güvenli şekilde kapatır."""
        try:
            if self.cur:
                self.cur.close()
        finally:
            if self.conn:
                self.conn.close()
        self.cur = None
        self.conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.close()

    # ---- primitives ----
    def execute(self, sql: str, params: Optional[Sequence[Any]] = None):
        """SQL sorgusu çalıştırır."""
        self.cur.execute(sql, params)

    def query_scalar(self, sql: str, params: Optional[Sequence[Any]] = None):
        """Tek değer döndüren sorgu."""
        self.cur.execute(sql, params)
        row = self.cur.fetchone()
        return row[0] if row else None

    def commit(self):
        """Commit işlemi."""
        self.conn.commit()

    def rollback(self):
        """Rollback işlemi."""
        self.conn.rollback()

    # ---- domain helpers ----
    def ensure_tick_parent(self):
        """tick_log ana tablosunu ve default partition'u oluşturur."""
        self.execute(f"""
        CREATE TABLE IF NOT EXISTS {self.schema}.{self.table} (
          id           BIGSERIAL,
          symbol       TEXT NOT NULL,
          time_utc     TIMESTAMPTZ NOT NULL,
          time_msc     BIGINT NOT NULL,
          bid          NUMERIC(12,3),
          ask          NUMERIC(12,3),
          last         NUMERIC(12,3),
          volume       BIGINT,
          flags        INT,
          spread_pts   INT
        ) PARTITION BY RANGE (time_utc);
        """)
        self.execute(f"""
        CREATE TABLE IF NOT EXISTS {self.schema}.{self.table}_default
        PARTITION OF {self.schema}.{self.table} DEFAULT;
        """)
        self.execute(f"""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_tick_default
          ON {self.schema}.{self.table}_default(symbol, time_msc);
        """)

    def call_manage_partitions(self, retention_days: int, precreate_days: int):
        """Partition yönetim fonksiyonunu çağırır; yoksa rollback ile sessiz geçer."""
        try:
            self.execute("SELECT public.manage_tick_log_partitions(%s,%s);",
                         (retention_days, precreate_days))
        except psycopg2.Error:
            self.rollback()
        else:
            self.commit()

    def insert_ticks(self, rows: Iterable[Sequence[Any]]):
        """
        Tick verilerini batch halinde ekler.
        rows: (symbol, time_utc, time_msc, bid, ask, last, volume, flags, spread_pts)
        """
        execute_values(self.cur, f"""
            INSERT INTO {self.schema}.{self.table}
              (symbol, time_utc, time_msc, bid, ask, last, volume, flags, spread_pts)
            VALUES %s
            ON CONFLICT (symbol, time_msc) DO NOTHING
        """, rows, page_size=self.page_size)
