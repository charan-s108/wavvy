#!/bin/sh
set -e

# Supabase / Neon provide postgres:// — SQLAlchemy asyncpg needs postgresql+asyncpg://
if [ -n "$DATABASE_URL" ]; then
  export DATABASE_URL=$(echo "$DATABASE_URL" \
    | sed 's|^postgres://|postgresql+asyncpg://|' \
    | sed 's|^postgresql://|postgresql+asyncpg://|')
fi

# HuggingFace persistent volume — ChromaDB lives here across restarts
mkdir -p /data/chroma_db
export CHROMA_PERSIST_DIR=${CHROMA_PERSIST_DIR:-/data/chroma_db}

# Both processes run in this container — worker calls /api/kb/search on localhost
export BACKEND_INTERNAL_URL=${BACKEND_INTERNAL_URL:-http://localhost:7860}

echo "▶ Running database migrations..."
alembic upgrade head

echo "▶ Seeding demo data..."
python seed.py || echo "   Seed skipped (already up to date)"

echo "▶ Starting Wavvy API + LiveKit Worker..."
exec supervisord -c supervisord.conf
