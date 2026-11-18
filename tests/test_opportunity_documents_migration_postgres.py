"""Destructive migration test, guarded to a named throwaway PostgreSQL container."""
import os
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


def _test_database_url():
    url = os.getenv("DOCUMENTS_TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("Set DOCUMENTS_TEST_DATABASE_URL to the isolated documents-mvp-pg-test container")
    parsed = urlparse(url)
    if (parsed.hostname != "documents-mvp-pg-test"
            or parsed.username != "documents_test"
            or parsed.path != "/documents_mvp_test"):
        raise RuntimeError("Refusing destructive migration test outside the named disposable PostgreSQL database")
    return url


def test_0027_upgrade_preserves_legacy_rows_enforces_gates_and_downgrades():
    url = _test_database_url()
    engine = create_engine(url)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    try:
        with engine.begin() as db:
            db.execute(text("DROP SCHEMA public CASCADE"))
            db.execute(text("CREATE SCHEMA public"))
            db.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            db.execute(text("INSERT INTO alembic_version(version_num) VALUES ('0026_source_identity_aliases')"))
            db.execute(text("CREATE TABLE sources (id INTEGER PRIMARY KEY, source_key VARCHAR(80) NOT NULL)"))
            db.execute(text("CREATE TABLE opportunities (id INTEGER PRIMARY KEY)"))
            db.execute(text("""
                CREATE TABLE source_opportunities (
                    id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id),
                    master_opportunity_id INTEGER REFERENCES opportunities(id),
                    source_opportunity_id VARCHAR(200) NOT NULL,
                    CONSTRAINT uq_source_opportunity_id_source_namespace UNIQUE(id, source_id)
                )
            """))
            db.execute(text("""
                CREATE TABLE opportunity_documents (
                    id INTEGER PRIMARY KEY, opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
                    source_id INTEGER NOT NULL REFERENCES sources(id), title VARCHAR(500) NOT NULL,
                    url VARCHAR(1200) NOT NULL, document_type VARCHAR(100),
                    first_seen_at TIMESTAMPTZ NOT NULL
                )
            """))
            db.execute(text("INSERT INTO sources(id,source_key) VALUES (1,'synthetic-test-source')"))
            db.execute(text("INSERT INTO opportunities(id) VALUES (1)"))
            db.execute(text("INSERT INTO source_opportunities(id,source_id,master_opportunity_id,source_opportunity_id) VALUES (10,1,1,'fixture-10')"))
            db.execute(text("INSERT INTO opportunity_documents(id,opportunity_id,source_id,title,url,document_type,first_seen_at) VALUES (7,1,1,'Legacy synthetic row','https://source.example.invalid/legacy','legacy-pdf',now())"))

        command.upgrade(config, "0027_opportunity_documents_mvp")
        with engine.begin() as db:
            version = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0027_opportunity_documents_mvp"
            legacy = db.execute(text("SELECT title,url,document_type,publication_status,access_status,source_opportunity_id FROM opportunity_documents WHERE id=7")).one()
            assert legacy.title == "Legacy synthetic row" and legacy.url.endswith("/legacy")
            assert legacy.document_type == "legacy-pdf" and legacy.publication_status == "DRAFT"
            assert legacy.access_status == "UNKNOWN" and legacy.source_opportunity_id is None
            insert_doc = text("""
                INSERT INTO opportunity_documents (
                    id,opportunity_id,source_id,source_opportunity_id,title,url,document_type,document_category,
                    first_seen_at,source_opportunity_url,access_status,rights_status,participation_requirement,
                authentication_required,payment_required_for_document,link_verification_status,last_verified_at,
                source_provenance_json,document_version,deduplication_key,
                    publication_status,created_at,updated_at
                ) VALUES (
                    8,1,1,10,'Synthetic approved booklet','https://source.example.invalid/booklet.pdf','pdf',
                    'TERMS_AND_CONDITIONS_BOOKLET',now(),'https://source.example.invalid/opportunity/10',
                    'PUBLIC_DIRECT_DOWNLOAD','DIRECT_LINK_APPROVED','PURCHASE_REQUIRED_FOR_PARTICIPATION',
                    false,false,'VERIFIED_PUBLIC',now(),'{}',1,:key,'APPROVED',now(),now()
                )
            """)
            db.execute(insert_doc, {"key": "a" * 64})
            with pytest.raises(IntegrityError):
                with db.begin_nested():
                    db.execute(text("""
                        INSERT INTO opportunity_documents (
                            id,opportunity_id,source_id,source_opportunity_id,title,url,first_seen_at,source_opportunity_url,
                            access_status,rights_status,participation_requirement,link_verification_status,
                            source_provenance_json,document_version,deduplication_key,publication_status,created_at,updated_at
                        ) VALUES (13,1,1,10,'Unknown security state','https://source.example.invalid/file',now(),
                            'https://source.example.invalid/opportunity/10','PUBLIC_DIRECT_DOWNLOAD','DIRECT_LINK_APPROVED',
                            'UNKNOWN','VERIFIED_PUBLIC','{}',1,:key,'APPROVED',now(),now())
                    """), {"key": "d" * 64})
            db.execute(text("""
                INSERT INTO opportunity_documents (
                    id,opportunity_id,source_id,source_opportunity_id,title,url,first_seen_at,source_opportunity_url,
                    access_status,rights_status,participation_requirement,authentication_required,payment_required_for_document,link_verification_status,
                    source_provenance_json,document_version,deduplication_key,publication_status,created_at,updated_at
                ) VALUES (9,1,1,10,'Second document','https://source.example.invalid/second.pdf',now(),
                    'https://source.example.invalid/opportunity/10','PUBLIC_DIRECT_DOWNLOAD','DIRECT_LINK_APPROVED',
                    'UNKNOWN',false,false,'VERIFIED_PUBLIC','{}',1,:key,'APPROVED',now(),now())
            """), {"key": "b" * 64})
            with pytest.raises(IntegrityError):
                with db.begin_nested():
                    db.execute(text("""
                        INSERT INTO opportunity_documents (
                            id,opportunity_id,source_id,source_opportunity_id,title,url,first_seen_at,source_opportunity_url,
                            access_status,rights_status,participation_requirement,link_verification_status,
                            source_provenance_json,document_version,deduplication_key,publication_status,created_at,updated_at
                        ) VALUES (10,1,1,10,'Restricted','https://source.example.invalid/restricted',now(),
                            'https://source.example.invalid/opportunity/10','RESTRICTED','RESTRICTED','UNKNOWN',
                            'VERIFIED_PUBLIC','{}',1,:key,'APPROVED',now(),now())
                    """), {"key": "c" * 64})
            with pytest.raises(IntegrityError):
                with db.begin_nested():
                    db.execute(text("""
                        INSERT INTO opportunity_documents (
                            id,opportunity_id,source_id,source_opportunity_id,title,url,document_type,document_category,
                            first_seen_at,source_opportunity_url,access_status,rights_status,participation_requirement,
                            link_verification_status,last_verified_at,source_provenance_json,document_version,deduplication_key,
                            publication_status,created_at,updated_at
                        ) VALUES (
                            12,1,1,10,'Duplicate key','https://source.example.invalid/duplicate.pdf','pdf',
                            'TERMS_AND_CONDITIONS_BOOKLET',now(),'https://source.example.invalid/opportunity/10',
                            'PUBLIC_DIRECT_DOWNLOAD','DIRECT_LINK_APPROVED','PURCHASE_REQUIRED_FOR_PARTICIPATION',
                            'VERIFIED_PUBLIC',now(),'{}',1,:key,'APPROVED',now(),now()
                        )
                    """), {"key": "a" * 64})
            with pytest.raises(IntegrityError):
                with db.begin_nested():
                    db.execute(text("""
                        INSERT INTO opportunity_documents (
                            id,opportunity_id,source_id,source_opportunity_id,title,url,first_seen_at,
                            publication_status,access_status,rights_status,participation_requirement,
                            link_verification_status,source_provenance_json,document_version,created_at,updated_at
                        ) VALUES (11,1,99,10,'Wrong source namespace','https://source.example.invalid/bad',now(),
                            'DRAFT','UNKNOWN','UNVERIFIED','UNKNOWN','UNVERIFIED','{}',1,now(),now())
                    """))
            # Running Alembic at the current head is a safe no-op.
            assert db.execute(text("SELECT count(*) FROM opportunity_documents")).scalar_one() == 3

        command.upgrade(config, "head")
        with engine.begin() as db:
            assert db.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0028_document_collection_engine"
            assert {"document_collection_runs","document_collection_candidates","document_verification_events"}.issubset(
                set(db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'")).scalars()))
            assert db.execute(text("SELECT count(*) FROM opportunity_documents")).scalar_one() == 3
        command.downgrade(config, "0026_source_identity_aliases")
        with engine.begin() as db:
            legacy = db.execute(text("SELECT title,url,document_type FROM opportunity_documents WHERE id=7")).one()
            assert legacy.title == "Legacy synthetic row" and legacy.document_type == "legacy-pdf"
            assert db.execute(text("SELECT count(*) FROM opportunity_documents")).scalar_one() == 3
        command.upgrade(config, "head")
        with engine.begin() as db:
            assert db.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0028_document_collection_engine"
            assert db.execute(text("SELECT count(*) FROM opportunity_documents")).scalar_one() == 3
            assert db.execute(text("SELECT count(*) FROM document_collection_candidates")).scalar_one() == 0
    finally:
        engine.dispose()
