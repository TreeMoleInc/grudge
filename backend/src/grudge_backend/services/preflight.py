"""Pre-flight gating for ranked/unranked queue-join (CLAUDE.md S3/Phase 6).
Runs fresh, synchronously, on every join attempt - no caching/staleness
column on automaton_versions (a deliberate choice: matches CLAUDE.md's literal
"runs before... enters a live tournament" wording, and avoids
invalidation-on-edit complexity entirely). Sim rooms are NOT gated by this -
only the ranked/unranked queue-join path (services/matchmaking.py:join_queue).

Reuses grudge_engine.preflight.run_preflight exactly as-is - the same sandbox
path a live match uses (CLAUDE.md: "no separate, looser standard"), just
called from the web process this time via sandbox.build_sandbox_backend()
instead of from worker.py.
"""

from __future__ import annotations

from grudge_engine.automaton import Automaton
from grudge_engine.preflight import run_preflight
from grudge_engine.results import PreflightResult

from grudge_backend.sandbox import build_sandbox_backend


class NoActiveVersionError(Exception):
    pass


class PreflightFailedError(Exception):
    def __init__(self, reason: str | None):
        self.reason = reason
        super().__init__(reason or "Automaton failed the pre-flight check.")


def run_preflight_check(*, automaton_id: str, code: str) -> PreflightResult:
    """Synchronous, blocking (real subprocess I/O under the hood) - callers on
    the async web event loop MUST wrap this in asyncio.to_thread, exactly like
    worker.py already wraps run_tournament(...).
    """
    return run_preflight(Automaton(id=automaton_id, source=code), build_sandbox_backend())
