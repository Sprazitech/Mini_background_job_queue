#!/usr/bin/env bash

set -e

python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp -n .env.example .env || true

echo "Edit .env with your Supabase project credentials, then:"
echo "  source .venv/bin/activate"
echo "  uvicorn app.main:app --reload --port 8000"