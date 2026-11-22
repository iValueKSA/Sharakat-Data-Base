# Al-Ahsa Investment Opportunities Intelligence Platform

An Arabic-first platform that tracks investment opportunities in Al-Ahsa Governorate and traces every record back to
its public source. It collects from ten public-source adapters: Furas, Al-Ahsa Investment Opportunities Platform,
AHDA, Invest Saudi, KFU, MODON, NCP, NHC, PIF Private Sector Hub and MWAN. Gaps in what a source publishes are
recorded separately from the technical health of its collector.

The platform runs **natively on Windows, Linux and macOS**. Docker isn't used or needed.

## Quick start

| OS | First time | Every day |
|---|---|---|
| Windows 10/11 / Server | Double-click **Install Platform Requirements.bat** | **Start Platform.bat** / **Stop Platform.bat** |
| macOS | Double-click **Install Platform.command** | **Start Platform.command** / **Stop Platform.command** |
| Linux | `bash sharakat.sh install` | `bash sharakat.sh start` / `bash sharakat.sh stop` |

The first run takes about 10–15 minutes and needs an internet connection. It installs, for the current user only:

* Python 3.12
* PostgreSQL 16
* a Redis-protocol server: Redis or Valkey on Linux and macOS, Microsoft Garnet with a private .NET 10 runtime on
  Windows

Every download is pinned and checked against its SHA-256. On Windows and macOS no administrator rights are needed;
on Linux `sudo` is used only for distribution packages.

The installer loads data once, into an empty database only. It uses, in order of preference:

1. a backup passed with `--restore`
2. the transfer package it's run from, or the newest one under `transfer/`, after checking its checksum and
   comparing record counts
3. the legacy `data/al-ahsa-live.db`
4. otherwise, an empty database

It then opens **http://localhost:8080**.

Everything the platform owns lives outside the project folder:

| OS | Location |
|---|---|
| Windows | `%LOCALAPPDATA%\Sharakat` |
| macOS | `~/Library/Application Support/Sharakat` |
| Linux | `~/.local/share/sharakat` |

That folder holds the database, logs, backups and generated secrets. Nothing in it is ever committed to git.

**Signing in:** `Local Admin Credentials.txt` in the project folder has the local administrator account. If the
restored data already contained that account, it keeps its password from the previous computer. Run
`reset-admin-password` to set a new one.

## Everyday commands

Run them through the launchers. On Windows use `scripts\native\bootstrap.ps1 <command>`, or the `.bat` files for
the common ones. On Linux and macOS use `bash sharakat.sh <command>`.

| Command | What it does |
|---|---|
| `start` / `stop` / `restart` | Start or stop all services. Running jobs finish first, and data is kept. |
| `status` | Mode, address, and the state of each component |
| `verify` | Read-only checks: health, worker, migrations, data quality, network exposure |
| `doctor` | Checks the machine's prerequisites and free ports |
| `backup` / `restore <file.dump>` | Immediate backup, or restore into an empty installation. A daily backup also runs automatically. |
| `export-transfer` | Package the platform and its data to move to another computer (**Prepare Transfer.bat**) |
| `reset-admin-password` | Generate a new password for the local administrator |
| `logs [api\|worker\|scheduler\|redis\|postgres\|supervisor]` | Show the end of a log |

Full reference, configuration and troubleshooting: [native runtime runbook](docs/runbooks/native-runtime.md).

## Running on a server

The same installation becomes a server with one command. It works on Windows Server, Linux and macOS.

| Setup | Command |
|---|---|
| Office or intranet (HTTP on the LAN) | `server --mode internal --public-url http://srv-name:8080` |
| Production, HTTPS served by the platform | `server --mode production --public-url https://platform.example.org --tls-cert cert.pem --tls-key key.pem` |
| Production behind IIS, nginx or a load balancer | `server --mode production --public-url https://... --behind-proxy --trusted-proxies <proxy IP>` |
| Use existing PostgreSQL or Redis services | `server --database-url postgresql://... --redis-url redis://...` |
| Start when the server boots | `service install --at-boot` (administrator terminal, or `sudo`) |

`server` validates the settings before saving them and prints the firewall command for the OS. `staging` and
`production` turn on the application's hardening: Secure cookies, HSTS, and startup refusal of unsafe settings.
PostgreSQL and Redis always stay on `127.0.0.1`. Step-by-step guide: [server.md](docs/runbooks/server.md).

For a Linux fleet managed directly with systemd and nginx, see [deployment.md](docs/runbooks/deployment.md),
[`deploy/`](deploy) and [staging.md](docs/runbooks/staging.md).

## Moving to another computer

On the old computer, run **Prepare Transfer.bat** (`export-transfer`) and copy the
`transfer\portable-package-<id>` folder across. On the new computer, run the installer from inside that folder. It
restores the data, verifies the checksum and the record counts, then starts the platform. Packages made by the
earlier Docker-based release work too.

The package contains business data and password hashes. Keep it private and **never commit it**.

## Development

Requirements: Python 3.12+.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. This dev mode uses SQLite by default and doesn't start PostgreSQL, Redis or Celery.
The legacy `ADMIN_TOKEN` path exists only outside protected environments, for development compatibility. Installed
and server modes use provisioned users and HTTP-only sessions.

| Task | Command |
|---|---|
| Unit and integration tests | `pytest -q` (offline fixtures; `pytest.ini` limits collection to `tests/`) |
| Native runtime tests | `pytest -q tests/test_native_runtime.py` |
| End-to-end check of the runtime on this machine | `python scripts/native/smoke_test.py`: install, start, login, export, restart and stop in a throwaway home on private ports |
| Lint (as CI) | `ruff check app migrations tests --select E9,F63,F7,F82` |

CI runs the test suite, a clean PostgreSQL migration, `pip-audit`, and the native runtime on Ubuntu, Windows and
macOS (see [`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

### Project layout

| Path | Contents |
|---|---|
| `app/` | FastAPI API, source adapters, data pipeline, Celery tasks; `app/static/` is the UI |
| `migrations/` | Alembic schema migrations |
| `sharakat_runtime/` | Native runtime: installer, PostgreSQL/Redis providers, supervisor, CLI, server mode |
| `scripts/native/` | OS launchers (`bootstrap.ps1`, `bootstrap.sh`) and the smoke test |
| `deploy/` | systemd units and nginx configuration for Linux fleet deployments |
| `tests/` | Test suite |
| `docs/` | Architecture, runbooks, source analysis, validation evidence |

### Source of truth

Develop, test, migrate and prepare releases from one official checkout of this repository. Don't keep parallel copies
or worktrees that diverge. Disposable test databases are fine. See the
[single-source-of-truth record](docs/development/SINGLE-SOURCE-OF-TRUTH.md).

Never commit runtime state or data. The following are ignored, and must stay that way:

* `platform.env`
* `Local Admin Credentials.txt`
* `transfer/` and `tmp/`
* backups and database dumps

## Main endpoints

- `GET /api/dashboard`, `/api/opportunities`, `/api/sources`
- `GET /api/opportunities/{id}`: source links and change history
- `GET /api/export.csv`, `/api/export.xlsx`
- `POST /api/auth/login`, `/api/auth/logout`; `GET /api/auth/me`
- Admin operations under `/api/admin/`
- `GET /health/live`, `/health/ready`, `/metrics`

## Documentation

| Topic | Document |
|---|---|
| Workstation install, commands, configuration, troubleshooting | [docs/runbooks/native-runtime.md](docs/runbooks/native-runtime.md) |
| Servers on any OS | [docs/runbooks/server.md](docs/runbooks/server.md) |
| Linux fleet deployment (systemd + nginx) | [docs/runbooks/deployment.md](docs/runbooks/deployment.md) |
| Backup and restore | [docs/runbooks/database-restore.md](docs/runbooks/database-restore.md) |
| Architecture and the move away from Docker | [docs/architecture/cross-platform-assessment.md](docs/architecture/cross-platform-assessment.md), [production-architecture.md](docs/architecture/production-architecture.md) |
| Source collection decisions and coverage limits | `docs/source-analysis/`, `docs/validation/` |

Source adapters keep the existing qualification, normalization, location-evidence, duplicate-resolution,
provenance and historical-data rules.
