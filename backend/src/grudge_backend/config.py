from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_DEFAULT_SECRET = "dev-only-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://grudge:grudge_dev_password@localhost:5432/grudge_dev"

    # Signs the short-lived OAuth state/PKCE cookie (Starlette SessionMiddleware) -
    # unrelated to the long-lived login session, which is a random token hashed
    # into the `sessions` table, never a signed/decodable value.
    oauth_state_secret: str = "dev-only-change-me"

    google_client_id: str = ""
    google_client_secret: str = ""

    frontend_base_url: str = "http://localhost:5173"
    # The backend's public address - what browsers and Google see (the OAuth
    # redirect URI is built from it).
    backend_base_url: str = "http://localhost:8000"
    # Where the worker/watchdog reach the web process for /internal/* relays
    # (services/progress_relay.py) - always the address uvicorn itself listens
    # on, never the public backend_base_url. In production the public address
    # would send every live progress update out through the internet and back
    # in, which fails outright on networks without NAT loopback (common for
    # home servers). Matches both backend/README.md's dev uvicorn command and
    # ops/deploy/grudge-backend.service.
    internal_base_url: str = "http://127.0.0.1:8000"

    session_cookie_name: str = "grudge_session"
    session_ttl_days: int = 30
    # False in dev (plain http://localhost); must be True wherever the app is
    # actually served over https.
    cookie_secure: bool = False

    # Shared secret checked on POST /internal/* - the worker/watchdog (separate
    # OS processes from the web process, per CLAUDE.md S3) call these to relay
    # realtime events into the web process's in-memory WebSocket connections;
    # never browser-facing, so this is not user auth.
    internal_shared_secret: str = "dev-only-change-me"

    # Dev alerting for watchdog-detected stalls (CLAUDE.md S3: "a Discord
    # webhook to a private channel"). Empty in dev = alerts are skipped, not
    # errored on.
    discord_webhook_url: str = ""

    # Which grudge_engine sandbox backend worker.py uses to run automaton code:
    # "dev" (DevSandboxBackend - plain subprocess.Popen, no OS-level isolation,
    # dev/test-only) or "nsjail" (NsjailSandboxBackend - real OS-level
    # isolation, Linux/WSL2 only). MUST be "nsjail" before any real user code
    # reaches this worker - see TODO.md's "Worker's sandbox backend" item.
    # Defaults to "dev" so local development on native Windows (where nsjail
    # can't run at all) keeps working without extra setup; production sets
    # SANDBOX_BACKEND=nsjail in its environment/.env (no GRUDGE_ prefix, same
    # as every other setting here - see .env.example).
    sandbox_backend: str = "dev"

    # Test-only: shrinks the ranked/unranked matchmaking room capacity (normally
    # 4, see services/matchmaking.py's RANKED_ROOM_SIZE/UNRANKED_ROOM_SIZE) so an
    # automated test can fill a room with a couple of simulated joins instead of
    # 4, to exercise /ws/matchmaking/queue/{id} - see TODO.md's "deactivate
    # before publishing" flag. MUST be unset (None) in any real deployment: a
    # live room capped below 4 would start ranked/unranked tournaments with the
    # wrong number of players. None (unset) is a no-op - matchmaking.py falls
    # back to the real 4-player size.
    matchmaking_room_capacity_override: int | None = None

    @model_validator(mode="after")
    def _reject_dev_secrets_in_production(self) -> Settings:
        # cookie_secure=True is already this codebase's own signal for "this
        # is a real deployment, not local dev" (it's set from the deploy env
        # file, never true by default - see cookie_secure's own comment).
        # Piggybacking on it here means a deploy that forgets to set
        # OAUTH_STATE_SECRET/INTERNAL_SHARED_SECRET fails to even start,
        # rather than silently running with a publicly-known secret - the
        # OAuth-state cookie becomes forgeable, and so does every
        # /internal/* request (see routers/internal.py).
        if self.cookie_secure:
            leaked = [
                name
                for name, value in (
                    ("OAUTH_STATE_SECRET", self.oauth_state_secret),
                    ("INTERNAL_SHARED_SECRET", self.internal_shared_secret),
                )
                if value == _DEV_DEFAULT_SECRET
            ]
            if leaked:
                raise ValueError(
                    f"{', '.join(leaked)} still has the dev default value "
                    f"({_DEV_DEFAULT_SECRET!r}) while COOKIE_SECURE=true (production "
                    "mode) - generate real values before deploying."
                )
        return self


settings = Settings()
