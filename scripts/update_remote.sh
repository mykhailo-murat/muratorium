#!/usr/bin/env bash
set -euo pipefail

# Muratorium production update script.
# Expected to run on already deployed server from repo root.
# Usage:
#   bash scripts/update_remote.sh
#   bash scripts/update_remote.sh master

BRANCH="${1:-master}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v git >/dev/null 2>&1; then
  echo "Error: git is not installed or not in PATH."
  exit 1
fi

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
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Error: working tree is not clean. Commit/stash local changes first."
  exit 1
fi

echo "[1/6] Fetching latest changes..."
git fetch origin

echo "[2/6] Switching to branch: ${BRANCH}"
git checkout "$BRANCH"

echo "[3/6] Pulling latest commit (fast-forward only)..."
git pull --ff-only origin "$BRANCH"

echo "[4/6] Ensuring db and redis are running..."
docker compose up -d db redis

echo "[5/6] Applying DB migrations..."
docker compose run --rm api alembic upgrade head

echo "[6/6] Rebuilding and restarting app services..."
docker compose up -d --build api worker beat

echo "Service status:"
docker compose ps

echo "Recent worker logs:"
docker compose logs --tail=30 worker

echo "Recent beat logs:"
docker compose logs --tail=30 beat

echo "Update completed."
