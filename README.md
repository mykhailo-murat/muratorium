# Muratorium

Single-user news aggregation pipeline:
- ingest RSS sources
- deduplicate by source/external id + content hash
- score selected items with OpenAI in batches
- publish urgent items to Telegram immediately (fast lane)
- publish digest 2 times per day (slow lane)

## Quick start

1. Copy env template:
```powershell
Copy-Item .env.example .env
```

2. Start infrastructure:
```powershell
docker compose up -d db redis
```

3. Run DB migrations:
```powershell
docker compose run --rm api alembic upgrade head
```

4. Seed RSS sources:
```powershell
docker compose run --rm api python -m app.db.seed_sources --file sources.txt
```

5. Start services:
```powershell
docker compose up -d api worker beat
```

## Alembic

- config: `alembic.ini`
- migration env: `alembic/env.py`
- migrations: `alembic/versions`

Create a new migration:
```powershell
docker compose run --rm api alembic revision -m "describe change"
```

Apply migrations:
```powershell
docker compose run --rm api alembic upgrade head
```

## OpenAI scoring

Required env:
- `LLM_ENABLED=true`
- `OPENAI_API_KEY=...`
- optional: `OPENAI_MODEL`, `LLM_BATCH_SIZE`

Behavior:
- polling only ingests RSS items
- fast lane runs every `FAST_POLL_SECONDS`:
  - clusters repeated stories from multiple sources
  - scores clusters with LLM
  - publishes urgent clusters immediately (with idempotency + hourly rate limit)
- digest task analyzes items with OpenAI 2 times per day: 15:00 and 21:00 (Europe/Kyiv)
- strict JSON is validated; on invalid JSON one repair retry is performed
- if LLM is disabled/fails, auto-publish is skipped (safe mode)

### AI digest instruction

LLM receives candidates and must:
- evaluate each news item
- translate selected news to Ukrainian
- keep only news that is:
  - directly related to Ukraine, or
  - a global event with broad international impact
- exclude local/narrow stories without broad impact
- return only top items with score `70+/100` for publication

Run digest manually (test mode):
```powershell
docker compose exec -T worker celery -A app.workers.celery_app:celery call app.workers.tasks.analyze_and_publish_digest --kwargs='{"test_mode": true}'
```

Run fast lane manually:
```powershell
docker compose exec -T worker celery -A app.workers.celery_app:celery call app.workers.tasks.process_urgent_candidates
```

Backfill existing news into clusters (one-time after enabling fast lane on old DB):
```powershell
docker compose exec -T worker celery -A app.workers.celery_app:celery call app.workers.tasks.backfill_clusters --args='[20000]'
```

Run cleanup manually:
```powershell
docker compose exec -T worker celery -A app.workers.celery_app:celery call app.workers.tasks.cleanup_old_records
```

## Telegram publishing

Required env:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHANNEL_ID` (channel id like `-100...` or direct chat id)

Urgent publish rules:
- `urgency >= URGENT_THRESHOLD`
- `confidence >= CONFIDENCE_THRESHOLD`
- `final_score >= FAST_SCORE_THRESHOLD`
- `source_count >= FAST_MIN_SOURCES`
- title similarity for clustering: `FAST_TITLE_SIMILARITY`
- hourly limit: `URGENT_RATE_LIMIT_PER_HOUR`
- no duplicates: guarded by `published_messages` keys per cluster

## Data retention cleanup

Daily cleanup task removes old data:
- old published news: `CLEANUP_KEEP_PUBLISHED_DAYS`
- old unpublished news: `CLEANUP_KEEP_UNPUBLISHED_DAYS`
- old idempotency records: `CLEANUP_KEEP_MESSAGES_DAYS`
- schedule: `CLEANUP_HOUR:CLEANUP_MINUTE` (Europe/Kyiv)

Bot prerequisites:
1. Add bot to channel as admin.
2. Grant `Post Messages` permission.
3. Use correct channel id (not @username).
4. Ensure bot token is valid and rotated if leaked.
