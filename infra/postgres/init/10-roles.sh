#!/bin/sh
# Run automatically by the PostgreSQL image when the volume is created;
# for an existing database: docker compose -f infra/docker-compose.yml exec db sh /docker-entrypoint-initdb.d/10-roles.sh
set -e
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${SMARTCAMPUS_OWNER_PASSWORD:?SMARTCAMPUS_OWNER_PASSWORD is required}"
: "${SMARTCAMPUS_APP_PASSWORD:?SMARTCAMPUS_APP_PASSWORD is required}"
: "${SMARTCAMPUS_READONLY_PASSWORD:?SMARTCAMPUS_READONLY_PASSWORD is required}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v owner_password="$SMARTCAMPUS_OWNER_PASSWORD" \
  -v app_password="$SMARTCAMPUS_APP_PASSWORD" \
  -v readonly_password="$SMARTCAMPUS_READONLY_PASSWORD" \
  -v app_db="$POSTGRES_DB" \
  -f /docker-entrypoint-initdb.d/roles.psql
