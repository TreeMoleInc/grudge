#!/usr/bin/env bash
#
# Pulls the latest code and redeploys it - for updates AFTER the first
# install (ops/install.sh). Assumes install.sh already ran successfully at
# least once, so the systemd services, Caddy, and Postgres roles already
# exist; this script only refreshes the code and restarts things.
#
# HOW TO RUN, on the server:
#   sudo /opt/grudge/ops/update.sh
#
# Safe to run any time there's a new fix to pick up. Every step is either
# idempotent or a plain restart, so running it twice in a row does nothing
# harmful the second time.
#
set -euo pipefail

step() { printf '\n\033[1;34m=== %s ===\033[0m\n' "$*"; }
info() { printf '  %s\n' "$*"; }
die()  { printf '\033[1;31mSTOP: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Run this with sudo."

CODE_DIR=/opt/grudge
[ -d "$CODE_DIR/.git" ] || die "No git repo at $CODE_DIR - this script only updates an existing install (run ops/install.sh first)."

step "1/4  Pulling the latest code"
BEFORE="$(sudo -u grudge -H git -C "$CODE_DIR" rev-parse HEAD)"
sudo -u grudge -H git -C "$CODE_DIR" pull --ff-only
AFTER="$(sudo -u grudge -H git -C "$CODE_DIR" rev-parse HEAD)"
if [ "$BEFORE" = "$AFTER" ]; then
  info "Already up to date - nothing new to pull. Continuing anyway (in case a previous update run stopped partway)."
else
  info "Updated $BEFORE -> $AFTER"
fi

step "2/4  Applying database migrations"
# alembic upgrade head is a no-op if the database is already current, so
# this is safe to run on every update, not just ones that add a migration.
systemd-run --quiet --wait --pipe --uid=grudge \
  -p EnvironmentFile=/etc/grudge.env \
  -p WorkingDirectory="$CODE_DIR/backend" \
  "$CODE_DIR/backend/.venv/bin/alembic" upgrade head
info "Database is up to date."

step "3/4  Reinstalling dependencies and rebuilding the website"
# Also cheap/idempotent when nothing changed - pip and npm ci both just
# confirm everything's already installed rather than redoing real work.
sudo -u grudge -H bash -c "cd '$CODE_DIR/backend' && .venv/bin/pip install -q -e '../engine[dev]' -e ."

BACKEND_URL="$(grep '^BACKEND_BASE_URL=' /etc/grudge.env | cut -d= -f2-)"
[ -n "$BACKEND_URL" ] || die "Could not read BACKEND_BASE_URL from /etc/grudge.env."
sudo -u grudge -H bash -c "cd '$CODE_DIR/frontend' && npm ci"
sudo -u grudge -H env VITE_API_BASE_URL="$BACKEND_URL" bash -c "cd '$CODE_DIR/frontend' && npm run build"
if grep -rl "$(echo "$BACKEND_URL" | sed -E 's|https?://||')" "$CODE_DIR/frontend/dist/assets/"*.js >/dev/null 2>&1; then
  info "Website rebuilt, backend address confirmed baked in."
else
  die "Website rebuilt but the backend address didn't get baked in - check BACKEND_BASE_URL in /etc/grudge.env."
fi

step "4/4  Restarting services"
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
