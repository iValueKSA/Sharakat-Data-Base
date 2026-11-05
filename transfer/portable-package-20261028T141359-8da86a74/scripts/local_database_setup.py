"""Safely import the current SQLite workspace into a new local PostgreSQL DB.

The import is one-time and transactional. It refuses non-local environments,
unexpected database names, a non-empty target, or a partial prior setup.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.types import Boolean, DateTime, JSON


def convert_sqlite_value(value, column):
    if value is None:
        return None
    if isinstance(column.type, JSON) and isinstance(value, (str, bytes, bytearray)):
        return json.loads(value)
    if isinstance(column.type, DateTime) and isinstance(value, str):
        normalized = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return value
    if isinstance(column.type, Boolean):
        return bool(value)
    return value


def _sqlite_backup(source_path: Path, backup_dir: Path) -> dict:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = backup_dir / f"pre-postgres-import-{stamp}.sqlite"
    source = sqlite3.connect(f"file:{source_path.resolve()}?mode=ro", uri=True)
    target = sqlite3.connect(output)
    try:
        source.backup(target)
        integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError("Safety copy failed SQLite integrity check")
    finally:
        source.close()
        target.close()
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": source_path.name,
        "file": output.name,
        "size_bytes": output.stat().st_size,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "integrity_check": integrity,
    }
    output.with_suffix(".json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _source_counts(connection, tables: set[str]) -> dict[str, int]:
    return {
        table: int(connection.execute(text(f'SELECT COUNT(*) FROM "{table}"')).fetchone()[0])
        for table in sorted(tables)
    }


def import_local_data() -> dict:
    if os.getenv("ENVIRONMENT", "").lower() != "local_user":
        raise RuntimeError("Refusing local import: ENVIRONMENT must be local_user")
    url = os.getenv("DATABASE_URL", "")
    expected_database = os.getenv("LOCAL_EXPECTED_DATABASE", "")
    from sqlalchemy.engine import make_url
    parsed = make_url(url)
    if not url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise RuntimeError("Refusing local import: target must be PostgreSQL")
    if expected_database != "sharakat_local" or parsed.database != expected_database:
        raise RuntimeError("Refusing local import: target database must be sharakat_local")

    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
    marker = os.getenv("LOCAL_SETUP_MARKER", "local_setup_state")
    sqlite_name = os.getenv("LOCAL_SQLITE_PATH", "/source-data/al-ahsa-live.db")
    source_path = Path(sqlite_name)
    source_exists = source_path.is_file()
    backup = None

    source_db = sqlite3.connect(f"file:{source_path.resolve()}?mode=ro", uri=True) if source_exists else None
    if source_db:
        source_db.row_factory = sqlite3.Row
        source_revision = source_db.execute("SELECT version_num FROM alembic_version").fetchone()
        if not source_revision or source_revision[0] not in (
            "0013_public_coverage_model",
            "0014_production_operations",
            "0015_source_method_text",
            "0016_source_type_text",
        ):
            source_db.close()
            raise RuntimeError("Existing SQLite database has an unsupported Alembic revision")
    source_tables = set()
    if source_db:
        source_tables = {
            row[0] for row in source_db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if row[0] != "alembic_version"
        }

    if not marker.replace("_", "").isalnum():
        raise RuntimeError("Invalid local setup marker name")
    with engine.begin() as connection:
        if connection.scalar(text("SELECT current_database()")) != expected_database:
            raise RuntimeError("Connected database does not match local database guard")
        connection.execute(text(
            f"CREATE TABLE IF NOT EXISTS {marker} (id INTEGER PRIMARY KEY, completed_at TIMESTAMPTZ NOT NULL, report JSONB NOT NULL)"
        ))
        existing = connection.execute(text(f"SELECT report FROM {marker} WHERE id=1")).scalar_one_or_none()
        if existing is not None:
            if source_db:
                source_db.close()
            return {"status": "ALREADY_IMPORTED", "report": existing}

        reflected = MetaData()
        reflected.reflect(bind=connection)
        common = source_tables.intersection(reflected.tables)
        target_business_tables = set(reflected.tables) - {"alembic_version", marker}
        existing_counts = _source_counts(connection, target_business_tables)
        if any(existing_counts.values()):
            raise RuntimeError("Target database has data but no local import marker; refusing to merge or overwrite")

        expected_revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        if expected_revision != "0016_source_type_text":
            raise RuntimeError("Target database must be migrated to 0016_source_type_text before import")

        if source_exists:
            backup = _sqlite_backup(source_path, Path(os.getenv("BACKUP_DIR", "/backups")))

        row_counts: dict[str, int] = {}
        pending_self_refs: list[tuple[str, str, int, int]] = []
        table_order = [name for name in reflected.sorted_tables if name.name in common]
        for target_table in table_order:
            name = target_table.name
            source_columns = {row[1] for row in source_db.execute(f'PRAGMA table_info("{name}")')}
            target_columns = [column for column in target_table.columns if column.name in source_columns]
            rows = source_db.execute(f'SELECT * FROM "{name}"').fetchall()
            values = []
            for row in rows:
                source_row = dict(row)
                item = {column.name: convert_sqlite_value(source_row[column.name], column) for column in target_columns}
                for column in target_table.columns:
                    if column.name not in item and column.name in ("job_state", "trigger_type", "attempt_number", "heartbeat_at") and name == "source_sync_jobs":
                        status = str(source_row.get("status", "")).upper()
                        item["job_state"] = {"SUCCESS":"COMPLETED", "FAILED":"FAILED", "QUEUED":"QUEUED", "RETRYING":"RETRYING", "CANCELLED":"CANCELLED", "RUNNING":"ABANDONED"}.get(status, "COMPLETED_WITH_WARNINGS")
                        item["trigger_type"] = "manual"
                        item["attempt_number"] = 1
                        item["heartbeat_at"] = item.get("finished_at") or item.get("started_at")
                        break
                for fk in target_table.foreign_keys:
                    if fk.column.table.name == name and item.get(fk.parent.name) is not None:
                        pending_self_refs.append((name, fk.parent.name, int(item["id"]), int(item[fk.parent.name])))
                        item[fk.parent.name] = None
                values.append(item)
            for start in range(0, len(values), 500):
                connection.execute(target_table.insert(), values[start:start + 500])
            row_counts[name] = len(values)

        for name, column, row_id, target_id in pending_self_refs:
            connection.execute(text(f'UPDATE "{name}" SET "{column}"=:target WHERE id=:row_id'), {"target": target_id, "row_id": row_id})

        if not row_counts and source_exists:
            raise RuntimeError("SQLite data was present but no application tables could be imported")

        # Advance PostgreSQL sequences after preserving SQLite primary keys.
        for target_table in table_order:
            pk = list(target_table.primary_key.columns)
            if len(pk) == 1 and str(pk[0].type).upper().startswith("INTEGER"):
                sequence = connection.scalar(text(
                    "SELECT pg_get_serial_sequence(:table_name, :column_name)"),
                    {"table_name": target_table.name, "column_name": pk[0].name})
                if sequence:
                    max_id = connection.scalar(text(
                        f'SELECT MAX("{pk[0].name}") FROM "{target_table.name}"'))
                    connection.execute(text(
                        "SELECT setval(CAST(:sequence AS regclass), :value, :called)"),
                        {"sequence": sequence, "value": max_id or 1, "called": max_id is not None})

        user_count = connection.execute(text("SELECT COUNT(*) FROM users")).scalar_one()
        admin_created = user_count == 0
        if admin_created:
            from app.security import hash_password, utcnow
            from app.models import User
            email = os.environ["BOOTSTRAP_ADMIN_EMAIL"].strip().lower()
            password = os.environ["BOOTSTRAP_ADMIN_PASSWORD"]
            connection.execute(User.__table__.insert().values(
                email=email, display_name="Local Administrator", role="admin",
                password_hash=hash_password(password), is_active=True,
                failed_login_count=0, created_at=utcnow()))

        after_counts = _source_counts(connection, common) if common else {}
        for name, count in row_counts.items():
            expected_count = count + (1 if name == "users" and admin_created else 0)
            if after_counts.get(name) != expected_count:
                raise RuntimeError(f"PostgreSQL row count mismatch for {name}")
        report = {"source_database": source_path.name if source_exists else None,
                  "backup": backup, "imported_rows": row_counts,
                  "admin_created": admin_created,
                  "completed_at": datetime.now(timezone.utc).isoformat()}
        connection.execute(text(f"INSERT INTO {marker}(id,completed_at,report) VALUES(1,now(),:report)"), {"report": json.dumps(report)})
    if source_db:
        source_db.close()
    return {"status": "IMPORTED", "report": report}


if __name__ == "__main__":
    result = import_local_data()
    print(json.dumps(result, ensure_ascii=False, default=str))
