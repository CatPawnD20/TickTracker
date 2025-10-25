# TickTracker

## Overview
TickTracker is a streaming worker designed to pull real-time tick data from the MetaTrader 5 (MT5) terminal and persist it to PostgreSQL. `tracker/Tracker.py` opens the MT5 session, validates symbol visibility, and reads newly arrived ticks sequentially in each loop. The raw entries are normalized in `tick/Tick.py`, where price, volume, and spread calculations are applied; before insertion the records are converted to a UTC timestamp and serialized into tuple form. On the storage side `database/PostgreSQL.py` guarantees the main table and default partition, loads the helper function for daily partitions, and creates the `pg_cron` job when required. Together the MT5→Tracker→Tick→PostgreSQL path becomes fully automated with partition management and cron triggers.

## Configuration Keys
The following environment variables are read via `.env` or the system environment (`config.py`). Duplicate `.env.example` into `.env` and replace the placeholder values with your actual credentials; the sample file intentionally contains fake data and must be updated for a real deployment.

| Group | Key | Description |
|------|---------|----------|
| MT5 | `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, `MT5_PATH`, `MT5_SYMBOL` | Login credentials for the MT5 terminal, terminal path, and default symbol. |
| PostgreSQL | `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DATABASE` | Core connection parameters. |
| PostgreSQL (advanced) | `POSTGRES_SCHEMA`, `POSTGRES_TABLE`, `POSTGRES_PAGE_SIZE`, `POSTGRES_SSLMODE`, `POSTGRES_TIMEOUT` | Schema/table names, batch insert size, SSL mode, and connection timeout. |
| Tracker | `BATCH_SIZE`, `POLL_MS`, `RETENTION_DAYS`, `PRECREATE_DAYS`, `ENABLE_PARTITION_MGMT`, `ENABLE_PG_CRON`, `PG_CRON_SCHEDULE`, `FLUSH_SEC` | Tick flush size, polling interval, partition retention/pre-creation windows, and cron parameters. |
| Tick | `TICK_POINT`, `TICK_SPREAD_ROUND` | Pip value and rounding precision used for spread calculations. |

## Docker Setup (Summary)
To run PostgreSQL 16 with `pg_cron` in Docker, consult `dockerHelp.md` for a step-by-step guide. In the compose file the critical `command` directives load the `pg_cron` extension and force UTC time zone; the volume definition mounts `pgdata` as an external volume for persistent storage. Additional scenarios (external volumes, `.env`, test commands) and detailed guidance are covered in `dockerHelp.md`.

## Pre-installing the Partition Function
`database/partitionManager.txt` keeps the raw SQL for the partition helper function and should be executed in the database before the project is launched. While the tracker runs, `PostgreSQL.install_manage_partitions` applies the same logic idempotently and is invoked inside `Tracker._init_db`, ensuring the function exists. Manual SQL execution is helpful for first-time setups where database permissions or external automation require upfront provisioning.

## Troubleshooting Scripts
| Script | Scenario | Details |
|--------|---------|-------|
| `debug/verify_setup.py` | Validate MT5 and PostgreSQL connectivity as well as partition tables/functions. | `db_verify()` checks for tables, indexes, and function presence; `mt5_verify()` ensures symbol and tick accessibility. |
| `debug/check_pg_cron.py` | Inspect the existence and status of the `pg_cron` job. | Creates or reports the target job if missing; outputs cron schedule, command, and active flag. |

## Running
1. Copy the sample environment file with `cp .env.example .env` and update the MT5/PostgreSQL fields with real values.
2. (Optional) Load the partition function into the database using `database/partitionManager.txt`.
3. Start the application with `python run_tracker.py [SYMBOL]`; if no symbol is provided the default from `config.py` is used. The tracker configuration invokes the partition helper according to `RETENTION_DAYS`/`PRECREATE_DAYS`, controlled by `ENABLE_PARTITION_MGMT` and `ENABLE_PG_CRON` flags.

## Directory Layout
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
├── README.en.md (this file)
└── README.md
```

See also: [Docker setup](dockerHelp.md), [pg_cron compose configuration](docker-compose.yml), and the [partition SQL template](database/partitionManager.txt).
