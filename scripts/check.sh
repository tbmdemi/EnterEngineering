#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

if [ ! -x .venv/bin/python ]; then
  echo "Missing .venv. Run the dependency installation steps in README.md first." >&2
  exit 1
fi

export DATABASE_URL="${ENCOUNTER_TEST_DATABASE_URL:-postgresql://careguard:careguard@localhost:5432/careguard?connect_timeout=5}"
export ENCOUNTER_TEST_DATABASE_URL="$DATABASE_URL"
export MIGRATION_DIR="db/migrations"
export AI_MODE="fixture"
CONFIGURED_DEMO_ACCESS_TOKEN="${DEMO_ACCESS_TOKEN:-}"
unset DEMO_ACCESS_TOKEN
echo "==> Start PostgreSQL and apply migrations"
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db migrate

echo "==> Backend, HTTP contract and PostgreSQL integration tests"
.venv/bin/python -m unittest discover -s tests -v

echo "==> Compile backend"
.venv/bin/python -m compileall -q backend

echo "==> Validate Compose configurations"
docker compose -f docker-compose.yml -f docker-compose.dev.yml config --quiet
export APP_DOMAIN="${APP_DOMAIN:-demo.example.com}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-local-check-only}"
export DEMO_ACCESS_TOKEN="${CONFIGURED_DEMO_ACCESS_TOKEN:-local-check-only}"
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet

echo "==> Build frontend"
(cd frontend && npm run build)

echo "All demo checks passed."
