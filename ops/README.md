# ops/

Everything needed to run Grudge on its production server: the app itself
(`deploy/`) and nightly database backups (`backup/`). Nothing here has run in
production yet.

**Assumes** Ubuntu 24.04 or newer, in an unprivileged Proxmox LXC container.
Every command is already written — run them as they are, top to bottom.
Commands use `sudo`; if the container doesn't have it yet, install it first as
root with `apt install -y sudo`.

Placeholders: `<domain>` is the domain the two subdomains live under,
`<repo-url>` is the GitHub repo's address, and `<container-id>` is the
container's Proxmox ID.

The real settings file, `grudge.env`, is sent separately — never through git,
because it holds real passwords.

## Fastest path: the install script

`install.sh` does every step below that happens **on the container**, in order,
so you don't have to run them by hand. First, clone the code to `/opt/grudge`
with your own GitHub access, and put the two files sent to you privately —
`grudge.env` and `rclone.conf` — in `/opt/grudge/ops` next to the script:

```bash
sudo git clone <repo-url> /opt/grudge
# then copy grudge.env and rclone.conf into /opt/grudge/ops
sudo DOMAIN=<domain> /opt/grudge/ops/install.sh
```

It asks for the domain if you don't pass it, stops immediately if the sandbox
check fails, and is safe to run again if it stops partway. It still can't do the
things that live outside the container — turn on container nesting from the
Proxmox host (step 1 below), point DNS at this server, and add the Google
sign-in address (steps 1, 10, and the testing section) — so do those too. The
numbered steps below are what the script runs; read them if a step fails or
you'd rather do it by hand.

## 1. Transfer — get it running

Steps 1–4 are the go/no-go check. If step 4 fails, stop there: nothing after it
is worth doing until the sandbox works.

### 1. Turn on nesting for the container

On the Proxmox **host**, not inside the container:

```bash
pct set <container-id> --features nesting=1
pct reboot <container-id>
```

The sandbox (`nsjail`) builds a small container of its own around every
player's code, and unprivileged containers block that unless nesting is on.
If `pct config <container-id>` already shows a `features:` line, keep what's
there and add nesting to it (e.g. `--features keyctl=1,nesting=1`) — this
setting replaces the whole list.

### 2. Install the basics and build nsjail

```bash
sudo apt update
sudo apt install -y git curl python3-venv make gcc g++ pkg-config libprotobuf-dev \
    protobuf-compiler libnl-route-3-dev libcap-dev bison flex libnl-3-dev
git clone --depth 1 https://github.com/google/nsjail.git /tmp/nsjail
cd /tmp/nsjail && git submodule update --init --recursive && make -j"$(nproc)"
sudo cp /tmp/nsjail/nsjail /usr/local/bin/nsjail
```

There's no ready-made nsjail package for Ubuntu, so it's built from source
(same commands as `engine/README.md`).

### 3. Create the app's user and download the code

```bash
sudo useradd --system --create-home --home-dir /home/grudge --shell /usr/sbin/nologin grudge
sudo git clone <repo-url> /opt/grudge
sudo chown -R grudge:grudge /opt/grudge
cd /opt/grudge/backend
sudo -u grudge -H python3 -m venv .venv
sudo -u grudge -H .venv/bin/pip install -e '../engine[dev]' -e .
```

- The repo is private: when `git clone` asks, sign in with a GitHub username
  and a personal access token that can read it.
- The code lives in `/opt/grudge`, and the user's own home folder is separate
  (`/home/grudge`). Keep them apart: Ubuntu makes new home folders private, and
  the web server and the backup job both need to read the code folder.
- The engine is installed straight from its folder in the repo (`../engine`) —
  it isn't published anywhere else. `[dev]` adds the test tools step 4 needs.

### 4. Check the sandbox actually works — stop here if it doesn't

```bash
sudo -u grudge -H bash -c 'cd /opt/grudge/engine && GRUDGE_TEST_NSJAIL=1 ../backend/.venv/bin/python -m pytest -m nsjail'
```

This runs the sandbox for real, as the same user the app runs as, and actively
tries to break out of it: reach the network, write files, use too much memory,
see other processes, and connect to other programs on the server (the way the
database is reached). Read the last line:

- **`N passed`** (plus some number `deselected`, which is fine) — carry on.
- **Anything `failed` or `error`** — stop. The sandbox doesn't hold here.
- **Anything `skipped`** — also stop. The tests didn't actually run, usually
  because `nsjail` isn't at `/usr/local/bin/nsjail`. Skipped is not a pass.

If it fails even with nesting on, the fallback is a full VM instead of a
container — not a privileged container, and not switching the sandbox off.

### 5. Put the two settings files in place

The app's settings, from the `grudge.env` file sent separately:

```bash
sudo mv grudge.env /etc/grudge.env
sudo chown root:root /etc/grudge.env
sudo chmod 600 /etc/grudge.env
sudo nano /etc/grudge.env
```

Change the two `https://CHANGEME` lines to the real addresses:

```
FRONTEND_BASE_URL=https://grudge.<domain>
BACKEND_BASE_URL=https://api.grudge.<domain>
```

The backup job's settings, from the template, with a fresh password for its
database user:

```bash
sudo cp /opt/grudge/ops/backup/grudge-backup.env.example /etc/grudge-backup.env
sudo chmod 600 /etc/grudge-backup.env
python3 -c "import secrets; print(secrets.token_hex(24))"
sudo nano /etc/grudge-backup.env
```

Paste that random value in as `PGPASSWORD`. Leave `RCLONE_REMOTE` for step 11.

Both files are readable by root only, on purpose. The services still get their
values — systemd reads the files for them — but the `grudge` user can't read
them, and player code in the sandbox runs as that user, so it can't reach the
passwords either.

### 6. Install Postgres and create the database

```bash
sudo apt install -y postgresql
sudo -u postgres psql
```

Then paste this into `psql` with both passwords filled in. The app's is already
inside `/etc/grudge.env` (in `DATABASE_URL`, between `grudge:` and
`@localhost`); the backup's is the `PGPASSWORD` from step 5.

```sql
CREATE ROLE grudge WITH LOGIN PASSWORD '<password from /etc/grudge.env>';
CREATE DATABASE grudge OWNER grudge;
CREATE ROLE grudge_backup_ro WITH LOGIN PASSWORD '<PGPASSWORD from /etc/grudge-backup.env>';
\c grudge
GRANT CONNECT ON DATABASE grudge TO grudge_backup_ro;
GRANT USAGE ON SCHEMA public TO grudge_backup_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO grudge_backup_ro;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO grudge_backup_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE grudge IN SCHEMA public GRANT SELECT ON TABLES TO grudge_backup_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE grudge IN SCHEMA public GRANT SELECT ON SEQUENCES TO grudge_backup_ro;
\q
```

- Two database users on purpose: the app can write, the backup job can only
  read.
- Everything after `\c grudge` has to run inside the `grudge` database — `\c`
  is what switches to it.
- `FOR ROLE grudge` makes every table the app creates later (step 7, and any
  future update) readable by the backup automatically. Without it, backups work
  at first, then fail the first time an update adds a table.

### 7. Create the database tables

```bash
sudo systemd-run --quiet --wait --pipe --uid=grudge -p EnvironmentFile=/etc/grudge.env -p WorkingDirectory=/opt/grudge/backend /opt/grudge/backend/.venv/bin/alembic upgrade head
```

The database starts completely empty — no dev/test data comes along.
`systemd-run` hands the command the same settings file the services get, since
the `grudge` user can't read that file itself.

### 8. Build the website

Ubuntu's own Node.js is too old for the build tools (they need 20.19 or newer),
so install Node 24 from NodeSource first:

```bash
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
sudo apt install -y nodejs
cd /opt/grudge/frontend
sudo -u grudge -H npm ci
sudo -u grudge -H env VITE_API_BASE_URL=https://api.grudge.<domain> npm run build
```

`VITE_API_BASE_URL` is baked into the website when it's built. Without it, the
site loads but can't talk to the backend — every request would go to
`localhost` on the visitor's own computer. Check it went in (this should print
at least one file name):

```bash
grep -l "api.grudge" /opt/grudge/frontend/dist/assets/*.js
```

### 9. Start the app

```bash
sudo cp /opt/grudge/ops/deploy/grudge-backend.service /opt/grudge/ops/deploy/grudge-worker.service /opt/grudge/ops/deploy/grudge-watchdog.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now grudge-backend grudge-worker grudge-watchdog
systemctl status grudge-backend grudge-worker grudge-watchdog --no-pager
```

All three should show `active (running)`. They restart on their own after a
crash or a reboot. If one isn't running, its log says why:
`journalctl -u grudge-worker -n 50 --no-pager` (swap in the service's name).

### 10. Domain and HTTPS

Two DNS records, both pointing at this server's public IP address:
`grudge.<domain>` (the website) and `api.grudge.<domain>` (the backend). Two
rather than one because the backend's routes aren't all under one shared path,
so splitting by subdomain needs no code changes. Ports 80 and 443 have to reach
this container — the HTTPS certificates are issued over them.

Install Caddy, a web server that handles HTTPS certificates automatically:

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

(On anything other than Debian/Ubuntu, grab a static binary from
https://caddyserver.com/download instead.)

Put the config in place, change both `grudge.example.com` addresses to the real
subdomains, and reload:

```bash
sudo cp /opt/grudge/ops/deploy/Caddyfile.example /etc/caddy/Caddyfile
sudo nano /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

**Already have a reverse proxy handling HTTPS for all your containers?** Still
install Caddy here, but put `http://` in front of both addresses in
`/etc/caddy/Caddyfile` (e.g. `http://grudge.<domain> {`) so it doesn't try to
get certificates of its own. Then have your main proxy forward both subdomains
to this container's port 80, keeping the original hostname and allowing
WebSockets.

### 11. Set up nightly backups

A separate user for the backup job, and a private folder for the local copies
(they contain every player's data, so only that user can open it):

```bash
sudo useradd --system --create-home --home-dir /var/lib/grudge-backup --shell /usr/sbin/nologin grudge-backup
sudo mkdir -p /var/backups/grudge
sudo chown grudge-backup:grudge-backup /var/backups/grudge
sudo chmod 700 /var/backups/grudge
```

Before setting up storage, check the database side works. This makes one dump
without uploading it:

```bash
sudo systemd-run --quiet --wait --pipe --uid=grudge-backup -p EnvironmentFile=/etc/grudge-backup.env -E SKIP_UPLOAD=1 -E BACKUP_DIR=/tmp/grudge-backup-test /opt/grudge/ops/backup/backup_db.sh
sudo rm -rf /tmp/grudge-backup-test
```

It should end with `SKIP_UPLOAD=1, leaving dump local only`.

Now the off-site storage. The account and bucket already exist (Cloudflare R2)
— install rclone, then put the real `rclone.conf` file (sent separately,
same as `grudge.env`) in place for the `grudge-backup` user:

```bash
sudo apt install -y unzip
curl https://rclone.org/install.sh | sudo bash
sudo mkdir -p /var/lib/grudge-backup/.config/rclone
sudo mv rclone.conf /var/lib/grudge-backup/.config/rclone/rclone.conf
sudo chown -R grudge-backup:grudge-backup /var/lib/grudge-backup/.config
sudo chmod 600 /var/lib/grudge-backup/.config/rclone/rclone.conf
```

Check it can actually see the bucket:

```bash
sudo -u grudge-backup -H rclone lsd r2:grudge-backups
```

That should print the bucket with no error. (Setting up storage from scratch
instead — a different provider, or a second one? Run
`sudo -u grudge-backup -H rclone config` instead, an interactive wizard, and
use `ops/backup/rclone.conf.example` as a shape reference. Whatever the
remote ends up named, `RCLONE_REMOTE` below has to match it.)

`RCLONE_REMOTE` in `/etc/grudge-backup.env` is already set to
`r2:grudge-backups`, matching the real `rclone.conf`'s remote name — confirm
it, then turn on the nightly timer:

```bash
sudo nano /etc/grudge-backup.env
sudo cp /opt/grudge/ops/backup/grudge-backup.service /opt/grudge/ops/backup/grudge-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now grudge-backup.timer
```

It runs every night, and catches up on a missed night if the server was off.

## 2. Testing — prove it actually works

Setup finishing isn't the same as it working. Each of these has to pass.

### Sign in and play a full match

Open `https://grudge.<domain>`, sign in with Google, write an automaton, and run
a sim tournament from start to finish. The processing screen should move on to
the results page by itself.

This is the check that proves the sandbox is really in use, not just switched on
in a settings file — a wrong sandbox setting makes tournaments fail loudly
rather than quietly run unprotected. Until the app is published, Google only
lets accounts added as test users sign in, so use one of those.

### Trigger a real backup and check it arrived

```bash
sudo systemctl start grudge-backup.service
journalctl -u grudge-backup.service -n 20 --no-pager
sudo -u grudge-backup -H rclone ls <RCLONE_REMOTE value>
```

The log should end with `uploaded to …`, and the dump should show up in the
storage listing.

### Restore that backup into a scratch database

An untested backup isn't a backup. Find the newest dump's name with
`sudo ls /var/backups/grudge`, then:

```bash
sudo -u postgres createdb -O grudge grudge_restore_test
sudo gunzip -c /var/backups/grudge/grudge_<timestamp>.sql.gz | sudo -u postgres psql -v ON_ERROR_STOP=1 -d grudge_restore_test -c 'SET ROLE grudge' -f -
sudo -u postgres psql -d grudge_restore_test -c 'SELECT count(*) FROM users;'
sudo -u postgres dropdb grudge_restore_test
```

The count should match the number of accounts that have signed in so far.
`SET ROLE grudge` loads the backup as the app's own database user, so the app
owns the restored tables — backups don't record who owns what. Worth repeating
every now and then, not just once.

## 3. Reference — not tasks, just good to know

### Restoring for real

Same as the test above, then swap it in for the live database:

```bash
sudo systemctl stop grudge-backend grudge-worker grudge-watchdog
sudo -u postgres createdb -O grudge grudge_restored
sudo gunzip -c /var/backups/grudge/grudge_<timestamp>.sql.gz | sudo -u postgres psql -v ON_ERROR_STOP=1 -d grudge_restored -c 'SET ROLE grudge' -f -
sudo -u postgres psql -c 'ALTER DATABASE grudge RENAME TO grudge_old;' -c 'ALTER DATABASE grudge_restored RENAME TO grudge;'
sudo systemctl start grudge-backend grudge-worker grudge-watchdog
```

Then re-run the backup user's permission lines from Transfer step 6 (from
`\c grudge` down, inside `sudo -u postgres psql`). Backups don't store
permissions, so without this the next night's backup fails. Once everything
looks right, remove the old copy: `sudo -u postgres dropdb grudge_old`.

Restoring into a new database and then swapping names is safer than restoring
on top of the live one: if anything goes wrong, the old database is still there.

If the server itself is gone, set up a new one with the Transfer steps, then
download a dump from the storage before restoring:
`sudo -u grudge-backup -H rclone copy <RCLONE_REMOTE value>/grudge_<timestamp>.sql.gz /tmp/`

### How long backups stick around

The server keeps the newest 7 dumps (set `KEEP_DAILY` in
`/etc/grudge-backup.env` to change that). Off-site copies are only ever deleted
by the storage provider's own settings — e.g. a bucket rule that deletes files
after 30 days — not by anything in this project, so set that rule up or they
pile up forever.
