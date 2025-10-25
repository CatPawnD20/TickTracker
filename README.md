# TickTracker

## Genel Bakış
TickTracker, MetaTrader 5 (MT5) terminalinden gerçek zamanlı tick verisi alıp PostgreSQL'e yazmak üzere tasarlanmış bir akış işleyicisidir. `tracker/Tracker.py`, MT5 oturumunu açar, sembol görünürlüğünü doğrular ve her döngüde yeni tick'leri sıralı şekilde okur.【F:tracker/Tracker.py†L13-L122】 Toplanan ham kayıtlar `tick/Tick.py` sınıfında fiyat, hacim ve spread hesaplarıyla normalize edilir; veritabanına gönderilmeden önce UTC zaman damgasına dönüştürülür ve tuple formatına serilir.【F:tick/Tick.py†L5-L42】 Yazma tarafında `database/PostgreSQL.py`, ana tabloyu ve varsayılan partisyonu garanti eder, günlük partisyonlar için fonksiyonu yükler ve gerekirse `pg_cron` job'unu oluşturur.【F:database/PostgreSQL.py†L9-L200】【F:database/PostgreSQL.py†L200-L286】 Böylece MT5→Tracker→Tick→PostgreSQL hattı, partisyon yönetimi ve cron tetikleyicileri ile birlikte uçtan uca otomatikleşir.

## Yapılandırma Anahtarları
Aşağıdaki ortam değişkenleri `.env` veya sistem ortamı üzerinden okunur (`config.py`).【F:config.py†L1-L58】 Depoya dahil edilen `.env.example` dosyasını kopyalayıp gerçek değerlerle doldurarak `.env` oluşturabilirsiniz; örnek dosyadaki tüm placeholder'lar sahte kimlik bilgileri içerir ve gerçek kurulumda değiştirilmelidir.

| Grup | Anahtar | Açıklama |
|------|---------|----------|
| MT5 | `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, `MT5_PATH`, `MT5_SYMBOL` | MT5 terminaline giriş kimlik bilgileri, terminal yolu ve varsayılan sembol. |
| PostgreSQL | `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DATABASE` | Temel bağlantı parametreleri. |
| PostgreSQL (ileri) | `POSTGRES_SCHEMA`, `POSTGRES_TABLE`, `POSTGRES_PAGE_SIZE`, `POSTGRES_SSLMODE`, `POSTGRES_TIMEOUT` | Şema/tablolar, batch ekleme boyutu, SSL modu ve bağlantı zaman aşımı. |
| Tracker | `BATCH_SIZE`, `POLL_MS`, `RETENTION_DAYS`, `PRECREATE_DAYS`, `ENABLE_PARTITION_MGMT`, `ENABLE_PG_CRON`, `PG_CRON_SCHEDULE`, `FLUSH_SEC` | Tick flush boyutu, çekme periyodu, partisyon saklama/ön-oluşturma günleri ve cron parametreleri. |
| Tick | `TICK_POINT`, `TICK_SPREAD_ROUND` | Spread hesapları için pip değeri ve yuvarlama basamağı. |

## Docker Kurulumu (Özet)
Docker ortamında PostgreSQL 16 + `pg_cron` çalıştırmak için `dockerHelp.md` ayrıntılı adımları sunar. Compose dosyasında kritik `command` satırları `pg_cron` kütüphanesini yükleyip zaman dilimini UTC'ye sabitler; volume tanımı kalıcı veri için `pgdata` bağını dış volume olarak işaretler.【F:docker-compose.yml†L1-L24】 Ek senaryolar (external volume, .env, test komutları) ve ayrıntılı yönergeler için `dockerHelp.md` belgesine bakın.【F:dockerHelp.md†L1-L189】

## Partition Fonksiyonunun Ön Kurulumu
`database/partitionManager.txt`, partisyon fonksiyonunun ham SQL sürümünü saklar ve proje başlatılmadan önce veritabanında çalıştırılması gereken referans betiğidir.【F:database/partitionManager.txt†L1-L48】 Tracker çalışırken `PostgreSQL.install_manage_partitions` aynı mantığı idempotent olarak uygular ve `Tracker._init_db` içinde çağrılır; böylece fonksiyonun mevcut olduğundan emin olunur.【F:database/PostgreSQL.py†L200-L286】【F:tracker/Tracker.py†L26-L47】 Manuel SQL uygulaması, özellikle ilk kurulumlarda veritabanı hakları veya dış otomasyon gerektiren ortamlarda başlangıç noktası sağlar.

## Hata Giderme Scriptleri
| Script | Senaryo | Detay |
|--------|---------|-------|
| `debug/verify_setup.py` | MT5 ve PostgreSQL bağlantılarını doğrulamak, partisyon tablosu/fonksiyonlarını kontrol etmek. | `db_verify()` tablo, indeks ve fonksiyon varlığını kontrol eder; `mt5_verify()` sembol ve tick erişimini sınar.【F:debug/verify_setup.py†L1-L132】 |
| `debug/check_pg_cron.py` | `pg_cron` job'unun varlığını ve durumunu sorgulamak. | Hedef job'u oluşturur/yoksa bildirir; cron schedule, komut ve aktiflik bilgilerini döker.【F:debug/check_pg_cron.py†L1-L60】 |

## Çalıştırma
1. `cp .env.example .env` komutuyla örnek ortam dosyasını kopyalayın ve gerekli MT5/PostgreSQL bilgilerini gerçek değerlerle güncelleyin.
2. (Opsiyonel) Partisyon fonksiyonunu veritabanına yükleyin (`database/partitionManager.txt`).
3. Uygulamayı `python run_tracker.py [SEMBOL]` komutuyla başlatın; sembol parametresi verilmezse `config.py` içerisindeki varsayılan kullanılır.【F:run_tracker.py†L1-L8】【F:tracker/Tracker.py†L13-L121】 `Tracker` yapılandırması, `RETENTION_DAYS`/`PRECREATE_DAYS` değerlerine göre partisyon fonksiyonunu çağırır ve `ENABLE_PARTITION_MGMT`/`ENABLE_PG_CRON` bayraklarıyla kontrol edilir.【F:tracker/Tracker.py†L13-L122】【F:config.py†L30-L49】

## Dizin Yapısı
```
TickTracker/
├── config.py
├── run_tracker.py
├── tracker/
│   └── Tracker.py
├── tick/
│   └── Tick.py
├── database/
│   ├── PostgreSQL.py
│   ├── partitionManager.txt
│   └── Dockerfile
├── debug/
│   ├── verify_setup.py
│   └── check_pg_cron.py
├── docker-compose.yml
├── dockerHelp.md
├── .env
├── env.example
├── requirements.txt
├── README.en.md
└── README.md (bu dosya)
```

Ek kaynaklar için: [Docker kurulumu](dockerHelp.md), [pg_cron compose ayarları](docker-compose.yml), [partisyon SQL şablonu](database/partitionManager.txt).
