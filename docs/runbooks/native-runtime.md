# Native runtime (no Docker): install, operate, recover

The platform runs directly on Windows 10/11, Linux and macOS. No Docker, WSL or
container runtime is used. The same code, UI, API and data model run as under
Docker Compose; only the hosting changed. Design and decisions:
[cross-platform assessment](../architecture/cross-platform-assessment.md).

## What runs

| Component | Native form | Replaces Compose service |
|---|---|---|
| PostgreSQL 16 | Private cluster in `<home>/pgdata`, `127.0.0.1:54329`, UTC, C collation | `db` |
| Redis protocol | `redis-server`/`valkey-server` (Linux/macOS) or Microsoft Garnet (Windows), `127.0.0.1:63790`, password, AOF | `redis` |
| API + UI | `uvicorn app.main:app` on `127.0.0.1:8080` (serves `app/static` directly) | `api` + `frontend` (nginx) |
| Worker | `celery worker --queues=source_sync,maintenance,notifications` (`--pool=threads` on Windows) | `worker` |
| Scheduler | `celery beat`, schedule file in `<home>/run` | `scheduler` |
| Migrations | `alembic upgrade head` on every start (`AUTO_MIGRATE=true`) | `migrate` |
| Supervisor | `python -m sharakat_runtime supervise`: ordered start, restart on crash, graceful stop | `depends_on` + `restart` |

`<home>` (all runtime state; override with `SHARAKAT_HOME`):

* Windows: `%LOCALAPPDATA%\Sharakat`
* macOS: `~/Library/Application Support/Sharakat`
* Linux: `${XDG_DATA_HOME:-~/.local/share}/sharakat`

Inside it: `config/platform.env` (generated secrets, owner-only permissions), `venv/`, `runtime/` (downloaded
binaries), `pgdata/`, `redis/`, `backups/`, `attachments/`, `logs/`, `run/`.

## Install and start

Requirements: an internet connection on first install, about 5 GB of free disk space, and a normal user account.
Administrator rights aren't needed on Windows or macOS. On Linux, `sudo` is used only to install distribution
packages.

| OS | First time | Every time |
|---|---|---|
| Windows | Double-click **Install Platform Requirements.bat** (or **Start Platform.bat**, which installs on first use) | **Start Platform.bat** / **Stop Platform.bat** |
| macOS | Double-click **Install Platform.command** (if blocked: right-click → Open) | **Start Platform.command** / **Stop Platform.command** |
| Linux | `bash sharakat.sh install` | `bash sharakat.sh start` / `bash sharakat.sh stop` |

The installer (`scripts/native/bootstrap.*` and then `python -m sharakat_runtime install`):

1. Finds or installs Python 3.12. Windows: winget, or the pinned python.org installer with its SHA-256 checked.
   macOS: Homebrew. Linux: apt/dnf.
2. Creates a private virtual environment and installs `requirements.txt`. This is repeated whenever that file
   changes.
3. Provides PostgreSQL 16. Windows/macOS: the pinned EDB binaries, SHA-256 verified. Linux: the PGDG apt
   repository (with no system cluster created) or dnf. An existing PostgreSQL 16+ is reused if found, or set
   `PG_BIN`.
4. Provides the Redis-protocol server. Linux/macOS: `redis-server`/`valkey-server`, installed if missing.
   Windows: pinned Garnet plus a private .NET 10 runtime from Microsoft's official installer script.
5. Generates `platform.env` with fresh secrets and creates the cluster, role and database.
6. Loads the initial data **once, only into an empty database**, choosing in this order:
   1. `install --restore <file.dump>`
   2. the transfer package it runs from, or the newest one under `transfer/`, with its checksum checked and its
      record counts compared against `expected-data-manifest.json`
   3. the legacy `data/al-ahsa-live.db` (`install --import-sqlite` forces this)
   4. an empty database (`install --fresh`)
7. Writes `Local Admin Credentials.txt` to the project folder, then starts the platform and opens
   `http://localhost:8080`.

Re-running the installer is safe. It reuses settings, binaries and the database, and never overwrites data.

## Daily operation

All commands work the same on every OS. On Windows use `scripts\native\bootstrap.ps1 <command>` or the `.bat`
files; on Linux/macOS use `bash sharakat.sh <command>`.

| Command | Purpose |
|---|---|
| `start` / `stop` / `restart` | Start, or stop gracefully. `stop` lets running jobs finish for up to 2 minutes. Data is kept. |
| `status` (`--json`) | Components and `/health/ready` |
| `verify` | Read-only checks: health, worker ping, migrations at head, admin account, data-quality gates, DB/Redis not exposed on the network. Report saved in `logs/`. |
| `doctor` | Machine prerequisites, free ports, installed binaries |
| `logs [api\|worker\|scheduler\|redis\|postgres\|supervisor\|migrations]` | Last lines of a log |
| `backup` | Immediate `pg_dump` backup into `<home>/backups` (the daily automatic backup still runs) |
| `restore <file.dump>` | Restore into an empty installation (platform stopped) |
| `export-transfer` | Package for another computer (**Prepare Transfer.bat**) |
| `reset-admin-password [--email]` | Generates a new password for the local admin account and writes it to `Local Admin Credentials.txt`. It signs out that account's sessions and records the reset in the audit trail. Needed when restored data already contained `admin@local`: the restore keeps that account's password from the old computer. |
| `service install` / `service uninstall` | Start at login: Task Scheduler (Windows), systemd `--user` (Linux), launchd agent (macOS) |
| `service install --at-boot` | Start when the server boots, before anyone signs in. See [server.md](server.md). |
| `server [--mode internal\|staging\|production\|off] ...` | Show or configure server mode: network address, HTTPS, reverse proxy, external PostgreSQL or Redis. See [server.md](server.md). |

## Configuration

Edit `<home>/config/platform.env`, then restart. Keys:

* `UI_PORT` (8080), `POSTGRES_PORT` (54329), `REDIS_PORT` (63790)
* `NATIONAL_UI_ENABLED`, `NATIONAL_MAP_ENABLED`, `NATIONAL_DASHBOARD_ENABLED` (default `true`, as in the Docker local
  stack), `RCU_SCHEDULED_SYNC_ENABLED`
* `WORKER_CONCURRENCY` (4), `AUTO_MIGRATE` (`true`), `REDIS_ENGINE` (`auto`, `redis` or `garnet`), `PG_BIN`,
  `GARNET_EXTRA_ARGS`
* Optional application settings passed through unchanged: `SMTP_*`, `ALERT_RECIPIENTS`, `BACKUP_RETAIN_*`,
  `SOURCE_JOB_*`, `DOCUMENT_COLLECTION_*`, `FURAS_NATIONAL_*` and the others listed in `sharakat_runtime/config.py`

Never commit or share `platform.env`.

## Moving from the Docker installation

1. On the computer that still runs Docker: **Prepare Transfer.bat** from the *previous* release, or use an existing
   `transfer\portable-package-*` folder.
2. On the target computer, run the installer from this release. It restores the newest package automatically,
   verifies its SHA-256 and compares the business counts with the package's `expected-data-manifest.json`. If the
   counts differ, the restore is discarded and the installer stops.
3. Sign in with the existing accounts. Password hashes are part of the data. Existing browser sessions end,
   because the native install has its own session key.
4. Once `verify` passes, Docker Desktop is no longer needed on this computer.

## Troubleshooting

| Symptom | Check / fix |
|---|---|
| `Port … already in use` | Another program uses it: change the port in `platform.env` or stop that program. `doctor` lists the ports. |
| Start fails at PostgreSQL | `logs/postgres.log`. "created by PostgreSQL N": the binaries changed major version; set `PG_BIN` to version N. |
| Redis fails on Windows | `logs/redis.log`, `logs/dotnet-install.log`. Run the installer again to repair the Garnet/.NET files. |
| Worker not ready (`health/ready` 503) | `logs/worker.log`; `verify` shows the worker ping. |
| A component keeps restarting | `status` shows "failed"; read its log, fix it, then `restart`. |
| Supervisor crashed | `stop` cleans up the processes left behind (PID files in `run/`), then `start`. |

## Windows notes

* Celery runs with `--pool=threads`. The hard task time limit isn't enforced on Windows; jobs stuck beyond the
  limit are reclaimed by the existing `recover_stale_jobs` schedule (every 5 minutes).
* Closing the launcher window doesn't stop the platform. Use **Stop Platform.bat**.
