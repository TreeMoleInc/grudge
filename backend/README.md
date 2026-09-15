# grudge-backend

Phases 2+3 of Grudge: Postgres schema, OAuth auth, CRUD APIs for
automata/folders/versions (Phase 2), plus waiting-room/matchmaking, sim rooms,
and the job-queue/worker/watchdog that actually runs tournaments via the real
`grudge_engine` (Phase 3). See the repo root [CLAUDE.md](../CLAUDE.md) for the
full product spec and [the phased build plan](../CLAUDE.md#4-phased-build-plan).
No frontend yet, and no relational match history/rating updates yet (Phase 6) -
see TODO.md's "Phase 3/6 scope line" item.

## Dev environment: native Windows backend + WSL2-hosted Postgres

Unlike `engine/`'s `nsjail` tier, Postgres has no OS-level requirement forcing
WSL2 - `backend/` runs its venv, `alembic`, and `pytest` **natively on Windows**,
connecting to a Postgres server that runs inside WSL2/Ubuntu 24.04 over
`localhost:5432` (WSL2's default bidirectional `localhost` port-forwarding).
This is simpler than duplicating the checkout into WSL2's native filesystem
(what `engine/`'s `nsjail` tier has to do, since `pip install -e` itself fails
on `/mnt/c/...` DrvFs paths) - `backend/` never runs `pip install` *inside*
WSL2 at all, so that bug never comes up here.

**The one real gotcha: WSL2's lightweight VM shuts down when nothing keeps a
session attached to it**, taking Postgres down with it (confirmed via
`journalctl -u postgresql`, which showed the VM repeatedly rebooting every
1-2 minutes - each gap between tool invocations was long enough for it to shut
down and get freshly restarted by the next `wsl` command, killing every
in-flight Postgres connection). `.wslconfig`'s `[wsl2]` `vmIdleTimeout=-1`
(this repo's `C:\Users\<you>\.wslconfig`) is *supposed* to disable this but
didn't reliably prevent it in testing. **What actually works:** keep one
`wsl` process attached for the duration of a dev/test session, e.g. in its own
terminal:
```bash
wsl -d Ubuntu-24.04 -- sleep infinity
```
With that running, Postgres stays reachable indefinitely and the full
integration suite (which briefly failed with `ConnectionRefusedError`/
"connection closed in the middle of operation" before this was diagnosed) runs
in under 10 seconds. If you ever see either of those errors again mid-session,
it means nothing was holding WSL2 open - check `wsl -l -v` (state should say
`Running`, not `Stopped`) and start a keep-alive session.

**One-time environment setup already done on this machine's WSL2/Ubuntu 24.04**
(documented here so a fresh machine/distro can repeat it - general WSL2/Ubuntu
health, nothing backend-specific):
- **DNS**: WSL2's built-in DNS proxy was returning only unreachable IPv6 records
  for some hosts, breaking `apt`/`pip`. Fixed by pointing `systemd-resolved` at
  public DNS directly (`/etc/systemd/resolved.conf`: `DNS=8.8.8.8 1.1.1.1`, then
  `systemctl restart systemd-resolved`) - editing `/etc/resolv.conf` directly
  does NOT stick, since `systemd-resolved` manages that file as a symlink and
  regenerates it on boot regardless of `wsl.conf`'s `generateResolvConf=false`
  (that setting only stops *WSL's own* generator, a separate thing).
- **IPv6**: even with working DNS, IPv6 routing itself was unreliable
  (`archive.ubuntu.com`/`pypi.org` returned IPv6-only or IPv6-first records that
  then hung/timed out instead of failing fast). Disabled outright via
  `/etc/sysctl.d/99-disable-ipv6.conf` (`net.ipv6.conf.*.disable_ipv6 = 1`) -
  forces IPv4, which works fine on this network.
- **Postgres**: `sudo apt-get install postgresql postgresql-contrib`, then a
  `grudge` role + `grudge_dev`/`grudge_test` databases (see below).

**Alternative, if `localhost` forwarding itself is ever the problem** (a
different failure mode than the VM-shutdown gotcha above - genuinely flaky
routing rather than "nothing's listening at all"): the whole backend can also
run natively inside WSL2 instead, same pattern as `engine/`'s WSL2 tier. A
working copy is already set up at `~/grudge-backend` (synced from this
checkout) with its own venv at `~/grudge-backend-venv`:
```bash
rsync -a --delete /mnt/c/Users/Josep/Documents/Personal/Python/Projects/Grudge/backend/ ~/grudge-backend/ --exclude .venv
cd ~/grudge-backend && ~/grudge-backend-venv/bin/python -m pytest -v
```

## Setup

On Windows, from `backend/`:

```bash
python -m venv .venv
.venv\Scripts\activate       # Windows; use `source .venv/bin/activate` on Linux/WSL2
pip install -e ../engine -e .[dev]   # grudge-engine is a real dep as of Phase 3 (the worker calls it directly)
cp .env.example .env         # DATABASE_URL etc. - defaults already point at grudge_dev
```

Inside WSL2/Ubuntu (one-time, creates the roles/databases the `.env` defaults
point at):

```bash
sudo -u postgres psql -c "CREATE ROLE grudge WITH LOGIN PASSWORD 'grudge_dev_password';"
sudo -u postgres psql -c "CREATE DATABASE grudge_dev OWNER grudge;"
sudo -u postgres psql -c "CREATE DATABASE grudge_test OWNER grudge;"
```

## Running things

From `backend/` on Windows (with a WSL2 keep-alive session running, per above):

```bash
alembic upgrade head        # apply migrations to grudge_dev
pytest -v                   # unit tier only (no DB needed)
GRUDGE_TEST_DATABASE_URL='postgresql+asyncpg://grudge:grudge_dev_password@localhost:5432/grudge_test' pytest -v   # unit + integration
uvicorn grudge_backend.main:app --host 127.0.0.1 --port 8000
python -m grudge_backend.worker     # separate process - claims queued jobs, runs tournaments for real
python -m grudge_backend.watchdog   # separate process - fails stale jobs, matchmaking sweeps, Discord alerts
```

**Don't pass `--reload` on Windows.** Its multiprocess reload architecture spawns a
separate server-child process; if that child (or the reloader itself) is later killed
externally rather than via its own Ctrl+C-driven shutdown - e.g. a script or another
tool tearing it down - Windows does not cascade-terminate the child the way a POSIX
process group would. The orphan keeps holding the port and keeps answering some
fraction of requests with whatever code was live when it was born, invisible to
`tasklist`/`Get-Process` filtered by the parent's command line (the orphan's own
command line is a generic `multiprocessing.spawn_main(parent_pid=...)`, matching
nothing you'd think to search for). Symptom: after editing and restarting, some
requests reflect the new code and some silently don't, with no error anywhere. If
you need hot-reload, use it, but confirm you're killing the *entire* process tree
(`Get-CimInstance Win32_Process | Where-Object Name -like 'python*'`, not just
anything matching "uvicorn") before trusting a restart actually took effect.

The worker and watchdog both need the web process (`uvicorn`) running too, since
they relay realtime events to it over `POST /internal/tournaments/{id}/progress`
(`INTERNAL_BASE_URL` - defaults to `http://127.0.0.1:8000`, matching the `uvicorn`
command above; deliberately separate from the public `BACKEND_BASE_URL`, see
`config.py`) - see CLAUDE.md §6 for why this internal-HTTP-callback shape was
chosen over Postgres `LISTEN`/`NOTIFY`.

`GRUDGE_TEST_DATABASE_URL` is deliberately separate from the app's own runtime
`DATABASE_URL` (set via `.env`) - integration tests are gated on it being set,
mirroring `engine/`'s `GRUDGE_TEST_NSJAIL=1` gating pattern for its WSL2-only
tier, and it points at `grudge_test` specifically so tests never touch dev data.

Migrations are applied to `GRUDGE_TEST_DATABASE_URL` automatically once per test
session (`tests/conftest.py`'s `_migrated_schema` fixture) - no separate manual
step needed before running the integration tier.

## Testing notes

- **Unit tier** (`tests/unit/`): schema validation, the folder-cycle-detection
  algorithm (tested via an in-memory parent lookup, not a real DB - see
  `services/folders.py`'s `find_cycle`), and OAuth userinfo-parsing. Runs
  anywhere, no DB.
- **Integration tier** (`tests/integration/`): real FastAPI app over `httpx`,
  real migrated Postgres. Each test runs inside a savepoint-per-test
  transaction that's always rolled back (SQLAlchemy 2.0's
  `join_transaction_mode="create_savepoint"`) - no truncation needed, and
  endpoint code calling `commit()` doesn't leak state across tests.
- **OAuth coverage, three layers**: `fetch_google_user`'s provider-response
  parser is unit-tested with fakes (`tests/unit/test_oauth_providers.py`); the
  upsert logic (`_login_or_create_user`) is tested directly against a real DB
  (`tests/integration/test_auth_flow.py`); and `tests/integration/test_oauth_e2e.py`
  drives the real `/auth/google/login` → callback endpoints end to end with
  `respx`-mocked provider HTTP calls, including a real RS256-signed `id_token`
  for Google (generated with a locally-created test RSA key, verified by Authlib
  against a mocked `jwks_uri` - genuine OIDC signature verification, not a stub)
  - this is what actually validates the real Authlib wiring (state, nonce, PKCE,
  token exchange, OIDC discovery) rather than just this project's own code
  around it.
- **Phase 3 coverage**: `tests/unit/test_matchmaking.py` (pure window/spread math,
  no DB/sleeps - explicit `elapsed_seconds`/`now` params, same
  injectable-determinism philosophy as `engine/`'s `seed` param);
  `tests/integration/test_matchmaking_api.py` (real HTTP room-fill, incl. the
  ranked window keeping far-apart players in separate rooms at join time);
  `tests/integration/test_worker.py` (the real `grudge_engine.tournament_runner.
  run_tournament` call end-to-end, via `worker.process_job` called directly
  rather than the real polling loop - see that function's docstring);
  `tests/integration/test_watchdog.py` (stale-job detection, Discord webhook
  mocked via `respx`); `tests/integration/test_sim_rooms_api.py`.
- **Testability fix worth knowing about**: `worker.py`/`watchdog.py`'s DB-touching
  functions (`process_job`, `handle_stale_jobs`, etc.) take an injectable
  `session_maker` parameter (default: the real `async_session_maker`, which opens
  genuinely separate DB connections). Tests pass `worker_session_maker` (a
  conftest fixture) instead, which always returns the *same* savepoint-bound
  `db_session` - without this, the worker/watchdog's separate connections
  wouldn't see a test's uncommitted fixture data at all (this was a real bug
  caught while writing these tests, not a hypothetical).
- **Known gap: no automated WebSocket tests.** `/ws/matchmaking/queue/{id}`,
  `/ws/sim-rooms/{id}`, and `/ws/tournaments/{id}/progress` are implemented and
  were manually verified end-to-end (a real `uvicorn` + worker run against
  `grudge_dev`, confirmed via the server's own request log), but
  `httpx.ASGITransport` doesn't implement the WebSocket upgrade handshake (a GET
  to a ws-only route just 404s - confirmed while attempting this), and
  Starlette's `TestClient` (which does support WS) runs the app in a separate
  thread/event loop that would break this suite's shared savepoint-bound
  `AsyncSession`. See TODO.md.

## Layout

See the repo root CLAUDE.md §6 (Conventions) for the established package layout
and testing approach.
