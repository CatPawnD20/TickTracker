# database/PostgreSQL.py
from typing import Iterable, Sequence, Optional, Any
import psycopg2
from psycopg2.extras import execute_values
from config import POSTGRES_CONFIG


class PostgreSQL:
    """PostgreSQL bağlantı yöneticisi ve tick verisi işlem sınıfı."""

    def __init__(self):
        # Config
        self.cfg = {
            "host": POSTGRES_CONFIG["host"],
            "port": POSTGRES_CONFIG.get("port", 5432),
            "user": POSTGRES_CONFIG["user"],
            "password": POSTGRES_CONFIG["password"],
            "dbname": POSTGRES_CONFIG["dbname"],
            "sslmode": POSTGRES_CONFIG.get("sslmode", "prefer"),
            "connect_timeout": POSTGRES_CONFIG.get("connect_timeout", 10),
        }
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
        self.conn.commit()
        print("[DB] commit")

    def rollback(self):
        self.conn.rollback()
        print("[DB] rollback")

    # ---- domain helpers ----
    def ensure_pg_cron_job(self, retention_days: int, precreate_days: int, cron_schedule: str) -> str:
        """pg_cron eklentisini kurar ve partisyon yönetimi job'unu idempotent şekilde tanımlar."""
        if not self.cur:
            raise RuntimeError("cursor not initialized; call connect() first")

        job_name = f"{self.schema}.{self.table}_manage_partitions"
        command = f"SELECT public.manage_tick_log_partitions({int(retention_days)},{int(precreate_days)});"

        print(f"[DB] ensuring pg_cron job name={job_name} schedule={cron_schedule}")

        try:
            self.execute("CREATE EXTENSION IF NOT EXISTS pg_cron;")

            self.execute("SELECT jobid FROM cron.job WHERE jobname=%s;", (job_name,))
            row = self.cur.fetchone()
            job_id = row[0] if row else None

            if job_id is not None:
                print(f"[DB] pg_cron job exists (id={job_id}), updating schedule/command")
                self.execute(
                    "SELECT cron.alter_job(%s, schedule => %s, command => %s);",
                    (job_id, cron_schedule, command),
                )
            else:
                print("[DB] pg_cron job missing, creating new schedule")
                try:
                    self.execute(
                        "SELECT cron.schedule_in_database(%s, %s, %s, %s);",
                        (job_name, cron_schedule, command, self.cfg["dbname"]),
                    )
                except psycopg2.Error as e:
                    if getattr(e, "pgcode", None) == "42883":
                        print("[DB] cron.schedule_in_database unavailable, falling back to cron.schedule")
                        self.execute(
                            "SELECT cron.schedule(%s, %s, %s);",
                            (job_name, cron_schedule, command),
                        )
                    else:
                        raise

            self.commit()
        except psycopg2.Error:
            self.rollback()
            raise

        return job_name

    def ensure_tick_parent(self):
        """tick_log ana tablo ve default partition'u idempotent şekilde hazırlar."""
        parent_exists = self.query_scalar(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema=%s AND table_name=%s
            """,
            (self.schema, self.table),
        )

        default_exists = self.query_scalar(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema=%s AND table_name=%s
            """,
            (self.schema, f"{self.table}_default"),
        )

        created_any = False

        if not parent_exists:
            print(f"[DB] creating parent table {self.schema}.{self.table}")
            # time_utc = timestamptz ve RANGE(time_utc)
            self.execute(
                f"""
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
                """
            )
            created_any = True
        else:
            print(f"[DB] table {self.schema}.{self.table} already exists, skipping creation")

        # Parent-level UNIQUE (partition key dahil)
        uq_exists = self.query_scalar(
            """
            SELECT 1
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname=%s AND t.relname=%s AND c.conname='uq_tick_global'
            """,
            (self.schema, self.table),
        )

        if not uq_exists:
            print(f"[DB] creating global UNIQUE uq_tick_global on {self.schema}.{self.table}")
            self.execute(
                f"""
                ALTER TABLE {self.schema}.{self.table}
                ADD CONSTRAINT uq_tick_global UNIQUE (symbol, time_msc, time_utc);
                """
            )
            created_any = True

        if not default_exists:
            print(f"[DB] creating default partition {self.schema}.{self.table}_default")
            self.execute(
                f"""
                CREATE TABLE {self.schema}.{self.table}_default
                PARTITION OF {self.schema}.{self.table} DEFAULT;
                """
            )
            self.execute(
                f"""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_tick_default
                  ON {self.schema}.{self.table}_default(symbol, time_msc, time_utc);
                """
            )
            created_any = True
        else:
            print(f"[DB] partition {self.schema}.{self.table}_default already exists, skipping creation")

        if created_any:
            self.commit()
            print("[DB] parent/partition created and committed")
        else:
            print("[DB] schema already ready; no changes")

    def call_manage_partitions(self, retention_days: int, precreate_days: int):
        """Partition yönetim fonksiyonunu çağırır; sadece 'undefined_function' durumunu yutar."""
        print(f"[DB] managing partitions (keep={retention_days}d, precreate={precreate_days}d)")
        try:
            self.execute("SELECT public.manage_tick_log_partitions(%s,%s);", (retention_days, precreate_days))
        except psycopg2.Error as e:
            # 42883 = undefined_function
            if getattr(e, "pgcode", None) == "42883":
                self.rollback()
                print("[DB] partition manager function missing — skipped")
                return
            self.rollback()
            print(f"[DB] partition manager error pgcode={getattr(e,'pgcode',None)} detail={getattr(e,'pgerror',None)}")
            raise
        else:
            self.commit()

    def insert_ticks(self, rows: Iterable[Sequence[Any]]):
        """
        Tick verilerini batch halinde ekler.
        rows: (symbol, time_utc, time_msc, bid, ask, last, volume, flags, spread_pts)
        """
        count = len(rows)
        execute_values(
            self.cur,
            f"""
            INSERT INTO {self.schema}.{self.table}
              (symbol, time_utc, time_msc, bid, ask, last, volume, flags, spread_pts)
            VALUES %s
            ON CONFLICT (symbol, time_msc, time_utc) DO NOTHING
            """,
            rows,
            page_size=self.page_size,
        )
        print(f"[DB] inserted {count} ticks")

    def install_manage_partitions(self):
        """manage_tick_log_partitions fonksiyonunu idempotent oluşturur. RANGE(time_utc) + günlük partition."""
        sql = r"""
        CREATE OR REPLACE FUNCTION public.manage_tick_log_partitions(retention_days integer, precreate_days integer)
        RETURNS void
        LANGUAGE plpgsql
        AS $$
        DECLARE
            now_utc_date   date := (now() AT TIME ZONE 'UTC')::date;
            keep_from_date date := (now_utc_date - retention_days + 1);
            create_to_date date := (now_utc_date + precreate_days);
            d              date;
            part_name      text;
            idx_name1      text;
            idx_name2      text;
            got_lock       boolean;
            r              record;
        BEGIN
            -- Çakışmayı önle
            got_lock := pg_try_advisory_lock(hashtext('public.manage_tick_log_partitions(time_utc)'));
            IF NOT got_lock THEN
                RETURN;
            END IF;

            -- Gereken aralıkta günlük partition oluştur
            d := keep_from_date;
            WHILE d <= create_to_date LOOP
                part_name := format('tick_log_%s', to_char(d, 'YYYYMMDD'));
                BEGIN
                    EXECUTE format(
                        'CREATE TABLE IF NOT EXISTS public.%I PARTITION OF public.tick_log
                         FOR VALUES FROM ((%L)::timestamp AT TIME ZONE ''UTC'')
                                      TO ((%L)::timestamp AT TIME ZONE ''UTC'')',
                        part_name, d, d + 1
                    );

                    -- Yerel indeksler
                    idx_name1 := part_name || '_time_idx';
                    EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON public.%I (time_utc)', idx_name1, part_name);

                    idx_name2 := part_name || '_uq';
                    EXECUTE format(
                        'CREATE UNIQUE INDEX IF NOT EXISTS %I ON public.%I (symbol, time_msc, time_utc)',
                        idx_name2, part_name
                    );
                EXCEPTION
                    WHEN duplicate_table THEN
                        NULL;
                END;
                d := d + 1;
            END LOOP;

            -- Eski partisyonları kaldır (isimden gün yakala)
            FOR r IN
                SELECT
                    c.relname AS child_name,
                    to_date(substring(c.relname FROM 'tick_log_(\d{8})'), 'YYYYMMDD') AS part_date
                FROM pg_class c
                JOIN pg_inherits i ON i.inhrelid = c.oid
                JOIN pg_class p ON p.oid = i.inhparent
                WHERE p.relname = 'tick_log'
                  AND c.relnamespace = 'public'::regnamespace
                  AND c.relkind = 'r'
            LOOP
                IF r.part_date IS NOT NULL AND r.part_date < keep_from_date THEN
                    EXECUTE format('DROP TABLE IF EXISTS public.%I CASCADE', r.child_name);
                END IF;
            END LOOP;

            PERFORM pg_advisory_unlock(hashtext('public.manage_tick_log_partitions(time_utc)'));
        END;
        $$;
        """
        self.execute(sql)
        self.commit()
        print("[DB] partition manager function installed")
