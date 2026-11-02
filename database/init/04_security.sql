-- 04_security.sql
-- Creates the read-only database role that the MCP server will use.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_analyst') THEN
        CREATE ROLE ai_analyst LOGIN PASSWORD 'ai_analyst_readonly';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE ai_analyst TO ai_analyst;
GRANT USAGE ON SCHEMA public TO ai_analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ai_analyst;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO ai_analyst;

-- Explicitly keep this role read-only at the session level.
ALTER ROLE ai_analyst SET default_transaction_read_only = on;
