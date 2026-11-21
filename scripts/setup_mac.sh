#!/bin/bash
# One-time setup on macOS (Apple Silicon). Run from the project root: ./scripts/setup_mac.sh
set -e
cd "$(dirname "$0")/.."
command -v brew >/dev/null || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
brew list uv >/dev/null 2>&1 || brew install uv
brew list ollama >/dev/null 2>&1 || brew install ollama
uv sync
[ -f .env ] || { cp .env.example .env; echo "Created .env - edit it with your SMTP + API key values."; }
chmod +x scripts/run_daily.sh
(ollama serve >/dev/null 2>&1 &) ; sleep 5
ollama pull qwen2.5:7b-instruct
uv run pytest -q
echo
echo "Next: edit .env, then:  uv run python main.py --dry-run"
echo "Schedule it:           ./scripts/install_launchd.sh 8 0   # daily at 08:00"
