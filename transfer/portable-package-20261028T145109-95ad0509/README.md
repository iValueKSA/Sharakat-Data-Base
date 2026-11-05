# Al-Ahsa Investment Opportunities Intelligence Platform

Arabic-first, source-traceable investment opportunity monitoring for Al-Ahsa Governorate. The source integration program has ten public-source adapters: Furas, Al-Ahsa Investment Opportunities Platform, AHDA, Invest Saudi, KFU, MODON, NCP, NHC, PIF Private Sector Hub, and MWAN. Public coverage limitations are preserved separately from technical health. No Wave 5 source is part of this platform change.

## Run locally on Windows

For normal use, install and start Docker Desktop once, then double-click [Start Platform.bat](Start%20Platform.bat). The launcher starts the local database, Redis, API, frontend, worker, and scheduler, waits for readiness, and opens `http://localhost:8080`. Use [Stop Platform.bat](Stop%20Platform.bat) to stop without deleting data. On first start, the existing SQLite dataset is backed up and imported once into local PostgreSQL; credentials are generated locally. Read [START-HERE.txt](START-HERE.txt) for the short user guide and the [Windows local runbook](docs/runbooks/local-windows.md) for technical details.

The first run requires Docker Desktop to be installed. The launcher starts it when installed but not running, and shows a friendly error when it is missing.

## Developer run (hot reload)

Requirements: Python 3.12+.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. This direct development mode defaults to SQLite and does not start the local user stack's PostgreSQL/Redis/Celery services. The legacy `ADMIN_TOKEN` path exists only outside production for development compatibility. Production and one-click local-user mode use provisioned users and HTTP-only sessions.

## Production reference

See [production architecture](docs/architecture/production-architecture.md), [production hardening report](docs/validation/production-hardening-phase-1.md), and the [deployment runbook](docs/runbooks/deployment.md). The Compose reference requires values from an external secret store and runs PostgreSQL, Redis, API, frontend, Celery worker, Beat scheduler, and a one-shot Alembic migration. The frontend binds to loopback for an HTTPS-terminating reverse proxy/load balancer. Never publish the database or Redis ports publicly.

For staging, use the same topology with a separate environment file and Compose project name:

```powershell
docker compose --env-file .env.staging -p alahsa-staging up --build -d
```

Staging must use separate PostgreSQL, Redis, administrator credentials, SMTP, and backup storage. `.env.example` contains variable names only.

## Main endpoints

- `GET /api/dashboard`, `/api/opportunities`, and `/api/sources`
- `GET /api/opportunities/{id}` for source links and change history
- `GET /api/export.csv` and `/api/export.xlsx`
- `POST /api/auth/login`, `/api/auth/logout`, and `GET /api/auth/me`
- Admin operations under `/api/admin/`
- `GET /health/live`, `/health/ready`, and `/metrics`

See `docs/source-analysis/` and `docs/validation/` for collection decisions and known public coverage limits. Source adapters retain the existing qualification, normalization, location evidence, duplicate resolution, provenance, and historical-data rules.
