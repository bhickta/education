#!/usr/bin/env bash
# One-time CodeDeploy bootstrap for the Himguru Education fork.
#
# The deployment group copies the EC2 tag filters of the existing RAPL
# development group, so it targets the same bench server.
set -euo pipefail

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-ap-south-1}}"
APP_NAME="${CODEDEPLOY_APP_NAME:-Education-App}"
GROUP_NAME="${CODEDEPLOY_GROUP_NAME:-Education-Live-Group}"
SOURCE_APP="${SOURCE_APP:-RaplBaddi-App}"
SOURCE_GROUP="${SOURCE_GROUP:-Rapl-Dev-Group}"
TARGET_TAG_KEY="${TARGET_TAG_KEY:-Name}"
TARGET_TAG_VALUE="${TARGET_TAG_VALUE:-raplbaddi}"
S3_BUCKET_NAME="${S3_BUCKET_NAME:-}"

for command in aws python3; do
	if ! command -v "$command" >/dev/null 2>&1; then
		echo "Missing required command: $command" >&2
		exit 1
	fi
done

export AWS_DEFAULT_REGION="$REGION"

account_id=$(aws sts get-caller-identity --query Account --output text)
echo "AWS account: $account_id"
echo "Region:      $REGION"
echo "Application: $APP_NAME"
echo "Group:       $GROUP_NAME"

if aws deploy get-application --application-name "$APP_NAME" >/dev/null 2>&1; then
	echo "Application $APP_NAME already exists"
else
	aws deploy create-application \
		--application-name "$APP_NAME" \
		--compute-platform Server >/dev/null
	echo "Created application $APP_NAME"
fi

if aws deploy get-deployment-group \
	--application-name "$APP_NAME" \
	--deployment-group-name "$GROUP_NAME" >/dev/null 2>&1; then
	echo "Deployment group $GROUP_NAME already exists"
else
	tmp_source=$(mktemp)
	tmp_create=$(mktemp)
	trap 'rm -f "$tmp_source" "$tmp_create"' EXIT

	aws deploy get-deployment-group \
		--application-name "$SOURCE_APP" \
		--deployment-group-name "$SOURCE_GROUP" \
		--query deploymentGroupInfo \
		--output json >"$tmp_source"

	python3 - "$tmp_source" "$tmp_create" "$APP_NAME" "$GROUP_NAME" "$TARGET_TAG_KEY" "$TARGET_TAG_VALUE" <<'PY'
import json
import sys

source_path, output_path, app_name, group_name, tag_key, tag_value = sys.argv[1:7]
source = json.load(open(source_path))

payload = {
	"applicationName": app_name,
	"deploymentGroupName": group_name,
	"serviceRoleArn": source["serviceRoleArn"],
	"deploymentConfigName": source.get("deploymentConfigName", "CodeDeployDefault.OneAtATime"),
	"deploymentStyle": source.get(
		"deploymentStyle",
		{"deploymentType": "IN_PLACE", "deploymentOption": "WITHOUT_TRAFFIC_CONTROL"},
	),
	"autoRollbackConfiguration": {
		"enabled": True,
		"events": ["DEPLOYMENT_FAILURE"],
	},
	# Target the app server explicitly. Environment=Production also matches
	# the prodrapl-db database instance.
	"ec2TagFilters": [
		{"Key": tag_key, "Value": tag_value, "Type": "KEY_AND_VALUE"},
	],
}

with open(output_path, "w") as handle:
	json.dump(payload, handle)
PY

	aws deploy create-deployment-group --cli-input-json "file://$tmp_create" >/dev/null
	echo "Created deployment group $GROUP_NAME"
fi

if [[ -n "$S3_BUCKET_NAME" ]]; then
	cat <<EOF

Required permissions for the GitHub Actions IAM user (scope the CodeDeploy
resource to the new application and group, and S3 to the education prefix):

{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "codedeploy:CreateDeployment",
        "codedeploy:GetDeployment",
        "codedeploy:GetDeploymentConfig",
        "codedeploy:RegisterApplicationRevision",
        "codedeploy:GetApplicationRevision"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::${S3_BUCKET_NAME}",
        "arn:aws:s3:::${S3_BUCKET_NAME}/education/*"
      ]
    }
  ]
}

Add these repository secrets:
  AWS_ACCESS_KEY_ID
  AWS_SECRET_ACCESS_KEY
  AWS_REGION=${REGION}
  S3_BUCKET_NAME=${S3_BUCKET_NAME}
EOF
else
	echo "S3_BUCKET_NAME not set; skipping the IAM policy example."
fi
