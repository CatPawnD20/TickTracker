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
        print(f"[DB] connecting to {self.cfg['host']}:{self.cfg['port']} db={self.cfg['dbname']}")
        self.conn = psycopg2.connect(**self.cfg)
        self.conn.autocommit = False
        self.cur = self.conn.cursor()
        print("[DB] connection established")

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
        print("[DB] connection closed")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc:
            self.conn.rollback()
            print("[DB] transaction rollback (exception)")
        else:
            self.conn.commit()
            print("[DB] transaction committed")
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
        print("[DB] commit")

    def rollback(self):
        """Rollback işlemi."""
        self.conn.rollback()
        print("[DB] rollback")

    # ---- domain helpers ----
    def ensure_tick_parent(self):
        """tick_log ana tablo ve default partition'u idempotent şekilde hazırlar."""
        parent_exists = self.query_scalar("""
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema=%s AND table_name=%s
            """, (self.schema, self.table))

        default_exists = self.query_scalar("""
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema=%s AND table_name=%s
            """, (self.schema, f"{self.table}_default"))

        created_any = False

        if not parent_exists:
            print(f"[DB] creating parent table {self.schema}.{self.table}")
            self.execute(f"""
            CREATE TABLE {self.schema}.{self.table} (
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
            created_any = True
        else:
            print(f"[DB] table {self.schema}.{self.table} already exists, skipping creation")

        # Parent-level global UNIQUE (partition key dahil)
        uq_exists = self.query_scalar("""
            SELECT 1
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname=%s AND t.relname=%s AND c.conname='uq_tick_global'
        """, (self.schema, self.table))

        if not uq_exists:
            print(f"[DB] creating global UNIQUE uq_tick_global on {self.schema}.{self.table}")
            self.execute(f"""
                ALTER TABLE {self.schema}.{self.table}
                ADD CONSTRAINT uq_tick_global UNIQUE (symbol, time_msc, time_utc);
            """)
            created_any = True

        if not default_exists:
            print(f"[DB] creating default partition {self.schema}.{self.table}_default")
            self.execute(f"""
            CREATE TABLE {self.schema}.{self.table}_default
            PARTITION OF {self.schema}.{self.table} DEFAULT;
            """)
            self.execute(f"""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_tick_default
              ON {self.schema}.{self.table}_default(symbol, time_msc, time_utc);
            """)
            created_any = True
        else:
            print(f"[DB] partition {self.schema}.{self.table}_default already exists, skipping creation")

        if created_any:
            self.commit()
            print("[DB] parent/partition created and committed")
        else:
            print("[DB] schema already ready; no changes")

    def call_manage_partitions(self, retention_days: int, precreate_days: int):
        """Partition yönetim fonksiyonunu çağırır; yoksa rollback ile sessiz geçer."""
        print(f"[DB] managing partitions (keep={retention_days}d, precreate={precreate_days}d)")
        try:
            self.execute("SELECT public.manage_tick_log_partitions(%s,%s);",
                         (retention_days, precreate_days))
        except psycopg2.Error:
            self.rollback()
            print("[DB] partition manager function missing — skipped")
        else:
            self.commit()

    def insert_ticks(self, rows: Iterable[Sequence[Any]]):
        """
        Tick verilerini batch halinde ekler.
        rows: (symbol, time_utc, time_msc, bid, ask, last, volume, flags, spread_pts)
        """
        count = len(rows)
        execute_values(self.cur, f"""
            INSERT INTO {self.schema}.{self.table}
              (symbol, time_utc, time_msc, bid, ask, last, volume, flags, spread_pts)
            VALUES %s
            ON CONFLICT (symbol, time_msc, time_utc) DO NOTHING
        """, rows, page_size=self.page_size)
        print(f"[DB] inserted {count} ticks")

    def install_manage_partitions(self):
        """manage_tick_log_partitions fonksiyonunu idempotent şekilde oluşturur."""
        sql = """
        CREATE OR REPLACE FUNCTION public.manage_tick_log_partitions(retention_days int, precreate_days int)
        RETURNS void LANGUAGE plpgsql AS $$
        DECLARE
          d date;
          part_name text;
        BEGIN
          -- Gelecek günleri oluştur
          FOR d IN current_date .. (current_date + precreate_days) LOOP
            part_name := format('tick_log_%s', to_char(d, 'YYYY_MM_DD'));
            EXECUTE format(
              'CREATE TABLE IF NOT EXISTS public.%I PARTITION OF public.tick_log
               FOR VALUES FROM (%L) TO (%L)',
              part_name, d, d + 1
            );
            EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON public.%I(symbol, time_utc)', part_name||'_sym_time', part_name);
            EXECUTE format('CREATE UNIQUE INDEX IF NOT EXISTS %I ON public.%I(symbol, time_msc, time_utc)', part_name||'_uq', part_name);
          END LOOP;

          -- Eski bölümleri düşür
          FOR d IN date '2000-01-01' .. (current_date - retention_days - 1) LOOP
            part_name := format('tick_log_%s', to_char(d, 'YYYY_MM_DD'));
            EXECUTE format('DROP TABLE IF EXISTS public.%I', part_name);
          END LOOP;
        END $$;
        """
        self.execute(sql)
        self.commit()
        print("[DB] partition manager function installed")
