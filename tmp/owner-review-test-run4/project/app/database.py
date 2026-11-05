import os
from pathlib import Path
import time, logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from .models import Base

DATABASE_URL=os.getenv("DATABASE_URL","sqlite:///./data/al-ahsa-live.db")
logger=logging.getLogger("app.database")
if DATABASE_URL.startswith("sqlite"):
    Path("data").mkdir(exist_ok=True)
    engine=create_engine(DATABASE_URL,connect_args={"check_same_thread":False},pool_pre_ping=True)
else:
    engine=create_engine(DATABASE_URL,pool_pre_ping=True,pool_size=int(os.getenv("DB_POOL_SIZE","10")),max_overflow=int(os.getenv("DB_MAX_OVERFLOW","20")),pool_timeout=int(os.getenv("DB_POOL_TIMEOUT_SECONDS","30")))
SessionLocal=sessionmaker(bind=engine,expire_on_commit=False)

@event.listens_for(engine,"before_cursor_execute")
def _start_query_timer(conn,cursor,statement,parameters,context,executemany):
    context._query_started=time.perf_counter()

@event.listens_for(engine,"after_cursor_execute")
def _log_slow_query(conn,cursor,statement,parameters,context,executemany):
    elapsed=time.perf_counter()-getattr(context,"_query_started",time.perf_counter())
    if elapsed>=float(os.getenv("SLOW_QUERY_SECONDS","1.0")):
        logger.warning("slow_database_query",extra={"duration_seconds":round(elapsed,4),"statement":statement[:500]})

def init_db():
    Base.metadata.create_all(engine)
