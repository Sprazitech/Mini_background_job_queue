-- Run this in the Supabase SQL Editor after running dead_letter_queue.sql.
-- It raises an error if a required DLQ object is missing.

DO $$
DECLARE
    missing_tables TEXT;
    missing_columns TEXT;
    missing_indexes TEXT;
    missing_functions TEXT;
    missing_views TEXT;
    trigger_found BOOLEAN;
    rls_missing TEXT;
BEGIN
    SELECT string_agg(required_name, ', ' ORDER BY required_name)
    INTO missing_tables
    FROM (
        SELECT required_name
        FROM unnest(ARRAY['jobs', 'worker_heartbeat', 'dead_letter_queue']) AS required(required_name)
        WHERE to_regclass('public.' || required_name) IS NULL
    ) missing;

    IF missing_tables IS NOT NULL THEN
        RAISE EXCEPTION 'Missing required tables: %', missing_tables;
    END IF;

    SELECT string_agg(required_name, ', ' ORDER BY required_name)
    INTO missing_columns
    FROM (
        SELECT required_name
        FROM unnest(ARRAY['metadata', 'error_message', 'error_stack', 'worker_id']) AS required(required_name)
        WHERE NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'jobs'
              AND column_name = required_name
        )
    ) missing;

    IF missing_columns IS NOT NULL THEN
        RAISE EXCEPTION 'Missing jobs columns: %', missing_columns;
    END IF;

    SELECT string_agg(required_name, ', ' ORDER BY required_name)
    INTO missing_indexes
    FROM (
        SELECT required_name
        FROM unnest(ARRAY[
            'idx_dead_letter_archived_at',
            'idx_dead_letter_resolution_status',
            'idx_dead_letter_failure_category',
            'idx_dead_letter_original_job_id',
            'idx_dead_letter_created_at'
        ]) AS required(required_name)
        WHERE NOT EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname = required_name
        )
    ) missing;

    IF missing_indexes IS NOT NULL THEN
        RAISE EXCEPTION 'Missing DLQ indexes: %', missing_indexes;
    END IF;

    SELECT string_agg(required_name, ', ' ORDER BY required_name)
    INTO missing_functions
    FROM (
        SELECT required_name
        FROM unnest(ARRAY[
            'archive_to_dead_letter_queue',
            'update_dead_letter_updated_at'
        ]) AS required(required_name)
        WHERE NOT EXISTS (
            SELECT 1
            FROM pg_proc routine
            JOIN pg_namespace namespace_info
              ON namespace_info.oid = routine.pronamespace
            WHERE namespace_info.nspname = 'public'
              AND routine.proname = required_name
        )
        UNION ALL
        SELECT 'reprocess_dead_letter_entry(uuid,text)'
        WHERE to_regprocedure('public.reprocess_dead_letter_entry(uuid,text)') IS NULL
        UNION ALL
        SELECT 'get_dead_letter_stats(timestamptz,timestamptz)'
        WHERE to_regprocedure('public.get_dead_letter_stats(timestamptz,timestamptz)') IS NULL
    ) missing;

    IF missing_functions IS NOT NULL THEN
        RAISE EXCEPTION 'Missing DLQ functions: %', missing_functions;
    END IF;

    SELECT string_agg(required_name, ', ' ORDER BY required_name)
    INTO missing_views
    FROM (
        SELECT required_name
        FROM unnest(ARRAY[
            'recent_dead_letter_entries',
            'unresolved_dead_letter_entries'
        ]) AS required(required_name)
        WHERE to_regclass('public.' || required_name) IS NULL
    ) missing;

    IF missing_views IS NOT NULL THEN
        RAISE EXCEPTION 'Missing DLQ views: %', missing_views;
    END IF;

    SELECT EXISTS (
        SELECT 1
        FROM pg_trigger trigger_info
        JOIN pg_class table_info ON table_info.oid = trigger_info.tgrelid
        JOIN pg_namespace namespace_info ON namespace_info.oid = table_info.relnamespace
        WHERE namespace_info.nspname = 'public'
          AND table_info.relname = 'jobs'
          AND NOT trigger_info.tgisinternal
          AND trigger_info.tgname = 'archive_failed_job_trigger'
    ) INTO trigger_found;

    IF NOT trigger_found THEN
        RAISE EXCEPTION 'Missing trigger: archive_failed_job_trigger';
    END IF;

    SELECT string_agg(required_name, ', ' ORDER BY required_name)
    INTO rls_missing
    FROM (
        SELECT required_name
        FROM unnest(ARRAY['jobs', 'worker_heartbeat', 'dead_letter_queue']) AS required(required_name)
        WHERE NOT EXISTS (
            SELECT 1
            FROM pg_class table_info
            JOIN pg_namespace namespace_info ON namespace_info.oid = table_info.relnamespace
            WHERE namespace_info.nspname = 'public'
              AND table_info.relname = required_name
              AND table_info.relrowsecurity
        )
    ) missing;

    IF rls_missing IS NOT NULL THEN
        RAISE EXCEPTION 'RLS is not enabled on: %', rls_missing;
    END IF;

    RAISE NOTICE 'Dead-letter queue schema verification passed';
END;
$$;

-- Review the resulting security configuration.
SELECT schemaname, tablename, policyname, roles, cmd
FROM pg_policies
WHERE tablename IN ('jobs', 'worker_heartbeat', 'dead_letter_queue')
ORDER BY tablename, policyname;

SELECT relname AS table_name, relrowsecurity AS rls_enabled,
       relforcerowsecurity AS rls_forced
FROM pg_class
WHERE relname IN ('jobs', 'worker_heartbeat', 'dead_letter_queue')
ORDER BY relname;
