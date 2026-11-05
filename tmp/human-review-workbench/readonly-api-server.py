"""Temporary current-code API for read-only live PostgreSQL performance checks."""
from sqlalchemy import event
from app.database import engine

if engine.dialect.name != "postgresql":
    raise RuntimeError("Expected the live PostgreSQL connection for this read-only server.")

@event.listens_for(engine, "connect")
def force_read_only(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("SET default_transaction_read_only = on")
    cursor.close()

import app.main as main

# Avoid startup DDL or source seeding; this temporary process serves GET requests only.
main.init_db = lambda: None
main.seed_sources = lambda _db: None

import uvicorn
uvicorn.run(main.app, host="0.0.0.0", port=8000, log_level="warning")
