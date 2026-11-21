#!/bin/bash
# Wrapper used by launchd. Logs to logs/daily.log.
cd "$(dirname "$0")/.." || exit 1
mkdir -p logs
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
# make sure Ollama is up (no-op if already running)
if command -v ollama >/dev/null && ! curl -s localhost:11434 >/dev/null; then
  (ollama serve >/dev/null 2>&1 &) ; sleep 5
fi
uv run python main.py >> logs/daily.log 2>&1
