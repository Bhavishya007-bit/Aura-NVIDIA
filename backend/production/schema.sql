CREATE TABLE IF NOT EXISTS aura_deployment_control (
 id integer PRIMARY KEY CHECK(id=1), ai_enabled boolean NOT NULL DEFAULT TRUE,
 updated_at timestamptz NOT NULL DEFAULT NOW());
INSERT INTO aura_deployment_control(id) VALUES(1) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS aura_production_usage (
 day date NOT NULL, account integer NOT NULL, used_tokens bigint NOT NULL DEFAULT 0,
 reserved_tokens bigint NOT NULL DEFAULT 0, PRIMARY KEY(day,account));
-- account=0 is the deployment-wide budget; positive accounts are authenticated students.
CREATE TABLE IF NOT EXISTS aura_request_limits (
 bucket text NOT NULL, minute timestamptz NOT NULL, requests integer NOT NULL,
 PRIMARY KEY(bucket,minute));
CREATE TABLE IF NOT EXISTS aura_demo_accounts (
 student_id integer PRIMARY KEY REFERENCES students(student_id),
 seed_version integer NOT NULL DEFAULT 1, created_at timestamptz NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS aura_revoked_tokens (
 digest text PRIMARY KEY, expires_at timestamptz NOT NULL);
