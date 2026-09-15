#!/usr/bin/env bash
#
# One-shot installer for Grudge on its production server. Runs every step of
# README.md's "Transfer" checklist that happens *on the container*, in order,
# so the server can be set up without doing it by hand. It is the same commands
# the README documents - if a step fails, that section of the README is the
# explanation of what it was trying to do.
#
# SAFE TO RE-RUN: every step checks whether it's already done and skips it, so
# if the script stops partway (a wrong value, a missing package), fix the cause
# and just run it again from the top.
#
# ---------------------------------------------------------------------------
# BEFORE YOU RUN THIS - five things the script cannot do for you:
#
#   1. Clone the code to /opt/grudge, using your own GitHub access:
#        sudo git clone <repo-url> /opt/grudge
#      Then run this script from there: sudo /opt/grudge/ops/install.sh
#      (The script no longer clones - everything downstream, the services and
#      the web server, expects the code at exactly /opt/grudge.)
#
#   2. Turn on nesting for the container. On the Proxmox HOST (not in here):
#        pct set <container-id> --features nesting=1
#        pct reboot <container-id>
#      Without it, the sandbox test in step 4 fails and the script stops.
#
#   3. Put the two secret files next to this script (they are sent to you
#      privately, never in the repo):
#        grudge.env      - the app's real passwords/keys
#        rclone.conf     - the off-site backup storage key
#      By default the script looks for them in the folder you run it from
#      (/opt/grudge/ops); set SECRETS_DIR=/path/to/folder to point elsewhere.
#
#   4. Point two DNS records at this server's public IP:
#        grudge.<domain>       and       api.grudge.<domain>
#      (Needed for HTTPS in step 10. The app still installs without it; it
#      just can't get certificates until DNS is live.)
#
#   5. Add the production sign-in address in Google Cloud Console:
#        https://api.grudge.<domain>/auth/google/callback
#      (Sign-in won't work until this is added - separate from the server.)
#
# ---------------------------------------------------------------------------
# HOW TO RUN (after cloning to /opt/grudge, per step 1 above):
#
#   sudo DOMAIN=example.com /opt/grudge/ops/install.sh
#
# It will ask for the domain if you don't pass it. You can also set these
# ahead of time as environment variables to run it unattended:
#
#   DOMAIN         the domain the two subdomains live under, e.g. example.com
#                  (the script builds grudge.<domain> and api.grudge.<domain>)
#   SECRETS_DIR    where grudge.env and rclone.conf are (default: this folder)
#   BEHIND_PROXY   set to 1 if another reverse proxy already handles HTTPS for
#                  your containers - Caddy then serves plain http on port 80 and
#                  your main proxy forwards the two subdomains to it (see step 10)
#
set -euo pipefail

# --- helpers ---------------------------------------------------------------

step() { printf '\n\033[1;34m=== %s ===\033[0m\n' "$*"; }
info() { printf '  %s\n' "$*"; }
warn() { printf '\033[1;33m  ! %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mSTOP: %s\033[0m\n' "$*" >&2; exit 1; }

ask() {
  # ask VAR "prompt"  - fills VAR from its current value or by prompting.
  local __var="$1" __prompt="$2" __val="${!1:-}"
  if [ -z "$__val" ]; then
    read -r -p "  $__prompt: " __val </dev/tty
  fi
  printf -v "$__var" '%s' "$__val"
}

[ "$(id -u)" -eq 0 ] || die "Run this with sudo (needs to install packages and create users)."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRETS_DIR="${SECRETS_DIR:-$SCRIPT_DIR}"
BEHIND_PROXY="${BEHIND_PROXY:-0}"

# --- gather the inputs the script needs ------------------------------------

step "Checking what's needed"

ask DOMAIN "Domain (e.g. example.com, no https:// and no 'grudge.' prefix)"
[ -n "$DOMAIN" ] || die "A domain is required."
FRONTEND_URL="https://grudge.${DOMAIN}"
BACKEND_URL="https://api.grudge.${DOMAIN}"

# The code must already be cloned to /opt/grudge (you do that yourself, with
# your own GitHub access - see the header). Everything downstream expects it
# exactly there, so check before doing anything.
if [ ! -e /opt/grudge/backend/pyproject.toml ]; then
  die "The code isn't at /opt/grudge yet. Clone it there first, with your own
  GitHub access, then run this script from it:
    sudo git clone <repo-url> /opt/grudge
    sudo DOMAIN=${DOMAIN} /opt/grudge/ops/install.sh"
fi

ENV_SRC="${SECRETS_DIR%/}/grudge.env"
RCLONE_SRC="${SECRETS_DIR%/}/rclone.conf"
[ -f "$ENV_SRC" ] || die "Can't find grudge.env in $SECRETS_DIR (set SECRETS_DIR to point at it)."
if [ ! -f "$RCLONE_SRC" ]; then
  warn "No rclone.conf in $SECRETS_DIR - off-site backup upload will be skipped."
  warn "Everything else still installs; add it later and re-run to finish backups."
fi

info "Website will be:  $FRONTEND_URL"
info "Backend will be:  $BACKEND_URL"
info "Code found at:    /opt/grudge"
[ "$BEHIND_PROXY" = "1" ] && info "Mode: behind an existing reverse proxy (Caddy serves plain http)."
printf '\n'
read -r -p "  Look right? Type yes to continue: " CONFIRM </dev/tty
[ "$CONFIRM" = "yes" ] || die "Cancelled - nothing was changed."

# ===========================================================================
# 2. Install the basics and build nsjail
# ===========================================================================
step "2/11  Installing packages and building the sandbox (nsjail)"

if command -v nsjail >/dev/null 2>&1; then
  info "nsjail already installed - skipping build."
else
  apt-get update
  apt-get install -y git curl python3-venv make gcc g++ pkg-config libprotobuf-dev \
    protobuf-compiler libnl-route-3-dev libcap-dev bison flex libnl-3-dev
  rm -rf /tmp/nsjail
  git clone --depth 1 https://github.com/google/nsjail.git /tmp/nsjail
  ( cd /tmp/nsjail && git submodule update --init --recursive && make -j"$(nproc)" )
  cp /tmp/nsjail/nsjail /usr/local/bin/nsjail
  info "nsjail built and installed at /usr/local/bin/nsjail."
fi

# ===========================================================================
# 3. Create the app's user and prepare the code
# ===========================================================================
step "3/11  Creating the grudge user and preparing the code"

id -u grudge >/dev/null 2>&1 \
  && info "User 'grudge' already exists - skipping." \
  || useradd --system --create-home --home-dir /home/grudge --shell /usr/sbin/nologin grudge

# The code is already at /opt/grudge (checked at the top). It was cloned by
# root (or whoever ran git clone); hand it to the grudge user the services
# run as. apt/git aren't needed for cloning here anymore, but the build below
# and other steps still need git/curl/python3-venv - installed in step 2.
info "Handing /opt/grudge to the grudge user."
chown -R grudge:grudge /opt/grudge

info "Creating the Python environment and installing the backend + engine..."
if [ ! -x /opt/grudge/backend/.venv/bin/python ]; then
  sudo -u grudge -H python3 -m venv /opt/grudge/backend/.venv
fi
sudo -u grudge -H bash -c 'cd /opt/grudge/backend && .venv/bin/pip install -q -e "../engine[dev]" -e .'

# ===========================================================================
# 4. Check the sandbox actually works - the go/no-go gate
# ===========================================================================
step "4/11  Testing the sandbox for real (this is the go/no-go check)"
info "Actively trying to break out of the sandbox - network, files, memory, other processes."

if sudo -u grudge -H bash -c 'cd /opt/grudge/engine && GRUDGE_TEST_NSJAIL=1 ../backend/.venv/bin/python -m pytest -m nsjail'; then
  info "Sandbox holds. Continuing."
else
  echo
  die "Sandbox test did NOT pass. Do not continue until this works.
  Most likely: container nesting is off (turn it on from the Proxmox host -
  see the top of this script), or nsjail isn't at /usr/local/bin/nsjail.
  'skipped' also counts as a failure here - the tests didn't actually run.
  If it still fails with nesting on, the fallback is a full VM, not a
  privileged container and not turning the sandbox off."
fi

# ===========================================================================
# 5. Put the two settings files in place
# ===========================================================================
step "5/11  Installing the settings files"

install -o root -g root -m 600 "$ENV_SRC" /etc/grudge.env
# Fill in the domain lines automatically, but only if they're still the CHANGEME
# placeholder - never clobber a value already set by hand.
sed -i "s|^FRONTEND_BASE_URL=https://CHANGEME.*|FRONTEND_BASE_URL=${FRONTEND_URL}|" /etc/grudge.env
sed -i "s|^BACKEND_BASE_URL=https://CHANGEME.*|BACKEND_BASE_URL=${BACKEND_URL}|" /etc/grudge.env
info "/etc/grudge.env installed (root-only), domain addresses set."

# Sanity-check the two settings that matter most for safety.
grep -q '^SANDBOX_BACKEND=nsjail' /etc/grudge.env \
  || die "SANDBOX_BACKEND is not 'nsjail' in grudge.env - refusing to continue with an unsafe sandbox setting."
grep -q '^MATCHMAKING_ROOM_CAPACITY_OVERRIDE=' /etc/grudge.env \
  && die "MATCHMAKING_ROOM_CAPACITY_OVERRIDE must not be set in production - remove it from grudge.env."
info "Safety settings look right (nsjail on, no test overrides)."

# Backup job's settings: from the template, with a freshly generated DB password.
if [ -f /etc/grudge-backup.env ]; then
  info "/etc/grudge-backup.env already exists - keeping it."
else
  install -o root -g root -m 600 /opt/grudge/ops/backup/grudge-backup.env.example /etc/grudge-backup.env
  BACKUP_PW="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
  sed -i "s|^PGPASSWORD=.*|PGPASSWORD=${BACKUP_PW}|" /etc/grudge-backup.env
  info "/etc/grudge-backup.env installed with a fresh backup-user password."
fi

# ===========================================================================
# 6. Install Postgres and create the database
# ===========================================================================
step "6/11  Installing Postgres and creating the database"

dpkg -s postgresql >/dev/null 2>&1 || apt-get install -y postgresql

# Pull the two passwords straight out of the settings files, so the database
# users are created with exactly the passwords the app and backup job will use
# - no re-typing, no chance of a mismatch.
APP_PW="$(python3 - "$ENV_SRC" <<'PY'
import sys, urllib.parse
for line in open(sys.argv[1]):
    line = line.strip()
    if line.startswith("DATABASE_URL="):
        url = line.split("=", 1)[1]
        print(urllib.parse.urlsplit(url).password or "")
        break
PY
)"
[ -n "$APP_PW" ] || die "Could not read the database password from DATABASE_URL in grudge.env."
BACKUP_PW="$(grep '^PGPASSWORD=' /etc/grudge-backup.env | cut -d= -f2-)"

psql_su() { sudo -u postgres psql -v ON_ERROR_STOP=1 "$@"; }

# App role + database (create only if missing - never resets an existing
# password). The password is passed as a psql variable and quoted with :'pw',
# which safely escapes any character - but that substitution only happens when
# psql reads from stdin/a file, NOT from -c, so these run via a here-doc.
if psql_su -tAc "SELECT 1 FROM pg_roles WHERE rolname='grudge'" | grep -q 1; then
  info "Role 'grudge' already exists - skipping."
else
  psql_su -v pw="$APP_PW" <<'SQL'
CREATE ROLE grudge LOGIN PASSWORD :'pw';
SQL
fi
if psql_su -tAc "SELECT 1 FROM pg_database WHERE datname='grudge'" | grep -q 1; then
  info "Database 'grudge' already exists - skipping."
else
  sudo -u postgres createdb -O grudge grudge
fi

# Read-only backup role.
if psql_su -tAc "SELECT 1 FROM pg_roles WHERE rolname='grudge_backup_ro'" | grep -q 1; then
  info "Role 'grudge_backup_ro' already exists - skipping."
else
  psql_su -v pw="$BACKUP_PW" <<'SQL'
CREATE ROLE grudge_backup_ro LOGIN PASSWORD :'pw';
SQL
fi

# Grants (safe to re-apply). Note FOR ROLE grudge, so tables the app creates in
# step 7 (and any future update) are readable by the backup automatically.
psql_su -d grudge <<'SQL'
GRANT CONNECT ON DATABASE grudge TO grudge_backup_ro;
GRANT USAGE ON SCHEMA public TO grudge_backup_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO grudge_backup_ro;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO grudge_backup_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE grudge IN SCHEMA public GRANT SELECT ON TABLES TO grudge_backup_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE grudge IN SCHEMA public GRANT SELECT ON SEQUENCES TO grudge_backup_ro;
SQL
info "Database, both users, and backup grants are set."

# ===========================================================================
# 7. Create the database tables
# ===========================================================================
step "7/11  Creating the database tables (migrations)"
# systemd-run hands the command the same settings file the services use, since
# the grudge user can't read /etc/grudge.env itself.
systemd-run --quiet --wait --pipe --uid=grudge \
  -p EnvironmentFile=/etc/grudge.env \
  -p WorkingDirectory=/opt/grudge/backend \
  /opt/grudge/backend/.venv/bin/alembic upgrade head
info "Tables created."

# ===========================================================================
# 8. Build the website
# ===========================================================================
step "8/11  Building the website"

if ! command -v node >/dev/null 2>&1 || [ "$(node -v | cut -d. -f1 | tr -d v)" -lt 20 ]; then
  info "Installing Node 24 (Ubuntu's own is too old for the build tools)..."
  curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
  apt-get install -y nodejs
fi

sudo -u grudge -H bash -c 'cd /opt/grudge/frontend && npm ci'
sudo -u grudge -H env VITE_API_BASE_URL="$BACKEND_URL" bash -c 'cd /opt/grudge/frontend && npm run build'

# The backend address is baked into the site at build time - confirm it went in.
if grep -l "api.grudge" /opt/grudge/frontend/dist/assets/*.js >/dev/null 2>&1; then
  info "Website built, backend address baked in correctly."
else
  die "Website built but the backend address didn't get baked in - check VITE_API_BASE_URL."
fi

# ===========================================================================
# 9. Start the app
# ===========================================================================
step "9/11  Starting the app services"
cp /opt/grudge/ops/deploy/grudge-backend.service \
   /opt/grudge/ops/deploy/grudge-worker.service \
   /opt/grudge/ops/deploy/grudge-watchdog.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now grudge-backend grudge-worker grudge-watchdog
sleep 2
if systemctl is-active --quiet grudge-backend grudge-worker grudge-watchdog; then
  info "All three services are running (they restart on their own after a crash or reboot)."
else
  systemctl status grudge-backend grudge-worker grudge-watchdog --no-pager || true
  die "One of the services didn't start - see the status above, then:
  journalctl -u grudge-backend -n 50 --no-pager  (swap in the failing name)."
fi

# ===========================================================================
# 10. Domain and HTTPS (Caddy)
# ===========================================================================
step "10/11  Installing Caddy (HTTPS / reverse proxy)"

if ! command -v caddy >/dev/null 2>&1; then
  apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
  apt-get update && apt-get install -y caddy
fi

# Build the Caddyfile from the template with the real subdomains filled in.
sed -e "s|grudge\.example\.com|grudge.${DOMAIN}|g" \
    -e "s|api\.grudge\.example\.com|api.grudge.${DOMAIN}|g" \
    /opt/grudge/ops/deploy/Caddyfile.example > /etc/caddy/Caddyfile
if [ "$BEHIND_PROXY" = "1" ]; then
  # Prefix both site addresses with http:// so Caddy serves plain HTTP on port
  # 80 and doesn't try to get its own certificates - your main proxy handles
  # HTTPS and forwards both subdomains here.
  sed -i -E "s|^(grudge\.${DOMAIN}) \{|http://\1 {|; s|^(api\.grudge\.${DOMAIN}) \{|http://\1 {|" /etc/caddy/Caddyfile
  warn "Behind-proxy mode: point your main reverse proxy at this container's port 80,"
  warn "keeping the original hostname and allowing WebSockets, for both subdomains."
fi
systemctl reload caddy || systemctl restart caddy
info "Caddy configured for grudge.${DOMAIN} and api.grudge.${DOMAIN}."
info "HTTPS certificates are issued automatically once DNS points here and ports 80/443 are open."

# ===========================================================================
# 11. Nightly backups
# ===========================================================================
step "11/11  Setting up nightly backups"

id -u grudge-backup >/dev/null 2>&1 \
  && info "User 'grudge-backup' already exists - skipping." \
  || useradd --system --create-home --home-dir /var/lib/grudge-backup --shell /usr/sbin/nologin grudge-backup
mkdir -p /var/backups/grudge
chown grudge-backup:grudge-backup /var/backups/grudge
chmod 700 /var/backups/grudge

# Prove the database side works before wiring up storage: one dump, no upload.
info "Testing a database dump (no upload)..."
rm -rf /tmp/grudge-backup-test
systemd-run --quiet --wait --pipe --uid=grudge-backup \
  -p EnvironmentFile=/etc/grudge-backup.env \
  -E SKIP_UPLOAD=1 -E BACKUP_DIR=/tmp/grudge-backup-test \
  /opt/grudge/ops/backup/backup_db.sh
rm -rf /tmp/grudge-backup-test
info "Database dump works."

if [ -f "$RCLONE_SRC" ]; then
  command -v rclone >/dev/null 2>&1 || { apt-get install -y unzip; curl https://rclone.org/install.sh | bash; }
  mkdir -p /var/lib/grudge-backup/.config/rclone
  install -o grudge-backup -g grudge-backup -m 600 "$RCLONE_SRC" /var/lib/grudge-backup/.config/rclone/rclone.conf
  RCLONE_REMOTE="$(grep '^RCLONE_REMOTE=' /etc/grudge-backup.env | cut -d= -f2-)"
  info "Checking off-site storage is reachable (${RCLONE_REMOTE})..."
  if sudo -u grudge-backup -H rclone lsd "${RCLONE_REMOTE%%:*}:" >/dev/null 2>&1; then
    info "Off-site storage reachable."
  else
    warn "Could not reach off-site storage - check rclone.conf and RCLONE_REMOTE, then re-run."
  fi
  cp /opt/grudge/ops/backup/grudge-backup.service /opt/grudge/ops/backup/grudge-backup.timer /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable --now grudge-backup.timer
  info "Nightly backup timer is on."
else
  warn "Skipped off-site backup setup (no rclone.conf). Add it and re-run to finish."
fi

# ===========================================================================
# Done
# ===========================================================================
step "Done - server side is set up"
cat <<EOF

  What's left, and only you can do it (see README.md sections 1 & 2):

    * DNS: point  grudge.${DOMAIN}  and  api.grudge.${DOMAIN}  at this
      server's public IP, and make sure ports 80 and 443 reach this container.
      HTTPS certificates appear on their own once that's live.

    * Google: add this sign-in address in Google Cloud Console:
        ${BACKEND_URL}/auth/google/callback

    * Then test it end to end: open ${FRONTEND_URL}, sign in with Google,
      write an automaton, and run a sim tournament through to the results page.
      (Until the app is published, only Google 'test users' can sign in.)

  Useful checks:
    systemctl status grudge-backend grudge-worker grudge-watchdog --no-pager
    journalctl -u grudge-backend -n 50 --no-pager

EOF
