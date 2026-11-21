#!/bin/bash
# Usage: ./scripts/install_launchd.sh HOUR MINUTE   (default 08:00)
set -e
cd "$(dirname "$0")/.."
H=${1:-8}; M=${2:-0}
ROOT="$(pwd)"
PLIST="$HOME/Library/LaunchAgents/com.user.aibriefing.plist"
sed -e "s|__ROOT__|$ROOT|g" -e "s|__HOUR__|$H|" -e "s|__MIN__|$M|" launchd/com.user.aibriefing.plist.template > "$PLIST"
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Installed. Test now with: launchctl kickstart gui/$(id -u)/com.user.aibriefing"
