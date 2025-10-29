# config.py
from dotenv import load_dotenv
import os

load_dotenv(override=True)  # env güncellemeleri sırasında güvenli yükleme

MT5_CONFIG = {
    "login": int(os.getenv("MT5_LOGIN", 0)),
    "password": os.getenv("MT5_PASSWORD", ""),
    "server": os.getenv("MT5_SERVER", ""),
    "path": os.getenv("MT5_PATH", ""),
    "symbol": os.getenv("MT5_SYMBOL", "XAUUSD"),
}

# --- PostgreSQL parametreleri ---
MT4_CONFIG = {
    "login": int(os.getenv("MT4_LOGIN", 0)),
    "password": os.getenv("MT4_PASSWORD", ""),
    "server": os.getenv("MT4_SERVER", ""),
    "path": os.getenv("MT4_PATH", ""),
    "symbol": os.getenv("MT4_SYMBOL", "XAUUSD"),
}

POSTGRES_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
    "dbname": os.getenv("POSTGRES_DATABASE", "trading"),

    # Ek konfigürasyonlar:
    "schema": os.getenv("POSTGRES_SCHEMA", "public"),           # tablo şeması
    "table_name": os.getenv("POSTGRES_TABLE", "tick_log"),      # tablo adı
    "page_size": int(os.getenv("POSTGRES_PAGE_SIZE", 1000)),    # batch insert büyüklüğü
    "sslmode": os.getenv("POSTGRES_SSLMODE", "prefer"),         # SSL bağlantı modu
    "connect_timeout": int(os.getenv("POSTGRES_TIMEOUT", 10))   # bağlantı zaman aşımı (saniye)
}

# --- Tracker parametreleri ---
TRACKER_CONFIG = {
    # Kaç tick toplandıktan sonra database'e yazılacağı
    "batch_size": int(os.getenv("BATCH_SIZE", 200)),

    # MT5'ten tick verisi çekme aralığı (ms)
    "poll_ms": int(os.getenv("POLL_MS", 200)),

    # Günlük partition yönetimi
    "retention_days": int(os.getenv("RETENTION_DAYS", 180)),   # kaç gün geriye saklanacak
    "precreate_days": int(os.getenv("PRECREATE_DAYS", 3)),     # kaç gün ileriye tablo oluşturulacak

    # Partition yönetimi bayrağı
    "enable_partition_mgmt": os.getenv("ENABLE_PARTITION_MGMT", "true").lower() == "true",
    "enable_pg_cron": os.getenv("ENABLE_PG_CRON", "false").lower() == "true",
    "pg_cron_schedule": os.getenv("PG_CRON_SCHEDULE", "15 02 * * *"),

    # (opsiyonel) flush_sec — sistem bütünlüğü için placeholder, kullanılmıyor
    "flush_sec": int(os.getenv("FLUSH_SEC", 1)),
}

# --- Tick parametreleri ---
TICK_CONFIG = {
    # Point değeri: 1 pip'in fiyat karşılığı (örnek: XAUUSD için 0.01)
    "point": float(os.getenv("TICK_POINT", 0.01)),

    # Fiyat farkı (spread) yuvarlama hassasiyeti
    "spread_round": int(os.getenv("TICK_SPREAD_ROUND", 5))
}
