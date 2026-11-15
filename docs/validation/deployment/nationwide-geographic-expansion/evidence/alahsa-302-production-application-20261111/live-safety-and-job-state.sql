BEGIN READ ONLY;
SELECT table_name || ':' || string_agg(column_name, ',' ORDER BY ordinal_position)
FROM information_schema.columns
WHERE table_schema='public' AND table_name IN ('source_sync_jobs','source_identity_aliases','source_identity_alias_audits','opportunity_change_history','audit_events','system_settings') GROUP BY table_name ORDER BY table_name;
SELECT to_jsonb(j)::text FROM source_sync_jobs j ORDER BY j.id DESC LIMIT 5;
SELECT 'active_sync_jobs='||count(*) FROM source_sync_jobs WHERE status IN ('QUEUED','PENDING','RUNNING','RETRYING');
SELECT 'alias_count='||count(*) FROM source_identity_aliases;
SELECT 'alias_audit_count='||count(*) FROM source_identity_alias_audits;
COMMIT;