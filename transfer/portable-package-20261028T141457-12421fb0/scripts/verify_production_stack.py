"""Read-only staging smoke check for the running production-like stack.

Run inside the API image after setting ENVIRONMENT=staging,
STAGING_DATABASE_NAME, DATABASE_URL, REDIS_URL, and API_BASE_URL.
This script never dispatches sync jobs or changes database rows.
"""
from __future__ import annotations

import os
import sys
import time
from urllib.request import urlopen

from sqlalchemy.engine import make_url


def main() -> int:
    if os.getenv("ENVIRONMENT", "").lower() != "staging":
        raise SystemExit("Refusing to run: ENVIRONMENT must be exactly 'staging'.")
    database_url = os.getenv("DATABASE_URL", "")
    expected_database = os.getenv("STAGING_DATABASE_NAME", "")
    parsed = make_url(database_url)
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise SystemExit("Refusing to run: DATABASE_URL must target PostgreSQL.")
    if not expected_database or parsed.database != expected_database:
        raise SystemExit("Refusing to run: database name must match STAGING_DATABASE_NAME.")
    if "prod" in expected_database.lower() and "staging" not in expected_database.lower():
        raise SystemExit("Refusing to run: expected database name looks like production.")

    results: list[tuple[str, bool, str]] = []

    def check(name: str, action) -> None:
        try:
            detail = action()
            results.append((name, True, str(detail)))
        except Exception as exc:  # report all checks before returning failure
            results.append((name, False, type(exc).__name__))

    def check_database() -> str:
        from sqlalchemy import create_engine, text

        engine = create_engine(database_url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
        try:
            with engine.connect() as connection:
                current = connection.scalar(text("SELECT current_database()"))
                revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
                if current != expected_database:
                    raise RuntimeError("connected database name mismatch")
                if revision != "0016_source_type_text":
                    raise RuntimeError("Alembic is not at 0016_source_type_text")
            return f"database={current}; alembic={revision}"
        finally:
            engine.dispose()

    def check_redis() -> str:
        import redis

        client = redis.Redis.from_url(os.environ["REDIS_URL"], socket_connect_timeout=3, socket_timeout=3)
        if not client.ping():
            raise RuntimeError("Redis ping failed")
        tick = client.get("scheduler:last_tick")
        if not tick:
            raise RuntimeError("scheduler tick has not been observed")
        age = time.time() - __import__("datetime").datetime.fromisoformat(tick).timestamp()
        if age > 180:
            raise RuntimeError("scheduler tick is stale")
        return f"ping=ok; scheduler_tick_age_seconds={int(age)}"

    def check_workers() -> str:
        from app.celery_app import celery_app

        nodes = celery_app.control.inspect(timeout=3).ping() or {}
        if not nodes:
            raise RuntimeError("no Celery workers responded")
        return f"workers={len(nodes)}"

    def check_api(path: str) -> str:
        base = os.getenv("API_BASE_URL", "http://api:8000").rstrip("/")
        with urlopen(f"{base}{path}", timeout=5) as response:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")
            return f"HTTP {response.status}"

    check("postgresql_migration", check_database)
    check("redis_and_beat_tick", check_redis)
    check("celery_workers", check_workers)
    check("api_live", lambda: check_api("/health/live"))
    check("api_ready", lambda: check_api("/health/ready"))

    for name, passed, detail in results:
        print(f"{'PASS' if passed else 'FAIL'} {name}: {detail}")
    return 0 if all(passed for _, passed, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
