# Local Phase 1 infrastructure evidence

**Captured:** 2026-10-13 (Asia/Amman)  
**Environment:** Windows 11 Pro build 26300, x64; `C:\Sharakat Data Base`.

| Component | Result | Evidence |
|---|---|---|
| Docker Desktop | RUNNING, version 4.95.0 | Installed through verified WinGet package `Docker.DockerDesktop` |
| Docker Engine | RUNNING, 29.8.2 | Engine became ready after Docker Desktop was stopped and `Start Platform.bat` was run |
| Compose | RUNNING, v5.6.0 | Compose config, build, up, stop, and start completed |
| WSL | 3.0.3.0, default version 2 | Docker Desktop Linux engine uses WSL2 |
| PostgreSQL | RUNNING, 16.15 | Alembic head 0016; `pg_trgm` 1.6 |
| Redis | RUNNING, 7 | API readiness and Celery task/worker checks passed |
| Python suite | PASS | 104 tests |

WSL2 and the Docker Linux Engine operate on this host. WMI reports `HypervisorPresent=True` while firmware virtualization fields report false; the installer did not attempt a BIOS change.

The original SQLite database and existing pre-local-Postgres safety copy remain present and unchanged. The importer created its own integrity-checked safety copy before the one-time transaction. PostgreSQL is the active local application database.

Static application checks remain useful but are no longer the sole evidence: Compose, PostgreSQL, Redis, worker, Beat, real backup, isolated restore, and Windows launchers all executed locally. Internet-hosted TLS, external CI, and off-host disaster recovery were not part of this single-computer validation.
