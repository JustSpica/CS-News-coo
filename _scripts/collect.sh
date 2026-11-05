#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/.venv/bin/activate"

source "$VENV"
cd "$ROOT"
python main.py "$@"
