#!/usr/bin/env bash
set -euo pipefail
name="mw-db-test-$$"
trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT
docker run --name "$name" -e POSTGRES_PASSWORD=local-test-only -d postgres:17-alpine >/dev/null
for i in {1..30}; do
  # The image briefly starts a temporary server during initialization. Wait for
  # the final server so it cannot disappear between readiness and the SQL checks.
  if docker logs "$name" 2>&1 | grep -q 'PostgreSQL init process complete' &&
     docker exec "$name" pg_isready -U postgres >/dev/null 2>&1; then break; fi
  sleep 1
done
docker exec "$name" pg_isready -U postgres >/dev/null
docker exec -i "$name" psql -U postgres -v ON_ERROR_STOP=1 <<'SQL'
create role anon; create role authenticated;
create schema auth;
create table auth.users(id uuid primary key);
create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
grant usage on schema auth to anon,authenticated;
grant execute on function auth.uid() to anon,authenticated;
insert into auth.users values('11111111-1111-1111-1111-111111111111'),('22222222-2222-2222-2222-222222222222');
SQL
docker exec -i "$name" psql -U postgres -v ON_ERROR_STOP=1 < supabase/migrations/202609170001_cloud_lists.sql
docker exec -i "$name" psql -U postgres -v ON_ERROR_STOP=1 < supabase/security-tests.sql
