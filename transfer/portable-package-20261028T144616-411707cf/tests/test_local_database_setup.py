import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import Column, Boolean, DateTime, Integer, JSON

from scripts.local_database_setup import convert_sqlite_value, import_local_data


def test_sqlite_import_converts_postgres_boolean_json_and_datetime():
    assert convert_sqlite_value(1, Column("enabled", Boolean)) is True
    assert convert_sqlite_value(0, Column("enabled", Boolean)) is False
    assert convert_sqlite_value('{"ar":"فرصة"}', Column("payload", JSON)) == {"ar":"فرصة"}
    value=convert_sqlite_value("2026-10-13T10:00:00+00:00", Column("created_at", DateTime(timezone=True)))
    assert value==datetime(2026,10,13,10,0,tzinfo=timezone.utc)


def test_local_import_refuses_production_or_wrong_database_before_connecting(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT","production")
    monkeypatch.setenv("DATABASE_URL","postgresql+psycopg://user:secret@db/sharakat_production")
    monkeypatch.setenv("LOCAL_EXPECTED_DATABASE","sharakat_local")
    with pytest.raises(RuntimeError,match="ENVIRONMENT must be local_user"):
        import_local_data()

    monkeypatch.setenv("ENVIRONMENT","local_user")
    monkeypatch.setenv("DATABASE_URL","postgresql+psycopg://user:secret@db/sharakat_production")
    with pytest.raises(RuntimeError,match="target database must be sharakat_local"):
        import_local_data()
