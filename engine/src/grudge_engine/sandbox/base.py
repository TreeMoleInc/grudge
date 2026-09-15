"""Abstract sandbox backend interface. match_runner.py, tournament_runner.py, and
preflight.py are written entirely against this interface and never import a
concrete backend directly - swapping dev_backend.py for nsjail_backend.py (or,
later, something else entirely per CLAUDE.md's documented upgrade path) requires
zero changes above this layer.
"""

from __future__ import annotations

import queue
import threading
from abc import ABC, abstractmethod
from typing import IO, Any

from grudge_engine import protocol


class SandboxProcess(ABC):
    """One running sandboxed child process: a persistent automaton for the
    duration of one match.

    `read_line(timeout)` must behave identically across backends/platforms,
    including a portable blocking-read-with-timeout - plain pipes don't support
    that natively on Windows. The standard fix, shared by every concrete backend
    via this base class, is a background daemon thread doing blocking readline()
    on the child's stdout and pushing parsed messages onto a queue; read_line is
    then just a bounded queue.get().
    """

    def __init__(self) -> None:
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._reader_thread: threading.Thread | None = None

    def _start_reader(self, stdout: IO[str]) -> None:
        self._reader_thread = threading.Thread(target=self._read_loop, args=(stdout,), daemon=True)
        self._reader_thread.start()

    def _read_loop(self, stdout: IO[str]) -> None:
        try:
            for raw_line in stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    msg = protocol.decode_line(line)
                except ValueError:
                    self._queue.put(protocol.protocol_error_message(f"malformed line: {line!r}"))
                    continue
                self._queue.put(msg)
        except (OSError, ValueError):
            pass
        finally:
            self._queue.put(protocol.protocol_error_message("stdout closed (EOF)"))

    def read_line(self, timeout: float) -> dict[str, Any] | None:
        """Returns the next parsed protocol message, or None if none arrived
        within `timeout` seconds. A malformed line or the child closing stdout
        surfaces as a synthetic protocol_error message rather than None, so
        callers can treat "child sent garbage" and "child hung" differently.
        """
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    @abstractmethod
    def send_line(self, msg: dict[str, Any]) -> None: ...

    @abstractmethod
    def poll(self) -> int | None:
        """Exit code if the process has exited, else None."""

    @abstractmethod
    def terminate(self) -> None: ...

    @abstractmethod
    def debug_output(self) -> str:
        """Captured stderr (player print() output) so far, size-capped."""


class SandboxBackend(ABC):
    @abstractmethod
    def spawn(
        self, source_code: str, *, automaton_id: str, seed: int | None = None
    ) -> SandboxProcess:
        """Start a fresh sandboxed process running `source_code` as one automaton
        for the duration of one match. `seed`, when not None, is forwarded so the
        automaton's `random` module seeds deterministically (test/debug use only -
        production call sites never pass this).
        """
