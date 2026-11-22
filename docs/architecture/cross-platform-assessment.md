# Cross-Platform, Docker-Free Runtime: Assessment and Proposed Architecture

Status: **Implemented (native runtime added; Docker files still present, no longer required).** See §9 for what was built and what still needs verification on real machines.
Date: 2026-11-22

This document records what the platform depends on today, where those dependencies are tied to Docker or to Windows, and how the runtime can be re-hosted natively on Windows, Linux and macOS without changing the UI, the API contracts or the business logic. It ends with the decisions that need an owner's sign-off before implementation starts.

---

## 1. Current system

### 1.1 Runtime topology (`docker-compose.yml`)

| Service | Image / command | Role |
|---|---|---|
| `db` | `postgres:16-alpine` | System of record. Volume `postgres_data`. |
| `redis` | `redis:7-alpine`, `--appendonly yes --requirepass` | Celery broker + result backend, distributed locks, rate limits, worker heartbeats. |
| `migrate` | `alembic upgrade head` (one-shot) | Schema migrations before API/worker start. |
| `api` | `uvicorn app.main:app --port 8000 --proxy-headers` | FastAPI backend. Also serves the UI (`/` and `/static`). |
| `worker` | `celery worker --queues=source_sync,maintenance,notifications --concurrency=4` | Source sync, backups, alerts, data quality. |
| `scheduler` | `celery beat` | 9 periodic schedules (`app/celery_app.py`). |
| `frontend` | `nginx-unprivileged` + `deploy/nginx.conf` | Serves `app/static`, reverse-proxies `/api` and `/health` to `api:8000`, adds security headers. Bound to `127.0.0.1:8080`. |
| `local-bootstrap` | `scripts/local_database_setup.py` (local overlay only) | One-time import of the legacy SQLite file into PostgreSQL. |

The runtime image also installs `postgresql-client-16` so the worker can run `pg_dump` (`app/backups.py`).

Six additional compose overlays (`docker-compose.furas-*.yml`, `lifecycle-patch*.yml`, `local.yml`, `portable.yml`) pin image tags and toggle feature flags for specific operational events.

### 1.2 Application

* **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic (28 migrations), Pydantic 2. About 20 000 lines in `app/`, with large modules: `main.py` (3 586 lines, all routes), `adapters.py` (2 947, ten source adapters), `service.py`, `data_quality.py`.
* **Frontend:** a static, framework-free SPA (`app/static/index.html`, `app.js`, CSS, vendored Leaflet). View state is in the query string (`?view=…`) and the path is always `/`, so nginx's `try_files … /index.html` fallback isn't needed for routing.
* **Auth:** HTTP-only session cookies, HMAC session digests keyed by `SECRET_KEY`, RBAC (`admin` / `analyst` / `viewer`), bootstrap admin from env, legacy `ADMIN_TOKEN` outside protected environments.
* **Background work:** Celery tasks in `app/tasks.py` and `app/document_collection/tasks.py`, routed to six queues. A non-Celery fallback (`service.scheduler_loop`) exists for development only (`SYNC_ON_STARTUP=true`).
* **Configuration:** about 50 environment variables read directly with `os.getenv` across many modules. There is no central settings object.
* **Windows launchers:** 11 `.bat` files plus about 1 900 lines of PowerShell (`Setup Platform.ps1`, `Prepare Transfer.ps1`, `scripts/*.ps1`) that install WSL2/Docker Desktop through WinGet and drive `docker compose`.
* **CI:** GitHub Actions on Ubuntu runs the tests on SQLite, migrations on a PostgreSQL 16 service, `pip-audit`, and builds both Docker images.

### 1.3 What is already portable

* Dev mode (`uvicorn app.main:app`) already runs without Docker on SQLite, with Redis and Celery switched off.
* FastAPI already serves the identical UI (`GET /` returns `index.html`, `/static` is mounted) and already sets the same security headers as nginx (CSP, `X-Frame-Options`, `nosniff`, `Referrer-Policy`, HSTS in protected environments).
* All Python dependencies (`psycopg[binary]`, `lxml`, `Pillow`, etc.) ship wheels for Windows, Linux and macOS (x64 and arm64).
* PostgreSQL 16 and the Redis protocol both have native builds on all three platforms (see §4 for the Windows caveat on Redis).

---

## 2. Findings

### 2.1 Docker coupling

| # | Where | Coupling |
|---|---|---|
| D1 | `app/celery_app.py:8`, `app/tasks.py:60` | Default `REDIS_URL=redis://redis:6379/0` uses the Compose hostname `redis`. |
| D2 | `app/backups.py:14`, `app/main.py:1304` | Default `BACKUP_DIR=/backups` is a container mount point. |
| D3 | `app/backups.py:19` | `pg_dump` must be on `PATH`. The image installs it; native hosts may not have it. |
| D4 | `deploy/nginx.conf` | `resolver 127.0.0.11` (Docker DNS) and upstream `api:8000`. |
| D5 | `.env.example`, `docker-compose.yml` | `FORWARDED_ALLOW_IPS=172.31.240.10` and a fixed Compose subnet, used so the API trusts nginx's `X-Forwarded-*`. |
| D6 | `.env.local.example`, `local.yml` | `DATABASE_URL=…@db:5432`, `LOCAL_SQLITE_PATH=/source-data/…`. |
| D7 | `scripts/*.ps1` (9 files), `Setup Platform.ps1`, `Prepare Transfer.ps1` | The whole install / start / stop / status / verify / transfer lifecycle is `docker compose`. |
| D8 | Compose `depends_on` + healthchecks | Startup ordering (db healthy → migrate → bootstrap → api/worker/beat) exists only in Compose. |
| D9 | `.github/workflows/ci.yml` | Builds Docker images as a release gate. |

### 2.2 OS and working-directory coupling

| # | Where | Issue |
|---|---|---|
| P1 | `app/main.py:772,1228` | `StaticFiles(directory="app/static")` and `FileResponse("app/static/index.html")` are relative to the current directory. They break if the API isn't launched from the repo root. |
| P2 | `app/database.py:8–11`, `app/main.py:54`, `alembic.ini` | `./data/...` relative defaults. The same applies to `ATTACHMENT_DIR=data/attachments`. |
| P3 | Celery on Windows | The default `prefork` pool isn't supported on Windows. `--pool=threads`/`solo` work, but **hard `task_time_limit` isn't enforced** outside prefork (soft limits are best-effort). Sync jobs rely on a 1 800 s hard limit plus stale-job recovery. |
| P4 | Lifecycle tooling | Windows only (PowerShell / `.bat`). There's nothing for Linux or macOS. |
| P5 | `README.md` | Hard-codes another developer's OneDrive path as the "only authorized source checkout". |
| **P6** | `app/export_storage.py:_ensure_private_root` | **XLSX export always fails on native Windows (HTTP 507).** `os.chmod(…, 0o700)` doesn't set POSIX mode bits on Windows, directories report `0o777`, and the `& 0o077` check rejects the directory every time. This is hidden today because the API only ever runs in a Linux container. Fix: on Windows, rely on the per-user `%TEMP%` ACL (or set an explicit owner-only DACL) instead of mode bits. Confirmed on this machine. |
| P7 | `pytest` configuration | There's no `testpaths`, so a bare `pytest` collects the 32 project copies under `transfer/` and aborts with 914 collection errors. CI runs bare `pytest -q` on a checkout that tracks `transfer/`. Fix: `testpaths = tests` plus untracking `transfer/`. |

### 2.2.1 Baseline test run (current code, no changes)

Windows 11, Python 3.11.9 (3.12 isn't installed on the assessment machine), SQLite, `pytest tests`: **753 passed, 32 failed, 7 errors, 9 skipped**.

| Group | Count | Cause | Platform-related? |
|---|---|---|---|
| Export endpoints return 507 / unreadable xlsx | ~18 | P6 | **Yes.** Must pass after the Windows fix. |
| `test_opportunity_documents.py` setup errors | 7 | Require a disposable PostgreSQL database by design | No (environment) |
| `test_dashboard_video_hero.py` | ~6 | Assert markup/CSS strings no longer in `index.html` / `data-dashboard.css` (tests lag the current UI) | No (pre-existing) |
| NCP portal adapter, status-lifecycle label | ~6 | Not yet classified | To be checked on Linux before attributing to Windows |

The Linux CI result is the reference baseline. Each group above must be either green or explained there before the migration starts.

### 2.3 Hard requirements the native runtime must keep

* **PostgreSQL, not SQLite, for the operational install.** The code relies on `SELECT … FOR UPDATE` (more than 15 call sites), `pg_advisory_xact_lock` / `pg_advisory_unlock` (`main.py:2914`, `document_collection/engine.py`, `furas_checkpoint.py`), a `pg_trgm` GIN index (migration 0014) and partial unique indexes. These paths silently degrade or no-op on SQLite. SQLite stays a dev/test convenience only.
* **Redis semantics.** Besides the broker, Redis provides `SET NX EX` source locks with Lua compare-and-delete release (`tasks.py`, about 20 call sites), scheduler leader election (`scheduler:leader`), queued-job reservations, `celery control inspect`/`revoke` (`main.py:1374`, `tasks.py:293`, `data_quality.py:1205`), and `INCR/EXPIRE` rate limiting (`security.py`).
* **Start order:** migrations → (first run only) SQLite import → API, worker, beat.

### 2.4 Security observations

| # | Finding | Recommendation |
|---|---|---|
| S1 | `SECRET_KEY` falls back to `"development-only-session-key"` (`security.py:41`), and the startup guard only runs for `production`/`staging`, not `local_user`. A local install missing the key would sign sessions with a public constant. | The native installer generates the key, and `local_user` refuses to start without it. |
| S2 | Rate limiting fails open to in-process memory when Redis is unavailable, except in `production`. | Acceptable locally. Document it. |
| S3 | The native runtime must keep PostgreSQL and Redis bound to `127.0.0.1` with generated passwords. The Compose network currently isolates them. | Enforced by the generated configs (`listen_addresses='127.0.0.1'`, Redis `bind 127.0.0.1` + `requirepass`). |
| S4 | The repository tracks about 30 000 generated files (`transfer/`, `tmp/`, `docs/validation/`), including logical database dumps (about 457 MB of git history). Dumps contain password hashes. | Remove them from version control and add them to `.gitignore`. This is a prerequisite to any release work (see §7). |

### 2.5 Maintainability observations (not blockers)

* `main.py` mixes about 150 routes, auth middleware, metrics and helpers. Splitting it into `APIRouter` modules is mechanical and low-risk, but it is **not needed** for portability. It is proposed as an optional later step, guarded by the existing route regression tests.
* Configuration is read ad hoc everywhere, and `os.getenv("ENVIRONMENT",os.getenv("ENV","development")).lower()` alone is repeated more than 10 times.

---

## 3. Target architecture

Principle: **change the infrastructure seams, not the domain.** Adapters, normalization, merge, data quality, review lifecycle and the UI aren't touched. Every change below is in configuration, process management or packaging.

```
                ┌──────────── sharakat (Python CLI, stdlib only) ────────────┐
                │ install · start · stop · status · doctor · backup · restore │
                │ migrate · import-legacy · service install/uninstall          │
                └───────┬───────────────┬───────────────┬───────────────┬─────┘
                        │ supervises    │               │               │
            ┌───────────▼──┐  ┌─────────▼────┐  ┌───────▼──────┐  ┌─────▼────────┐
            │ PostgreSQL 16│  │ Redis-protocol│  │ uvicorn API  │  │ celery worker│
            │ app-owned    │  │ server        │  │ + UI (static)│  │ + celery beat│
            │ cluster      │  │ 127.0.0.1     │  │ 127.0.0.1:8080│ │              │
            └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
                 data dir, logs, backups, config → per-OS app-data directory
```

### 3.1 New / changed modules

| Module | Responsibility |
|---|---|
| `app/settings.py` | Single typed settings object (stdlib `dataclass` + env parsing, no new dependency). Holds every variable now read with `os.getenv`, with the **same names and defaults** except the Docker-specific defaults D1, D2 and D6. Modules migrate to it one at a time. Behaviour stays identical because env names are unchanged. |
| `app/paths.py` | Resolves the package root (`Path(__file__)`) for static assets (fixes P1) and the per-OS data root: `%LOCALAPPDATA%\Sharakat` on Windows, `~/Library/Application Support/Sharakat` on macOS, `$XDG_DATA_HOME/sharakat` on Linux. Overridable with `SHARAKAT_HOME`, which allows a portable folder install. |
| `platform_runtime/` (new top-level package) | The CLI and the process supervisor. Starts the components in dependency order, waits on real readiness probes (`pg_isready`-equivalent via psycopg, Redis `PING`, `/health/ready`), writes PID files and logs under the data root, and shuts down gracefully (worker drain uses the existing `stop_grace_period` equivalent of 2 minutes). Uses `subprocess` and `signal` from the stdlib, with OS-specific bits behind one small `ProcessHost` abstraction (`CREATE_NEW_PROCESS_GROUP`/`CTRL_BREAK_EVENT` on Windows, process groups and `SIGTERM` on POSIX). |
| `platform_runtime/providers/` | One provider per external binary (`postgres`, `redis`), each with `locate() → install() → init() → start() → stop() → health()`. This is the only place where per-OS install logic lives. |
| Launchers | Thin wrappers that call the CLI: existing `.bat` files keep their names and double-click behaviour on Windows, `sharakat.sh` on Linux, `Sharakat.command` on macOS. |

### 3.2 Reverse proxy

nginx is dropped from the local runtime. uvicorn serves the UI and API on `127.0.0.1:8080`, so the user-facing URL is unchanged. Required parity:

* Security headers are already emitted by the FastAPI middleware (identical CSP).
* `X-Request-ID` is already generated by the middleware when absent.
* The 240 s export timeout isn't needed without a proxy. uvicorn has no read timeout on streamed responses.
* `client_max_body_size 2m`: add an equivalent request-size check in the middleware for the upload routes, so behaviour stays the same.
* `--proxy-headers`/`FORWARDED_ALLOW_IPS`: not needed when nothing sits in front of uvicorn. For production behind a real TLS proxy, `deploy/nginx.conf` is kept as a reference (upstream changed to `127.0.0.1:8000`, Docker resolver removed).

### 3.3 Startup sequence (replaces Compose `depends_on`)

1. Load config from `<data root>/config/.env`, which the installer generates with fresh secrets and permissions restricted to the user.
2. Start PostgreSQL and wait until it accepts connections. Start Redis and wait for `PING`.
3. `alembic upgrade head` (skipped when `AUTO_MIGRATE=false`, matching the pinned "migrations disabled" overlays).
4. First run only: `scripts/local_database_setup.py` imports legacy SQLite (unchanged script; only its paths come from settings).
5. Start uvicorn, the Celery worker and Celery beat. Wait for `/health/ready`, then open the browser.

---

## 4. Docker elimination per component

| Component | Native replacement | Windows | Linux | macOS |
|---|---|---|---|---|
| PostgreSQL 16 | **App-owned cluster**: `initdb` into `<data root>/pgdata`, `pg_ctl` start/stop, `listen_addresses=127.0.0.1`, generated password, private port (default 54329, configurable). Also provides `pg_dump`/`pg_restore`, which fixes D3. | EDB binaries (zip, no system service required) | PGDG packages (`apt`/`dnf`) | Postgres.app binaries or Homebrew `postgresql@16` |
| Redis | Redis-protocol server bound to `127.0.0.1` with `requirepass` and AOF | **Decision required (§6, Q1)** | Distribution `redis`/`valkey` package | Homebrew `redis` |
| Celery worker | Native process | `--pool=threads --concurrency=4` | `prefork` (unchanged) | `prefork` (unchanged) |
| Celery beat | Native process, schedule file under the data root | same | same | same |
| nginx | Removed locally; uvicorn serves the UI (§3.2) | — | — | — |
| One-shot migrate / bootstrap | CLI steps in the startup sequence | — | — | — |
| Python 3.12 | The installer provisions a private runtime and venv under the data root | python.org installer or `winget` | system `python3.12` or deadsnakes | python.org pkg or Homebrew |

**Windows hard time limits (P3).** With the threads pool a hung sync isn't killed at 1 800 s. Mitigation: the existing soft limit plus `recover_stale_jobs` already marks stale jobs; add an explicit `httpx` timeout audit across the adapters so no single request can hang indefinitely. This needs sign-off (§6, Q2).

---

## 5. Installation, operations and testing

### 5.1 Install

`install` is idempotent and resumable (the existing reboot-resume pattern is kept):

1. Check prerequisites and disk space (`doctor`).
2. Provision Python 3.12 and the venv, then `pip install -r requirements.txt` (pinned with a lock file, see 5.4).
3. Provision PostgreSQL and Redis through their providers.
4. Generate config and secrets (fixes S1). Write `Local Admin Credentials.txt` with user-only ACLs, as today.
5. Optionally register as a service: systemd user unit (Linux), launchd agent (macOS), Task Scheduler at-logon task on Windows. The Task Scheduler task needs no admin rights and no extra tool such as NSSM.

### 5.2 Existing Docker installs: data migration

The current `Prepare Transfer` step already produces a verified, checksummed `pg_dump`. The native `restore` command accepts that package, so a user moves by running *Prepare Transfer* on the Docker install once, then *Setup* on the native one. No data is converted. PostgreSQL stays on major version 16, so the dump restores as-is. The legacy SQLite import path also stays.

### 5.3 Backup and recovery

`app/backups.py` is unchanged apart from resolving `pg_dump` from the provisioned binaries and `BACKUP_DIR` from settings. The daily Beat schedule and the retention logic are unchanged. `sharakat restore <dump>` wraps `pg_restore` into a fresh database and refuses to overwrite a non-empty one, matching current Setup behaviour.

### 5.4 Testing strategy

| Layer | What | Where |
|---|---|---|
| Existing suite | All 66 test files, unchanged, as the regression baseline | CI matrix: `ubuntu`, `windows`, `macos` × Python 3.12 |
| PostgreSQL integration | Run the suite against real PostgreSQL 16 so the `FOR UPDATE`, advisory-lock and trigram paths are exercised. CI currently only runs migrations on PostgreSQL. | CI service container on Linux; provisioned cluster on Windows/macOS |
| Redis/Celery integration | Lock acquire/release Lua scripts, leader election, `inspect`/`revoke`, a real sync of a fixture source through the worker | All three OSes against the chosen Redis provider |
| Runtime | `install → start → /health/ready → login → export.xlsx → stop → start` on clean runners | CI matrix, `doctor` on user machines |
| UI regression | Playwright screenshots of every view against the Docker baseline, pixel diff zero (same HTML/CSS/JS bytes, so a mismatch means a serving difference such as MIME types or headers) | Linux CI |
| API regression | Recorded request/response snapshots of all `GET` endpoints from the Docker stack, replayed against native | Linux CI |
| Security | `pip-audit` (existing), check that DB/Redis listen only on loopback, refuse start without `SECRET_KEY` | CI |

Dependencies get pinned (`requirements.lock` via `pip-compile`) so the three OSes install the same versions. Today only ranges are specified.

---

## 6. Decisions required before implementation

**Q1: Redis on Windows.** There's no official Redis server for Windows. Options:

| Option | Change to app code | Risk |
|---|---|---|
| **A. Redis-compatible server per OS** (Redis/Valkey on Linux/macOS; Microsoft **Garnet**, MIT-licensed, on Windows) | None | Garnet has to pass the Celery transport plus the Lua compare-and-delete scripts. Needs a 1-day compatibility spike before committing. |
| B. Run Redis through WSL on Windows | None | Reintroduces WSL, which is close to the dependency we're removing. |
| C. Replace Redis with PostgreSQL (advisory locks, a rate-limit table, a DB-backed Celery broker) | Large: about 30 call sites plus Celery transport | Kombu's SQL transport lacks broadcast, so `inspect`/`revoke` break. High regression risk. |

Recommendation: **A, gated on the spike.** If Garnet fails the spike, fall back to discussing C as a separately scoped project.

**Q2: Windows hard task time limits.** Accept soft limits plus stale-job recovery on Windows (recommended), or require a different pool.

**Q3: Docker as an option.** Keep `Dockerfile`/Compose as an *optional* production deployment path (recommended, since the production reference and runbooks depend on it), or delete them entirely. Either way, nothing in the native path requires Docker.

**Q4: Scope of internal refactoring.** Limit it to the infrastructure seams above (recommended), or also split `main.py` into routers in this project.

---

## 7. Proposed implementation order

Each step leaves the application deployable and is verified by the full test suite before the next one starts.

0. **Repository hygiene:** untrack `transfer/`, `tmp/` and generated validation dumps, and update `.gitignore`. History rewrite is a separate, explicitly approved action.
1. `app/paths.py` plus package-relative static paths (P1, P2). No behaviour change.
2. `app/settings.py`, migrating modules incrementally; Docker defaults D1, D2, D6 replaced; S1 guard for `local_user`.
3. Redis compatibility spike (Q1).
4. `platform_runtime`: PostgreSQL provider, Redis provider, supervisor, CLI (Linux first, then macOS, then Windows).
5. Launchers (`.bat`, `.sh`, `.command`), service integration, `doctor`.
6. Restore from existing transfer packages (data migration for current users).
7. CI matrix on three OSes, PostgreSQL integration run, UI and API regression against the Docker baseline.
8. Documentation: per-OS install, configuration reference, runbooks updated (`local-windows.md` replaced by `native-runtime.md`, `deployment.md`, `staging.md`, `database-restore.md`), and an ADR for this change.

## 8. Original vs. proposed

| Concern | Today | Proposed |
|---|---|---|
| Host requirements | Windows 11 + WSL2 + Docker Desktop | Windows 10/11, Linux, macOS; no container runtime |
| Orchestration | Compose `depends_on` + healthchecks | Python supervisor with the same order and real probes |
| UI serving | nginx container | uvicorn (already serves the identical assets and headers) |
| Database | PostgreSQL 16 in a container volume | PostgreSQL 16 cluster owned by the app in the per-OS data dir |
| Queue / locks | Redis container | Redis-protocol server on loopback (per Q1) |
| Config | ~50 scattered `os.getenv`, Docker hostnames as defaults | One settings module, same variable names, host-neutral defaults |
| Lifecycle tooling | ~1 900 lines of PowerShell (Windows only) | One cross-platform CLI with thin per-OS launchers |
| Business logic, API, UI | — | Unchanged |

---

## 9. Implementation record (2026-11-22)

Decisions taken: Q1 **Garnet on Windows** (native Redis/Valkey on Linux/macOS, Garnet as fallback), Q2 **soft limits plus stale-job recovery on Windows**, Q3 Docker files kept for now (nothing in the native path uses them), Q4 **infrastructure seams only**.

| Area | Change |
|---|---|
| Repository | `transfer/`, `tmp/`, `tmp*.json` and `__pycache__` are untracked and ignored; `pytest.ini` sets `testpaths = tests` (P7). |
| App: paths (P1) | `app/paths.py`; static files and `index.html` resolve from the package, not the working directory. |
| App: Docker defaults (D1, D2, D6) | `REDIS_URL` defaults to `127.0.0.1`; `BACKUP_DIR` defaults to `backups`; the legacy SQLite path defaults to the project's `data/`. Compose always sets these explicitly, so Docker behaviour is unchanged. |
| App: Windows export (P6) | `export_storage` checks privacy on Windows through the per-user temp location and rejects reparse points, instead of using POSIX mode bits. |
| App: security (S1) | `local_user` refuses to start without `SECRET_KEY`. |
| App: nginx parity | `MAX_REQUEST_BODY_BYTES` (set to 2 MiB by the runtime) returns 413 like `client_max_body_size 2m`. It is inactive unless set. |
| Runtime | `sharakat_runtime/` package: per-OS home (`home.py`), generated settings and app environment (`config.py`), pinned SHA-256-verified downloads (`downloads.py`), process primitives (`procs.py`), PostgreSQL provider (`postgres.py`), Redis/Garnet provider (`redis_server.py`), command lines (`services.py`), supervisor (`supervisor.py`), CLI (`cli.py`), start-at-login (`autostart.py`). |
| Launchers | `.bat` files keep their names and now call `scripts/native/bootstrap.ps1`; `sharakat.sh` and `*.command` call `scripts/native/bootstrap.sh`. |
| Data migration | `install` restores the transfer package it runs from (or the newest under `transfer/`), verifies the dump's SHA-256 and compares the stable business counts with `expected-data-manifest.json`, discarding the restore on mismatch. `export-transfer` writes the same package format natively. |
| Tests | `tests/test_native_runtime.py` (19 tests); `scripts/native/smoke_test.py` (real install/start/login/export/restart/stop); CI job `native-runtime` on Ubuntu, Windows and macOS. |
| Docs | `docs/runbooks/native-runtime.md`; README, START-HERE.txt and PORTABLE-SETUP-README.md updated. |

Behaviour choices made to keep parity with the Docker stack:

* PostgreSQL is initialised with `--locale=C`, UTF-8 and `timezone = 'UTC'`. This matches `postgres:16-alpine` (musl has no locale collation; the container ran in UTC), so ordering and date rendering don't change.
* The worker consumes exactly `source_sync,maintenance,notifications`, as in Compose. This is asserted by a test against `docker-compose.yml`.
* The national UI/map/dashboard flags default to `true`, as in `docker-compose.local.yml`.
* uvicorn runs with `--no-proxy-headers`. With no proxy in front, trusting `X-Forwarded-For` would let any local process spoof its address and get around the per-client rate limits.

Test results on the assessment machine (Windows 11, Python 3.11): **792 passed, 11 failed, 7 errors**, against the baseline of 753/32/7. None of the remaining failures are platform-related:

* 6 are stale `test_dashboard_video_hero` assertions.
* 4 NCP tests need `pytest-asyncio`, which isn't in `requirements.txt`.
* 1 `test_ingestion` case depends on the date: its fixture deadline is now in the past.
* 7 errors come from document tests that require a disposable PostgreSQL database.

### 9.1 Verification on Windows 11 (2026-11-22)

Both runs used isolated `SHARAKAT_HOME` folders and private ports, with no Docker installed.

**Smoke test** (`scripts/native/smoke_test.py`, empty database): **passed.** The cycle was install → start → `health/ready` (database, redis and worker all ok) → UI and `/static` → admin login → XLSX export → `verify` → stop → start → stop. `verify` showed the worker answering `ping` over Garnet, migrations at head `0028`, and PostgreSQL, Garnet and the UI not reachable from the LAN address.

**Restore of real data** (newest package, `portable-package-20261028T145109-95ad0509`): the dump checksum was verified and the stable business counts matched `expected-data-manifest.json` (587 masters of which 566 current and 21 merged, 21 merge-lineage records, 2 users, 28,761 observations). Migrations then upgraded it from `0023` to `0028`, and the platform became ready. Data-quality gates came out at 129 pass, 4 warning and 1 fail. The failing gate is `SOURCE_LAST_SUCCESS_TOO_OLD`, which is expected for a 25-day-old snapshot that hasn't synced since.

Defects found and fixed by these runs:

1. **Garnet startup.** `--logdir` is only valid together with `--storage-tier`, so it was removed.
2. **Migrations on a clean PostgreSQL database.** `0022`, `0024`, `0025` and `0028` weren't guarded, unlike `0014`–`0021`. `migrations/env.py` builds the current schema before replaying from `0013`, so a clean `alembic upgrade head` failed at `0022` with a duplicate column. This also affects the CI "Clean PostgreSQL migration" step. The four migrations now skip objects that already exist. They behave exactly as before on databases that don't have those objects.
3. **Garnet with kombu 5.7.** When pidbox or event queues have `x-expires`, kombu refreshes binding tables with a Lua script inside `MULTI`/`EXEC`, and Garnet never answers it. That hung worker start-up at `mingle` and every control broadcast. Plain `EVAL` inside `MULTI` does work on Garnet. Fix: `CELERY_DISABLE_QUEUE_EXPIRY=1`, set by the runtime only when the broker is Garnet, which clears `control_queue_expires` and `event_queue_expires`. Docker and native Redis are unchanged.

Still to run: the CI `native-runtime` matrix on Linux and macOS. It hasn't been pushed, by request.

### 9.2 Server mode (2026-11-22)

The native runtime now serves as a server on any OS. Configuration is done with the `server` command and is
validated before it's saved. Guide: [server.md](../runbooks/server.md).

* **`internal`:** LAN over HTTP. The app runs as `local_user` and listens on all interfaces.
* **`staging` / `production`:** HTTPS, either served by uvicorn from PEM files or behind a named reverse proxy
  (`--proxy-headers` trusting only `FORWARDED_ALLOW_IPS`). The app runs with its full protected-environment
  hardening.
* **External databases:** an optional `EXTERNAL_DATABASE_URL` / `EXTERNAL_REDIS_URL`. The runtime then doesn't
  start its own PostgreSQL or Redis, and restore, transfer and backup use the given URL.
* **Start at boot:** `service install --at-boot` installs a Task Scheduler start-up task on Windows, a systemd
  system unit on Linux, or a LaunchDaemon on macOS, all running as the service account.

Verified on Windows 11 in production mode, with a self-signed certificate on an isolated home. These checks passed:

* HTTPS `health/ready` with the certificate verified against the hostname
* HSTS header
* UI over HTTPS
* admin login, with the session cookie `Secure` and `HttpOnly`
* XLSX export
* plain HTTP refused on the HTTPS port
* `verify`: worker ping, and PostgreSQL and Redis not exposed

Not yet exercised on real hardware: Linux and macOS start-at-boot, a LAN-facing `internal` server with a firewall
rule, and external database or Redis services.
