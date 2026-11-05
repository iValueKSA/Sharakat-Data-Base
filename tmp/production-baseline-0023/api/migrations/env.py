import os
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from app.models import Base

config=context.config
if config.config_file_name: fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url",os.getenv("DATABASE_URL","sqlite:///./data/al-ahsa-live.db").replace("%","%%"))
target_metadata=Base.metadata

def run_migrations_offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"),target_metadata=target_metadata,literal_binds=True,dialect_opts={"paramstyle":"named"},compare_type=True)
    with context.begin_transaction(): context.run_migrations()

def run_migrations_online():
    connectable=engine_from_config(config.get_section(config.config_ini_section),prefix="sqlalchemy.",poolclass=pool.NullPool)
    with connectable.connect() as connection:
        # 0001_initial intentionally snapshots the then-current ORM metadata. The
        # repository later evolved that snapshot, so its historical chain cannot
        # be replayed against an empty database. Preserve existing databases and
        # use the latest pre-Phase-1 schema as the clean-install baseline.
        from sqlalchemy import inspect, text
        inspector=inspect(connection)
        if not inspector.get_table_names():
            Base.metadata.create_all(bind=connection)
            connection.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
            connection.execute(text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),{"revision":"0013_public_coverage_model"})
            connection.commit()
        context.configure(connection=connection,target_metadata=target_metadata,compare_type=True)
        with context.begin_transaction(): context.run_migrations()
        connection.commit()

run_migrations_offline() if context.is_offline_mode() else run_migrations_online()
