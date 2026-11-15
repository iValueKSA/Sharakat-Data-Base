SELECT table_name || ':' || string_agg(column_name, ',' ORDER BY ordinal_position)
FROM information_schema.columns
WHERE table_schema='public' AND table_name IN ('opportunities','source_opportunities','source_observations','sources','geographic_reference_units','opportunity_data_conflicts','location_reviews')
GROUP BY table_name ORDER BY table_name;