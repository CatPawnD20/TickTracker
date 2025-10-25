# debug/check_pg_cron.py
"""pg_cron iş zamanlayıcısını hızlıca doğrulamak için yardımcı araç."""

import psycopg2

from config import POSTGRES_CONFIG, TRACKER_CONFIG


def pg_cron_status(job_name: str | None = None):
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

    target_job = job_name or f"{schema}.{table}_manage_partitions"

    with psycopg2.connect(**cfg) as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS pg_cron;")
            except psycopg2.Error as e:
                print("pg_cron_extension_error:", getattr(e, "pgerror", repr(e)))
                return

            cur.execute(
                """
                SELECT jobid, schedule, command, database, active
                FROM cron.job
                WHERE jobname=%s
                """,
                (target_job,),
            )
            row = cur.fetchone()

            if not row:
                print("jobname:", target_job)
                print("status:", "missing")
                return

            jobid, schedule, command, database, active = row
            print("jobname:", target_job)
            print("jobid:", jobid)
            print("schedule:", schedule)
            print("command:", command)
            print("database:", database)
            print("active:", active)


if __name__ == "__main__":
    print("== PG_CRON STATUS ==")
    if not TRACKER_CONFIG.get("enable_pg_cron", False):
        print("warning: TRACKER_CONFIG.enable_pg_cron false — job oluşturulmamış olabilir")
    pg_cron_status()
