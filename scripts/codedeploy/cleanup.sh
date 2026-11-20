#!/usr/bin/env bash
# CodeDeploy BeforeInstall hook for the Education live deployment group.
set -euo pipefail

EXPECTED_GROUP="${CODEDEPLOY_GROUP_NAME:-Education-Live-Group}"
GROUP_NAME="${DEPLOYMENT_GROUP_NAME:-}"

APP="education"
BENCH_DIR="${BENCH_DIR:-/home/frappe/dev-bench-v16}"
APP_DIR="$BENCH_DIR/apps/$APP"
ARTIFACTS_ROOT="/home/frappe/codedeploy-artifacts"
ARTIFACTS_DIR="$ARTIFACTS_ROOT/education"
PRESERVE_DIR="$ARTIFACTS_ROOT/education-previous-assets"
TMP_DIR="/tmp/codedeploy-education"

log() { echo "--- $(date '+%Y-%m-%d %H:%M:%S') | $* ---"; }

if [[ "$GROUP_NAME" != "$EXPECTED_GROUP" ]]; then
	log "ERROR: refusing cleanup for deployment group '$GROUP_NAME' (expected '$EXPECTED_GROUP')"
	exit 1
fi

free_kb=$(df -Pk /home | awk 'NR==2 {print $4}')
if [[ "${free_kb:-0}" -lt 2097152 ]]; then
	log "ERROR: less than 2 GiB free on /home ($((free_kb / 1024)) MiB); free disk space before deploying"
	exit 1
fi

rm -rf "$TMP_DIR"
rm -rf "$PRESERVE_DIR"
mkdir -p "$PRESERVE_DIR/public/frontend" "$PRESERVE_DIR/education/www"

if [[ -d "$APP_DIR/public/frontend/assets" ]]; then
	cp -a "$APP_DIR/public/frontend/assets" "$PRESERVE_DIR/public/frontend/assets"
	log "Preserved previous portal assets"
fi

# The legacy /edu-portal page is untracked on the live checkout. Keep it so a
# deploy does not remove a page that was never part of the repository.
if [[ -f "$APP_DIR/education/www/edu-portal.html" ]]; then
	cp -a "$APP_DIR/education/www/edu-portal.html" "$PRESERVE_DIR/education/www/edu-portal.html"
	log "Preserved legacy edu-portal.html"
fi

if [[ -d "$APP_DIR" ]]; then
	rm -rf "$APP_DIR"
	log "Removed old app directory $APP_DIR"
fi

rm -rf "$ARTIFACTS_DIR"
log "Cleanup complete"
