# TickTracker Docker Kurulum Rehberi

> Not: Aşağıdaki örneklerde kullanılan placeholder değerler `.env` dosyasındaki gerçek bilgilerle değiştirilmeli ve yalnızca oradan yönetilmelidir.

## Amaç
PostgreSQL 16’yı `pg_cron` uzantısıyla Docker üzerinde çalıştırmak, var olan veriyi korumak ve günlük cron job’unu UTC 00:00’da çalıştırmak.

---

## Gereksinimler
- Windows işletim sistemi  
- Docker Desktop kurulu  
- Proje dizini:  
  `C:\Users\CatPawnD20\PycharmProjects\TickTracker`

---

## 1. Klasör Yapısı
```
TickTracker/
  database/
    Dockerfile
  docker-compose.yml
  .env
  ...
```

---

## 2. PostgreSQL + pg_cron için Dockerfile
`database/Dockerfile`
```Dockerfile
FROM postgres:16

RUN apt-get update \
 && apt-get install -y postgresql-16-cron \
 && rm -rf /var/lib/apt/lists/*
```

---

## 3. docker-compose.yml

### 3.1 Yeni Kurulum (veri sıfırdan)
```yaml
version: "3.9"
services:
  db:
    build: ./database
    container_name: ticktracker-postgres
    restart: always
    environment:
      POSTGRES_PASSWORD: <POSTGRES_PASSWORD>
      POSTGRES_DB: <POSTGRES_DB>
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    command:
      - "-c"
      - "shared_preload_libraries=pg_cron"
      - "-c"
      - "timezone=Etc/UTC"
      - "-c"
      - "cron.database_name=<POSTGRES_DB>"

volumes:
  pgdata:
```

### 3.2 Mevcut Volume’u Koruma
Önce mevcut container’ın volume adını bul:
```powershell
docker inspect pg16 --format='{{json .Mounts}}'
```
Örnek:
```
"Name":"<your_volume_id>"
```

Sonra compose dosyasında external volume olarak tanımla:
```yaml
version: "3.9"
services:
  db:
    build: ./database
    container_name: ticktracker-postgres
    restart: always
    environment:
      POSTGRES_PASSWORD: <POSTGRES_PASSWORD>
      POSTGRES_DB: <POSTGRES_DB>
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    command:
      - "-c"
      - "shared_preload_libraries=pg_cron"
      - "-c"
      - "timezone=Etc/UTC"
      - "-c"
      - "cron.database_name=<POSTGRES_DB>"

volumes:
  pgdata:
    external: true
    name: <your_volume_id>
```

---

## 4. .env Dosyası
```
ENABLE_PG_CRON=true
PG_CRON_SCHEDULE=0 0 * * *   # her gün UTC 00:00
```

---

## 5. Kurulum ve Çalıştırma
```powershell
cd C:\Users\CatPawnD20\PycharmProjects\TickTracker
docker compose up -d --build
docker ps
```

---

## 6. pg_cron Kurulumu
Container çalıştıktan sonra:
```powershell
docker exec -it ticktracker-postgres psql -U postgres -d <POSTGRES_DB> -c "CREATE EXTENSION IF NOT EXISTS pg_cron;"
docker exec -it ticktracker-postgres psql -U postgres -d <POSTGRES_DB> -c "SHOW shared_preload_libraries;"
docker exec -it ticktracker-postgres psql -U postgres -d <POSTGRES_DB> -c "SHOW timezone;"
```

---

## 7. Cron Job Testi (manuel)
```sql
SELECT cron.schedule(
  'public.tick_log_manage_partitions',
  '0 0 * * *',
  $$SELECT public.manage_tick_log_partitions(180, 3);$$
);
SELECT * FROM cron.job;
```

---

## 8. Günlük Kullanım
```powershell
docker start ticktracker-postgres
docker stop ticktracker-postgres
docker logs -f ticktracker-postgres
docker exec -it ticktracker-postgres psql -U postgres -d <POSTGRES_DB>
```

---

## 9. Otomatik Başlatma
`docker-compose.yml` içine:
```yaml
restart: always
```

---

## 10. Yedekleme ve Geri Yükleme
```powershell
docker exec -t ticktracker-postgres pg_dumpall -U postgres > C:\pg_dumpall.sql
type C:\pg_dumpall.sql | docker exec -i ticktracker-postgres psql -U postgres
```

---

## 11. Sorun Giderme
| Hata | Neden | Çözüm |
|------|--------|--------|
| `extension "pg_cron" is not available` | İmajda `postgresql-16-cron` yok | `database/Dockerfile` doğru olduğundan emin ol, sonra `docker compose up -d --build` |
| `pg_cron` görünmüyor | `shared_preload_libraries` ayarlanmamış | Compose `command` satırını kontrol et |
| Port çakışması | Başka container 5432’yi kullanıyor | Eski container’ı durdur veya porta `"5433:5432"` ata |
| Zaman farkı | Timezone yanlış | `SHOW timezone;` → `Etc/UTC` olmalı |

---

## 12. Minimum Komut Seti
```powershell
docker compose up -d --build
docker exec -it ticktracker-postgres psql -U postgres -d <POSTGRES_DB> -c "CREATE EXTENSION IF NOT EXISTS pg_cron;"
docker exec -it ticktracker-postgres psql -U postgres -d <POSTGRES_DB> -c "SHOW shared_preload_libraries;"
docker exec -it ticktracker-postgres psql -U postgres -d <POSTGRES_DB> -c "SELECT * FROM pg_extension WHERE extname='pg_cron';"
```

---

## 13. Notlar
- Cron işleri UTC saatine göre çalışır.
- Aynı volume adı kullanılırsa veri korunur.
- `[DB] commit` log’u sistemin doğru kurulduğunu gösterir.
