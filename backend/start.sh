#!/bin/sh
set -e

# Railway PostgreSQL addon provides DATABASE_URL as postgres:// or postgresql://
# SQLAlchemy asyncpg driver requires postgresql+asyncpg://
if [ -n "$DATABASE_URL" ]; then
  export DATABASE_URL=$(echo "$DATABASE_URL" \
    | sed 's|^postgres://|postgresql+asyncpg://|' \
    | sed 's|^postgresql://|postgresql+asyncpg://|')
fi

echo "▶ Running database migrations..."
alembic upgrade head

echo "▶ Seeding demo data..."
python seed.py || echo "Seed skipped (already up to date)"

echo "▶ Starting Wavvy API..."
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
