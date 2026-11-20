#!/usr/bin/env bash
# Shared deploy lock for dev-bench-v16.
#
# CodeDeploy can run deployments for different applications at the same time.
# The Himguru and Education pipelines share one bench, so every bench mutation
# must be serialized. This directory lock is acquired in BeforeInstall and
# released by ValidateService (or by an error trap in the install hook).
set -euo pipefail

LOCK_DIR="${DEPLOY_LOCK_DIR:-/var/lock/codedeploy-frappe-bench.lock}"
LOCK_STALE_SECONDS="${DEPLOY_LOCK_STALE_SECONDS:-3600}"
LOCK_WAIT_SECONDS="${DEPLOY_LOCK_WAIT_SECONDS:-2400}"
LOCK_OWNER="${DEPLOYMENT_GROUP_NAME:-unknown-group}"

acquire_deploy_lock() {
	local started now age
	started=$(date +%s)

	while ! mkdir "$LOCK_DIR" 2>/dev/null; do
		now=$(date +%s)
		age=0
		if [[ -d "$LOCK_DIR" ]]; then
			age=$((now - $(stat -c %Y "$LOCK_DIR" 2>/dev/null || echo "$now")))
		fi

		if (( age > LOCK_STALE_SECONDS )); then
			echo "Removing stale deploy lock ($age seconds old)"
			rm -rf "$LOCK_DIR"
			continue
		fi

		if (( now - started > LOCK_WAIT_SECONDS )); then
			echo "ERROR: timed out waiting for the shared deploy lock"
			exit 1
		fi

		echo "Another deployment holds the bench lock; waiting 15s..."
		sleep 15
	done

	{
		echo "owner=$LOCK_OWNER"
		echo "pid=$$"
		echo "started=$(date -Is)"
	} >"$LOCK_DIR/owner"

	echo "Acquired deploy lock for $LOCK_OWNER"
}

release_deploy_lock() {
	if [[ ! -d "$LOCK_DIR" ]]; then
		return 0
	fi
	if [[ -f "$LOCK_DIR/owner" ]] && ! grep -qx "owner=$LOCK_OWNER" "$LOCK_DIR/owner"; then
		return 0
	fi
	rm -rf "$LOCK_DIR"
}
