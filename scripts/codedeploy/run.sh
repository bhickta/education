#!/usr/bin/env bash
# Runs as the frappe user after the Education app directory is replaced.
set -euo pipefail

: "${BENCH_DIR:?BENCH_DIR is required}"
: "${APP:?APP is required}"
: "${SITE:?SITE is required}"

SKIP_BUILD="${SKIP_BUILD:-false}"
SKIP_MIGRATE="${SKIP_MIGRATE:-false}"
SKIP_RESTART="${SKIP_RESTART:-false}"
SKIP_BACKUP="${SKIP_BACKUP:-false}"
DEPLOY_SHA="${DEPLOY_SHA:-unknown}"

export PATH="/home/frappe/.local/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"
export NVM_DIR="$HOME/.nvm"
if [[ -s "$NVM_DIR/nvm.sh" ]]; then
	# shellcheck disable=SC1091
	. "$NVM_DIR/nvm.sh"
fi

log() { echo "--- $(date '+%Y-%m-%d %H:%M:%S') | $* ---"; }

cd "$BENCH_DIR"

if ! grep -qxF "$APP" sites/apps.txt; then
	echo "$APP" >> sites/apps.txt
	log "Added $APP to sites/apps.txt"
fi

log "Installing Python dependencies for $APP"
./env/bin/pip install --quiet -e "apps/$APP"

if [[ "$SKIP_BUILD" != "true" ]]; then
	log "Building bench assets for $APP"
	bench build --app "$APP"
else
	log "Skipping bench build"
fi

if [[ "$SKIP_BACKUP" != "true" ]]; then
	log "Backing up $SITE database before migrate"
	bench --site "$SITE" backup

	backup_dir="$BENCH_DIR/sites/$SITE/private/backups"
	mapfile -t old_db < <(
		find "$backup_dir" -maxdepth 1 -type f -name "*-database.sql.gz" -printf "%T@ %p\n" |
			sort -rn | awk 'NR>7 {print $2}'
	)
	if (( ${#old_db[@]} )); then
		rm -f "${old_db[@]}"
		log "Pruned ${#old_db[@]} old database backups"
	fi

	mapfile -t old_files < <(
		find "$backup_dir" -maxdepth 1 -type f \( -name "*-files.tar" -o -name "*-private-files.tar" \) -printf "%T@ %p\n" |
			sort -rn | awk 'NR>3 {print $2}'
	)
	if (( ${#old_files[@]} )); then
		rm -f "${old_files[@]}"
		log "Pruned ${#old_files[@]} old file backups"
	fi
else
	log "Skipping database backup"
fi

if [[ "$SKIP_MIGRATE" != "true" ]]; then
	log "Migrating $SITE"
	bench --site "$SITE" migrate
else
	log "Skipping migrate"
fi

log "Clearing cache for $SITE"
bench --site "$SITE" clear-cache

if [[ "$SKIP_RESTART" != "true" ]]; then
	log "Restarting bench"
	bench restart
else
	log "Skipping restart"
fi

echo "$DEPLOY_SHA" > "$BENCH_DIR/apps/$APP/DEPLOYED_SHA"
log "Deployed $DEPLOY_SHA"
