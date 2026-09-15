#!/usr/bin/env bash
set -euo pipefail

# Nightly logical backup of the Grudge Postgres database. Dumps + compresses
# locally, uploads off-box via rclone (provider-agnostic - which remote it
# actually is lives in rclone's own config, not here, so swapping B2/S3/
# whatever later needs no script change), then rotates old local copies.
# Run by grudge-backup.timer/.service (see ../README.md for setup).
#
# Required environment (normally supplied via /etc/grudge-backup.env, loaded
# by the systemd service):
#   PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE - standard libpq vars,
#     picked up by pg_dump automatically
#   RCLONE_REMOTE   - rclone remote:path to upload to, e.g. "b2:grudge-backups"
#     (not required when SKIP_UPLOAD=1)
#
# Optional environment:
#   BACKUP_DIR   - local staging directory for dumps (default /var/backups/grudge)
#   KEEP_DAILY   - how many local dumps to retain (default 7)
#   SKIP_UPLOAD  - set to 1 to dump+rotate locally without uploading; for
#     testing the script itself, or a dry run before rclone is configured

BACKUP_DIR="${BACKUP_DIR:-/var/backups/grudge}"
KEEP_DAILY="${KEEP_DAILY:-7}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DUMP_FILE="${BACKUP_DIR}/grudge_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

# Guards the pg_dump|gzip pipeline itself failing partway (e.g. a dropped
# connection): `pipefail` correctly aborts the script via `set -e` in that
# case, but an implicit set -e exit skips straight past everything below
# without a chance to remove the half-written $DUMP_FILE it leaves behind -
# confirmed empirically: a pg_dump connection failure still left a real
# ~20-byte file (gzip's own header/footer for zero input), which is "not
# empty" by a plain -s size check, so that check alone doesn't catch it.
# Disarmed (DUMP_OK=1) the moment the dump is confirmed good, so a later
# failure (upload, rotation) never deletes an otherwise-good local backup.
DUMP_OK=0
cleanup_incomplete_dump() {
  if [ "$DUMP_OK" != "1" ]; then
    rm -f "$DUMP_FILE"
  fi
}
trap cleanup_incomplete_dump ERR

pg_dump --no-owner --no-privileges | gzip -9 > "$DUMP_FILE"

# Separate safety net from the trap above: pg_dump can exit 0 while still
# producing a suspiciously empty dump (that path doesn't go through the
# trap, since nothing there actually failed).
if [ ! -s "$DUMP_FILE" ]; then
  echo "backup_db.sh: dump produced an empty file, aborting" >&2
  rm -f "$DUMP_FILE"
  exit 1
fi
DUMP_OK=1

if [ "${SKIP_UPLOAD:-0}" = "1" ]; then
  echo "backup_db.sh: SKIP_UPLOAD=1, leaving dump local only ($DUMP_FILE)" >&2
else
  rclone copy "$DUMP_FILE" "$RCLONE_REMOTE"
  echo "backup_db.sh: uploaded to $RCLONE_REMOTE/$(basename "$DUMP_FILE")"
fi

# Local rotation only - `set -e` above already means we never reach this line
# if the dump or upload failed, so a failed run never rotates a good backup
# away. Off-box copies are expired separately via the storage provider's own
# lifecycle rules (see ../README.md) - not duplicated here, so there's only
# one place retention is actually configured.
find "$BACKUP_DIR" -maxdepth 1 -name 'grudge_*.sql.gz' -type f -printf '%T@ %p\n' \
  | sort -rn \
  | tail -n +"$((KEEP_DAILY + 1))" \
  | cut -d' ' -f2- \
  | xargs -r rm -f
