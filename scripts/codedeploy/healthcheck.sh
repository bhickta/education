#!/usr/bin/env bash
# CodeDeploy ValidateService hook for the Education live deployment group.
set -euo pipefail

# shellcheck disable=SC1091
source "$(dirname "$0")/lock.sh"

EXPECTED_GROUP="${CODEDEPLOY_GROUP_NAME:-Education-Live-Group}"
GROUP_NAME="${DEPLOYMENT_GROUP_NAME:-}"
SITE_URL="${SITE_URL:-https://apsrohru.erp.himguru.in}"

log() { echo "--- $(date '+%Y-%m-%d %H:%M:%S') | $* ---"; }

if [[ "$GROUP_NAME" != "$EXPECTED_GROUP" ]]; then
	log "ERROR: refusing health check for deployment group '$GROUP_NAME' (expected '$EXPECTED_GROUP')"
	exit 1
fi

trap 'release_deploy_lock' EXIT

for attempt in $(seq 1 18); do
	if curl -fsS --max-time 10 "$SITE_URL/api/method/ping" >/dev/null 2>&1; then
		for path in / /school /school-portal; do
			code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$SITE_URL$path")
			if [[ "$code" != "200" ]]; then
				log "ERROR: $path returned $code"
				exit 1
			fi
			log "$path -> $code"
		done
		log "Health check passed"
		exit 0
	fi

	log "Site not ready yet (attempt ${attempt}/18); retrying in 10 seconds"
	sleep 10
done

log "ERROR: $SITE_URL did not respond to /api/method/ping"
exit 1
