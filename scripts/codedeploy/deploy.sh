#!/usr/bin/env bash
# CodeDeploy AfterInstall hook for the Education live deployment group.
set -euo pipefail

EXPECTED_GROUP="${CODEDEPLOY_GROUP_NAME:-Education-Live-Group}"
GROUP_NAME="${DEPLOYMENT_GROUP_NAME:-}"

APP="education"
BENCH_DIR="${BENCH_DIR:-/home/frappe/dev-bench-v16}"
SITE="${SITE:-apsrohru.erp.himguru.in}"
APP_DIR="$BENCH_DIR/apps/$APP"
ARTIFACTS_ROOT="/home/frappe/codedeploy-artifacts"
ARTIFACTS_DIR="$ARTIFACTS_ROOT/education"
PRESERVE_DIR="$ARTIFACTS_ROOT/education-previous-assets"
TMP_DIR="/tmp/codedeploy-education"

log() { echo "--- $(date '+%Y-%m-%d %H:%M:%S') | $* ---"; }

if [[ "$GROUP_NAME" != "$EXPECTED_GROUP" ]]; then
	log "ERROR: refusing deploy for deployment group '$GROUP_NAME' (expected '$EXPECTED_GROUP')"
	exit 1
fi

if [[ ! -d "$TMP_DIR" ]]; then
	log "ERROR: CodeDeploy staging directory $TMP_DIR was not created"
	exit 1
fi

mkdir -p "$ARTIFACTS_ROOT"
rm -rf "$ARTIFACTS_DIR"
cp -a "$TMP_DIR" "$ARTIFACTS_DIR"
rm -rf "$TMP_DIR"

SKIP_BUILD="false"
SKIP_MIGRATE="false"
SKIP_RESTART="false"
SKIP_BACKUP="false"
DEPLOY_SHA="unknown"

if [[ -f "$ARTIFACTS_DIR/.deploy_config" ]]; then
	# shellcheck disable=SC1091
	source "$ARTIFACTS_DIR/.deploy_config"
else
	log "WARNING: .deploy_config missing; running the full deployment"
fi

log "Deploying $APP to $SITE from ${DEPLOY_SHA}"
log "Flags: SKIP_BUILD=$SKIP_BUILD SKIP_MIGRATE=$SKIP_MIGRATE SKIP_RESTART=$SKIP_RESTART SKIP_BACKUP=$SKIP_BACKUP"

mkdir -p "$BENCH_DIR/apps"
rm -rf "$APP_DIR"
cp -a "$ARTIFACTS_DIR" "$APP_DIR"

if [[ -d "$PRESERVE_DIR/public/frontend/assets" ]]; then
	mkdir -p "$APP_DIR/public/frontend/assets"
	cp -an "$PRESERVE_DIR/public/frontend/assets/." "$APP_DIR/public/frontend/assets/"
	log "Restored previous portal assets"
fi

if [[ -d "$APP_DIR/public/frontend/assets" ]]; then
	find "$APP_DIR/public/frontend/assets" -type f -mtime +60 -delete
fi

rm -rf "$PRESERVE_DIR"
chown -R frappe:frappe "$APP_DIR"

sudo -u frappe env \
	BENCH_DIR="$BENCH_DIR" \
	APP="$APP" \
	SITE="$SITE" \
	SKIP_BUILD="$SKIP_BUILD" \
	SKIP_MIGRATE="$SKIP_MIGRATE" \
	SKIP_RESTART="$SKIP_RESTART" \
	SKIP_BACKUP="$SKIP_BACKUP" \
	DEPLOY_SHA="$DEPLOY_SHA" \
	bash "$APP_DIR/scripts/codedeploy/run.sh"

log "Deployment steps complete"
