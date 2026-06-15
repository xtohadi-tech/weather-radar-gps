#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
REPO_DIR="$HOME/weather-radar-gps"
cd "$REPO_DIR"

echo "[*] Checking changes..."
if [[ -z "$(git status --porcelain)" ]]; then
  echo "[!] No changes to deploy."
  exit 0
fi

echo "[*] Staging and committing..."
git add -A
read -rp "Commit message: " msg
if [[ -z "$msg" ]]; then
  msg="update: $(date '+%Y-%m-%d %H:%M')"
fi
git commit -m "$msg"

echo "[*] Pushing to origin/main..."
git push origin main

echo "[*] Done. Open https://github.com/xtohadi-tech/weather-radar-gps/settings/pages"
echo "    Set Source = Deploy from branch = main = / (root)"
echo "    Wait ~1 min, then visit:"
echo "    https://xtohadi-tech.github.io/weather-radar-gps/"
