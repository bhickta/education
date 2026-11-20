# CI/CD Guide — Himguru Education fork

This fork deploys the `education` app to the live Himguru bench with GitHub
Actions, S3, and CodeDeploy. It is intentionally separate from the upstream
`frappe/education` workflows.

## Branch and environment

| Branch | Environment | Bench | Site | CodeDeploy group |
| :--- | :--- | :--- | :--- | :--- |
| `himguru` | Live | `/home/frappe/dev-bench-v16` | `apsrohru.erp.himguru.in` | `Education-Live-Group` |

The `himguru` branch is the live fork. Do not merge this pipeline into the
upstream-facing `develop` branch; keep upstream sync work separate.

## Pipeline

1. The frontend is installed and built with Vite (Node 20, because this fork
   still uses Vite 2).
2. Commit flags are parsed.
3. The app is zipped and uploaded to S3 under `education/`.
4. CodeDeploy runs the revision:
   - `scripts/codedeploy/cleanup.sh`
   - `scripts/codedeploy/deploy.sh`
   - `scripts/codedeploy/healthcheck.sh`
5. The workflow waits for CodeDeploy and checks the live site.

The deployment group enables automatic rollback on deployment failure. A
failed ValidateService hook counts as a failure.

## Commit flags

The same flags as the Himguru app pipeline:

| Flag | Effect |
| :--- | :--- |
| `[skip build]` | Skips `bench build --app education` |
| `[skip migrate]` | Skips `bench migrate` |
| `[skip restart]` | Skips `bench restart` |
| `[skip backup]` | Skips the pre-migrate database backup |
| `[restart only]` | Skips build, migrate, and backup |

The frontend is always built in CI.

## One-time AWS setup

The CodeDeploy agent is already on the server. Create the Education
application and deployment group:

```bash
AWS_REGION=ap-south-1 \
S3_BUCKET_NAME=<the existing RAPL bucket> \
./scripts/codedeploy/bootstrap-aws.sh
```

The script targets the app server with the `Name=raplbaddi` tag, not the
broader `Environment=Production` set, because that also matches the
`prodrapl-db` database instance.

Add these secrets to this repository:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION` (`ap-south-1`)
- `S3_BUCKET_NAME`

The same credentials and bucket as the Himguru app pipeline are fine if the
IAM policy includes the `education/` prefix and the new CodeDeploy
application/group.

## What the server does

- Refuses a deployment group other than `Education-Live-Group`.
- Refuses to start with less than 2 GiB free on `/home`.
- Preserves `public/frontend/assets` so cached portal HTML keeps resolving.
- Installs `education` with `pip install -e`.
- Runs `bench build --app education` unless skipped.
- Backs up the database before `bench migrate`, keeping seven database
  backups and three file backups.
- Migrates, clears cache, restarts bench, and validates the live URLs.

## Coordination with the Himguru app

Both apps share `dev-bench-v16` and the same site. A deploy of either app runs
`bench migrate`, `bench clear-cache`, and `bench restart`, so it affects the
other app. Do not run the Himguru and Education deploys at the same time.
If simultaneous deploys become common, add a shared `flock` around the
bench steps in both pipelines.

## Rollback

Automatic rollback restores the previous code revision, but it does not undo a
completed migration. Restore the pre-migrate backup from:

`/home/frappe/dev-bench-v16/sites/apsrohru.erp.himguru.in/private/backups/`

Then re-run the previous CodeDeploy revision or revert the offending commit on
`himguru` and let the pipeline deploy the revert.
