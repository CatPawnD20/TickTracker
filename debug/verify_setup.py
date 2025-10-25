# debug/verify_setup.py
import sys
import time
import psycopg2
import MetaTrader5 as mt5
from config import POSTGRES_CONFIG, MT5_CONFIG

def db_verify():
    print("== DB VERIFY ==")
    cfg = {
        "host": POSTGRES_CONFIG["host"],
        "port": POSTGRES_CONFIG.get("port", 5432),
        "user": POSTGRES_CONFIG["user"],
        "password": POSTGRES_CONFIG["password"],
        "dbname": POSTGRES_CONFIG["dbname"],
        "sslmode": POSTGRES_CONFIG.get("sslmode", "prefer"),
        "connect_timeout": POSTGRES_CONFIG.get("connect_timeout", 10),
    }
    schema = POSTGRES_CONFIG.get("schema", "public")
    table = POSTGRES_CONFIG.get("table_name", "tick_log")

    with psycopg2.connect(**cfg) as conn:
        with conn.cursor() as cur:
            # parent table
            cur.execute("""
                SELECT 1 FROM information_schema.tables
                WHERE table_schema=%s AND table_name=%s
            """, (schema, table))
            print("parent_table:", "ok" if cur.fetchone() else "missing")

            # default partition
            cur.execute("""
                SELECT 1 FROM information_schema.tables
                WHERE table_schema=%s AND table_name=%s
            """, (schema, f"{table}_default"))
            print("default_partition:", "ok" if cur.fetchone() else "missing")

            # global UNIQUE on parent
            cur.execute("""
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class t ON t.oid=c.conrelid
                JOIN pg_namespace n ON n.oid=t.relnamespace
                WHERE n.nspname=%s AND t.relname=%s AND c.conname='uq_tick_global'
            """, (schema, table))
            print("constraint_uq_tick_global:", "ok" if cur.fetchone() else "missing")

            # function existence
            cur.execute("""
                SELECT 1 FROM pg_proc p
                JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE p.proname='manage_tick_log_partitions' AND n.nspname='public'
            """)
            print("function_manage_partitions:", "ok" if cur.fetchone() else "missing")

            # list partitions
            cur.execute("""
                SELECT inhrelid::regclass::text
                FROM pg_inherits
                WHERE inhparent = %s::regclass
                ORDER BY 1 DESC
                LIMIT 10
            """, (f"{schema}.{table}",))
            parts = [r[0] for r in cur.fetchall()]
            print("partitions_top10:", parts if parts else "none")

            # default partition indexes
            cur.execute("""
                SELECT indexname FROM pg_indexes
                WHERE schemaname=%s AND tablename=%s
            """, (schema, f"{table}_default"))
            idxs = [r[0] for r in cur.fetchall()]
            print("default_indexes:", idxs if idxs else "none")

            # row counts
            cur.execute(f"SELECT count(*) FROM {schema}.{table}_default")
            print("rows_default:", cur.fetchone()[0])

            cur.execute(f"SELECT count(*) FROM {schema}.{table}")
            print("rows_total_parent:", cur.fetchone()[0])

            # latest rows (from parent, spans partitions)
            cur.execute(f"""
                SELECT symbol, time_utc, bid, ask, spread_pts
                FROM {schema}.{table}
                ORDER BY time_utc DESC
                LIMIT 5
            """)
            latest = cur.fetchall()
            print("latest_rows:", latest if latest else "none")

def mt5_verify():
    print("== MT5 VERIFY ==")
    ok = mt5.initialize(
        path=MT5_CONFIG.get("path"),
        login=MT5_CONFIG.get("login", 0),
        password=MT5_CONFIG.get("password", ""),
        server=MT5_CONFIG.get("server", "")
    )
    if not ok:
        code, msg = mt5.last_error()
        print("mt5_init_error:", code, msg)
        return

    symbol = MT5_CONFIG.get("symbol", "XAUUSD")
    si = mt5.symbol_info(symbol)
    if not si or not si.visible:
        if not mt5.symbol_select(symbol, True):
            print("symbol_select_failed:", symbol)
            mt5.shutdown()
            return

    t = mt5.symbol_info_tick(symbol)
    if t:
        print("tick:", {"bid": t.bid, "ask": t.ask, "time_msc": t.time_msc})
    else:
        print("tick: none")

    start_ms = int((time.time() - 3) * 1000)
    ticks = mt5.copy_ticks_from(symbol, start_ms / 1000.0, 1000, mt5.COPY_TICKS_ALL)
    print("ticks_3s_count:", 0 if ticks is None else ticks.size)
    mt5.shutdown()

if __name__ == "__main__":
    try:
        db_verify()
    except Exception as e:
        print("DB_VERIFY_ERROR:", repr(e))
    try:
        mt5_verify()
    except Exception as e:
        print("MT5_VERIFY_ERROR:", repr(e))
