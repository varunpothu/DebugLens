#!/bin/bash
set -Eeuo pipefail
umask 077
exec >> /var/log/debuglens-backup.log 2>&1

backup_dir="/var/lib/debuglens-backups"
install -d -m 0700 "$backup_dir"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_name="debuglens-$timestamp.sqlite"
backup_path="$backup_dir/$backup_name"
metadata_path="$backup_path.json"
container_id=""
uploaded=false

cleanup() {
  if [[ "$uploaded" == "true" ]]; then
    if [[ -n "$container_id" ]]; then
      docker exec "$container_id" rm -f "/data/$backup_name" >/dev/null 2>&1 || true
    fi
    rm -f "$backup_path" "$metadata_path"
  fi
}
trap cleanup EXIT

if [[ -z "${DEBUGLENS_BACKUP_BUCKET:-}" || -z "${DEBUGLENS_BACKUP_KMS_KEY_ARN:-}" || -z "${AWS_REGION:-}" ]]; then
  echo "Backup configuration is incomplete; refusing to upload."
  exit 1
fi

container_id="$(docker compose \
  --project-directory /opt/debuglens \
  --env-file /etc/debuglens/runtime.env \
  -f /opt/debuglens/deploy/compose.aws.yml \
  ps -q api)"
if [[ -z "$container_id" ]]; then
  echo "API container is not available; backup skipped."
  exit 1
fi

echo "Starting SQLite backup at $timestamp"
metadata="$(docker exec "$container_id" python -m app.db_backup backup --destination "/data/$backup_name")"
docker cp "$container_id:/data/$backup_name" "$backup_path"
chmod 0600 "$backup_path"
printf '%s\n' "$metadata" > "$metadata_path"
chmod 0600 "$metadata_path"

expected_sha="$(printf '%s' "$metadata" | python3 -c 'import json,sys; print(json.load(sys.stdin)["sha256"])')"
actual_sha="$(sha256sum "$backup_path" | awk '{print $1}')"
if [[ "$expected_sha" != "$actual_sha" ]]; then
  echo "Backup SHA-256 mismatch; preserving the local copy for investigation."
  exit 1
fi

aws s3 cp "$backup_path" "s3://$DEBUGLENS_BACKUP_BUCKET/backups/$backup_name" \
  --region "$AWS_REGION" --sse aws:kms --sse-kms-key-id "$DEBUGLENS_BACKUP_KMS_KEY_ARN" --only-show-errors
aws s3 cp "$metadata_path" "s3://$DEBUGLENS_BACKUP_BUCKET/backups/$backup_name.json" \
  --region "$AWS_REGION" --sse aws:kms --sse-kms-key-id "$DEBUGLENS_BACKUP_KMS_KEY_ARN" --only-show-errors

uploaded=true
echo "SQLite backup uploaded to s3://$DEBUGLENS_BACKUP_BUCKET/backups/$backup_name (sha256 $actual_sha)"
