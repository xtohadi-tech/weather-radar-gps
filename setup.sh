#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
REPO_DIR="$HOME/weather-radar-gps"
if [ ! -d "$REPO_DIR" ]; then
  echo "[*] Cloning repo..."
  git clone git@github.com:xtohadi-tech/weather-radar-gps.git "$REPO_DIR"
else
  echo "[*] Repo exists, pulling latest..."
  cd "$REPO_DIR"
  git pull --rebase
fi
echo "[*] Done. Run with: python $REPO_DIR/weather_radar.py"
