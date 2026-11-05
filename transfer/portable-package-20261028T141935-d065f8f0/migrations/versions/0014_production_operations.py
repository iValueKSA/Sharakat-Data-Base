"""Production operations: sessions, audit, alerts and execution metadata.

Revision ID: 0014_production_operations
Revises: 0013_public_coverage_model
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_production_operations"
down_revision = "0013_public_coverage_model"
branch_labels = None
depends_on = None


def _columns(table):
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table):
    return {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}


def _add_columns(table, columns):
    missing=[column for column in columns if column.name not in _columns(table)]
    if missing:
        with op.batch_alter_table(table) as batch:
            for column in missing:batch.add_column(column)


def _index(name, table, columns, **options):
    if name not in _indexes(table):op.create_index(name,table,columns,if_not_exists=True,**options)


def upgrade():
    bind=op.get_bind()
    bind.execute(sa.text("UPDATE sources SET polling_frequency_minutes=720 WHERE source_key='modon' AND polling_frequency_minutes=360"))
    bind.execute(sa.text("UPDATE sources SET polling_frequency_minutes=720 WHERE source_key='pif' AND polling_frequency_minutes=1440"))

    _add_columns("source_sync_jobs",[
        sa.Column("job_state",sa.String(40),nullable=False,server_default="RUNNING"),
        sa.Column("trigger_type",sa.String(20),nullable=False,server_default="manual"),
        sa.Column("queued_at",sa.DateTime(timezone=True)),sa.Column("worker_id",sa.String(200)),
        sa.Column("heartbeat_at",sa.DateTime(timezone=True)),sa.Column("correlation_id",sa.String(100)),
        sa.Column("attempt_number",sa.Integer(),nullable=False,server_default="1"),sa.Column("celery_task_id",sa.String(100)),
    ])
    for name,column in (("ix_source_sync_jobs_job_state","job_state"),("ix_source_sync_jobs_correlation_id","correlation_id"),("ix_source_sync_jobs_celery_task_id","celery_task_id")):
        _index(name,"source_sync_jobs",[column])

    _add_columns("users",[
        sa.Column("is_active",sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.Column("failed_login_count",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("locked_until",sa.DateTime(timezone=True)),sa.Column("last_login_at",sa.DateTime(timezone=True)),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
    ])

    bind.execute(sa.text("""
        UPDATE source_sync_jobs
        SET job_state = CASE
            WHEN status = 'SUCCESS' THEN 'COMPLETED'
            WHEN status = 'FAILED' THEN 'FAILED'
            WHEN status = 'QUEUED' THEN 'QUEUED'
            WHEN status = 'RETRYING' THEN 'RETRYING'
            WHEN status = 'CANCELLED' THEN 'CANCELLED'
            WHEN status = 'RUNNING' THEN 'ABANDONED'
            ELSE 'COMPLETED_WITH_WARNINGS'
        END,
        heartbeat_at = COALESCE(heartbeat_at, finished_at, started_at)
        WHERE job_state = 'RUNNING'
    """))

    tables=set(sa.inspect(bind).get_table_names())
    if "user_sessions" not in tables:
        op.create_table("user_sessions",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("user_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=False),sa.Column("token_hash",sa.String(64),nullable=False,unique=True),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),sa.Column("last_seen_at",sa.DateTime(timezone=True),nullable=False))
    for col in ("user_id","token_hash","expires_at"):_index(f"ix_user_sessions_{col}","user_sessions",[col],unique=(col=="token_hash"))

    if "audit_events" not in tables:
        op.create_table("audit_events",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("user_id",sa.Integer(),sa.ForeignKey("users.id")),sa.Column("event_type",sa.String(100),nullable=False),sa.Column("entity_type",sa.String(100)),sa.Column("entity_id",sa.String(200)),sa.Column("before_json",sa.JSON()),sa.Column("after_json",sa.JSON()),sa.Column("request_metadata",sa.JSON(),nullable=False,server_default="{}"),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    for col in ("user_id","event_type","created_at"):_index(f"ix_audit_events_{col}","audit_events",[col])

    if "alert_events" not in tables:
        op.create_table("alert_events",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("fingerprint",sa.String(64),nullable=False,unique=True),sa.Column("event_type",sa.String(100),nullable=False),sa.Column("severity",sa.String(20),nullable=False),sa.Column("source_id",sa.Integer(),sa.ForeignKey("sources.id")),sa.Column("payload",sa.JSON(),nullable=False,server_default="{}"),sa.Column("status",sa.String(20),nullable=False,server_default="OPEN"),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("acknowledged_by",sa.Integer(),sa.ForeignKey("users.id")),sa.Column("acknowledged_at",sa.DateTime(timezone=True)),sa.Column("resolved_at",sa.DateTime(timezone=True)),sa.Column("notification_state",sa.String(20),nullable=False,server_default="PENDING"),sa.Column("notification_error",sa.Text()))
    for col in ("fingerprint","event_type","severity","source_id","status","created_at"):_index(f"ix_alert_events_{col}","alert_events",[col],unique=(col=="fingerprint"))

    for table,column in (("opportunities","status"),("opportunities","sector"),("opportunities","submission_deadline"),("opportunities","created_at"),("opportunities","updated_at"),("source_opportunities","source_opportunity_id")):
        _index(f"ix_{table}_{column}_prod",table,[column])
    if bind.dialect.name=="postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        _index("ix_opportunities_title_trgm","opportunities",["normalized_title"],postgresql_using="gin",postgresql_ops={"normalized_title":"gin_trgm_ops"})


def downgrade():
    raise RuntimeError("Production operations migration is forward-only; use a forward fix to preserve job, audit, alert, and user history.")
