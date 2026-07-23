#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — add your OPENAI_API_KEY before generating BRDs."
fi

mkdir -p data/uploads data/chroma

if [ ! -d "services/python-processor/.venv" ]; then
  python3 -m venv services/python-processor/.venv
fi

source services/python-processor/.venv/bin/activate
pip install -r services/python-processor/requirements.txt

if [ ! -d "apps/api/node_modules" ]; then
  npm install --prefix apps/api
fi

if [ ! -d "apps/web/node_modules" ]; then
  npm install --prefix apps/web
fi

echo "Setup complete."
echo "Run services in separate terminals:"
echo "1) source services/python-processor/.venv/bin/activate && uvicorn app.main:app --reload --port 8000 --app-dir services/python-processor"
echo "2) npm run dev --prefix apps/api"
echo "3) npm run dev --prefix apps/web"
