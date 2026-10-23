#!/usr/bin/env bash
#
# Redeploys whatever code is CURRENTLY in /opt/grudge: applies database
# migrations, refreshes dependencies, rebuilds the website, and restarts the
# services. For updates AFTER the first install (ops/install.sh).
#
# This script does NOT download anything - use ops/pull-and-update.sh for the
# normal "get the latest from GitHub and deploy it" routine, which pulls and
# then runs this. (Pulling is kept out of here on purpose: the repo is
# private, only root/the person who cloned it has GitHub access, and a script
# that overwrites itself mid-run is asking for trouble.)
#
# HOW TO RUN, on the server:
#   sudo /opt/grudge/ops/update.sh
#
# Every step is idempotent or a plain restart, so running it twice in a row
# is harmless.
#
set -euo pipefail

step() { printf '\n\033[1;34m=== %s ===\033[0m\n' "$*"; }
info() { printf '  %s\n' "$*"; }
die()  { printf '\033[1;31mSTOP: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Run this with sudo."

CODE_DIR=/opt/grudge
[ -f "$CODE_DIR/backend/pyproject.toml" ] || die "No code at $CODE_DIR - this only updates an existing install (run ops/install.sh first)."
[ -f /etc/grudge.env ] || die "/etc/grudge.env is missing - this only updates an existing install (run ops/install.sh first)."

step "1/3  Applying database migrations"
# alembic upgrade head is a no-op if the database is already current, so
# this is safe on every update whether or not this change touched the schema.
systemd-run --quiet --wait --pipe --uid=grudge \
  -p EnvironmentFile=/etc/grudge.env \
  -p WorkingDirectory="$CODE_DIR/backend" \
  "$CODE_DIR/backend/.venv/bin/alembic" upgrade head
info "Database is up to date."

step "2/3  Reinstalling dependencies and rebuilding the website"
# Cheap when nothing changed - pip and npm ci just confirm everything's there.
sudo -u grudge -H bash -c "cd '$CODE_DIR/backend' && .venv/bin/pip install -q -e '../engine[dev]' -e ."

BACKEND_URL="$(grep '^BACKEND_BASE_URL=' /etc/grudge.env | cut -d= -f2-)"
[ -n "$BACKEND_URL" ] || die "Could not read BACKEND_BASE_URL from /etc/grudge.env."
sudo -u grudge -H bash -c "cd '$CODE_DIR/frontend' && npm ci"

# Build into a STAGING folder (dist.new), check it, and only then swap it in
# as the live site (dist - what Caddy serves). Building straight into dist
# meant a failed check below left the broken build live anyway: a site built
# without the backend address silently points every visitor's browser at
# http://localhost:8000 (their own computer), which can leave the page blank.
sudo -u grudge -H bash -c "rm -rf '$CODE_DIR/frontend/dist.new'"
sudo -u grudge -H env VITE_API_BASE_URL="$BACKEND_URL" bash -c "cd '$CODE_DIR/frontend' && npm run build -- --outDir dist.new --emptyOutDir"

API_HOST="$(echo "$BACKEND_URL" | sed -E 's|https?://||')"
if ! grep -rlF "$API_HOST" "$CODE_DIR/frontend/dist.new/assets/"*.js >/dev/null 2>&1; then
  rm -rf "$CODE_DIR/frontend/dist.new"
  die "The new website build is missing the backend address ($API_HOST), so it was NOT put live - the site is still running its previous version. Check BACKEND_BASE_URL in /etc/grudge.env."
fi
if grep -rlF "localhost:8000" "$CODE_DIR/frontend/dist.new/assets/"*.js >/dev/null 2>&1; then
  rm -rf "$CODE_DIR/frontend/dist.new"
  die "The new website build still points at localhost:8000, so it was NOT put live - the site is still running its previous version."
fi

rm -rf "$CODE_DIR/frontend/dist.old"
[ -d "$CODE_DIR/frontend/dist" ] && mv "$CODE_DIR/frontend/dist" "$CODE_DIR/frontend/dist.old"
mv "$CODE_DIR/frontend/dist.new" "$CODE_DIR/frontend/dist"
rm -rf "$CODE_DIR/frontend/dist.old"
info "Website rebuilt and put live, backend address confirmed baked in."

step "3/3  Restarting services"
systemctl restart grudge-backend grudge-worker grudge-watchdog
sleep 2
if systemctl is-active --quiet grudge-backend grudge-worker grudge-watchdog; then
  info "All three services are running."
else
  systemctl status grudge-backend grudge-worker grudge-watchdog --no-pager || true
  die "One of the services didn't come back up - see the status above, then:
  journalctl -u grudge-backend -n 50 --no-pager  (swap in the failing name)."
fi

step "Done - the site is now running the latest code"
