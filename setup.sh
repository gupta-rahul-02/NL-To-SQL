#!/usr/bin/env bash
# setup.sh — First-time setup script for NL-to-SQL
set -e

echo "==> Copying .env.example to .env (edit it before running docker compose up)"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "    Created .env — fill in your MSSQL_SERVER, MSSQL_DATABASE, credentials."
else
  echo "    .env already exists, skipping."
fi

echo ""
echo "==> Starting infrastructure services (Ollama + Redis)…"
docker compose up -d ollama redis

echo ""
echo "==> Waiting for Ollama to be ready…"
until curl -sf http://localhost:11434/api/tags > /dev/null; do
  sleep 3
  echo "    Still waiting for Ollama…"
done

echo ""
echo "==> Pulling LLM models (this may take a few minutes on first run)…"
docker compose exec ollama ollama pull defog/sqlcoder-7b-2
docker compose exec ollama ollama pull nomic-embed-text

echo ""
echo "==> Starting all services…"
docker compose up -d

echo ""
echo "==> Waiting for backend to be healthy…"
until curl -sf http://localhost:8000/health > /dev/null; do
  sleep 5
  echo "    Still waiting for backend…"
done

echo ""
echo "==> Indexing schema into ChromaDB…"
curl -s -X POST http://localhost:8000/api/schema/index | python3 -m json.tool

echo ""
echo "✓ Setup complete!"
echo "  Frontend:  http://localhost"
echo "  Backend:   http://localhost:8000/docs"
echo "  Health:    http://localhost:8000/health"
