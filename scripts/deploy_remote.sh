#!/usr/bin/env bash
set -euo pipefail

# Muratorium production deploy script.
# Expected flow:
# 1) git clone ...
# 2) create and fill .env
# 3) run this script from repo root

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed or not in PATH."
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Error: docker compose is not available."
  exit 1
fi

if [[ ! -f ".env" ]]; then
  echo "Error: .env not found in $ROOT_DIR"
  echo "Create it first (you can start from .env.example)."
  exit 1
fi

required_vars=(
  DATABASE_URL
  REDIS_URL
  OPENAI_API_KEY
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHANNEL_ID
)

for key in "${required_vars[@]}"; do
  value="$(grep -E "^${key}=" .env | head -n1 | cut -d'=' -f2- || true)"
  if [[ -z "${value}" ]]; then
    echo "Error: ${key} is empty or missing in .env"
    exit 1
  fi
done

echo "[1/5] Starting db and redis..."
docker compose up -d db redis

echo "[2/5] Waiting for postgres readiness..."
max_attempts=30
for ((i=1; i<=max_attempts; i++)); do
  if docker compose exec -T db pg_isready -U muratorium -d muratorium >/dev/null 2>&1; then
    break
  fi
  if [[ "$i" -eq "$max_attempts" ]]; then
    echo "Error: postgres is not ready after waiting."
    exit 1
  fi
  sleep 2
done

echo "[3/5] Running Alembic migrations..."
docker compose run --rm api alembic upgrade head

echo "[4/5] Building and starting api, worker, beat..."
docker compose up -d --build api worker beat

echo "[5/5] Service status:"
docker compose ps

echo "Recent worker logs:"
docker compose logs --tail=40 worker

echo "Recent beat logs:"
docker compose logs --tail=40 beat

echo "Deploy completed."
