"""Shared sandbox-backend construction. Extracted out of worker.py (Phase 6)
so the FastAPI web process can build a real sandbox backend too - needed for
pre-flight checks run synchronously inside a queue-join HTTP request
(services/preflight.py) - without importing worker.py itself, which pulls in
job-polling/heartbeat machinery the web process has no business touching.

Which grudge_engine backend actually runs automaton code is controlled by
`settings.sandbox_backend` ("dev" or "nsjail" - see config.py), defaulting to
"dev" (DevSandboxBackend, insecure, dev-only) so native-Windows local dev
keeps working without nsjail installed. Swapping to nsjail in production is
just setting SANDBOX_BACKEND=nsjail in the environment (see engine/README.md's
documented backend-swap property) - but that swap **must actually happen**
before any real user code reaches either this or the worker; tracked in
TODO.md so it isn't silently forgotten. `build_sandbox_backend` fails loudly
(raises, doesn't silently fall back to dev) on an unknown value or on
"nsjail" where no nsjail binary is actually available.
"""

from __future__ import annotations

from grudge_engine.sandbox.base import SandboxBackend
from grudge_engine.sandbox.dev_backend import DevSandboxBackend
from grudge_engine.sandbox.nsjail_backend import NsjailSandboxBackend

from grudge_backend.config import settings


def build_sandbox_backend() -> SandboxBackend:
    backend_name = settings.sandbox_backend
    if backend_name == "dev":
        return DevSandboxBackend()
    if backend_name == "nsjail":
        return NsjailSandboxBackend()  # raises RuntimeError if nsjail isn't on PATH
    raise ValueError(f"Unknown SANDBOX_BACKEND {backend_name!r} - expected 'dev' or 'nsjail'.")
