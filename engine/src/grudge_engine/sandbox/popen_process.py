"""Shared SandboxProcess implementation for any backend that ultimately runs the
shim as a plain subprocess.Popen with stdio passthrough - both dev_backend.py and
nsjail_backend.py wrap a Popen this way. They differ only in how the argv/env for
that Popen gets built (bare vs. wrapped in an `nsjail ...` invocation); once
started, both are driven identically, which is what this class captures.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
from typing import Any

from grudge_engine import protocol
from grudge_engine.sandbox.base import SandboxProcess

_MAX_DEBUG_LOG_CHARS = 64 * 1024


def write_automaton_source(automaton_id: str, source_code: str) -> tuple[str, str]:
    """Writes `source_code` to a fresh temp dir, shared by every Popen-based
    backend (dev_backend.py, nsjail_backend.py) so their spawn() logic doesn't
    duplicate this write, and so a Popen failure right after this call - a
    transient error, unrelated to the source file itself - can't leak the temp
    dir the way it could when each backend built and cleaned it up separately
    (nothing else owns this directory until a SandboxProcess is constructed
    around the resulting Popen; see callers). Returns (tmp_dir, source_path).
    """
    tmp_dir = tempfile.mkdtemp(prefix=f"grudge_{automaton_id}_")
    source_path = os.path.join(tmp_dir, "automaton.py")
    try:
        with open(source_path, "w", encoding="utf-8") as f:
            f.write(source_code)
    except OSError:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    return tmp_dir, source_path


class PopenSandboxProcess(SandboxProcess):
    def __init__(self, popen: subprocess.Popen, tmp_dir: str) -> None:
        super().__init__()
        self._popen = popen
        self._tmp_dir = tmp_dir
        self._debug_chunks: list[str] = []
        self._debug_lock = threading.Lock()
        self._start_reader(self._popen.stdout)
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stderr_thread.start()

    def _read_stderr(self) -> None:
        try:
            for line in self._popen.stderr:
                with self._debug_lock:
                    self._debug_chunks.append(line)
        except (OSError, ValueError):
            pass

    def send_line(self, msg: dict[str, Any]) -> None:
        try:
            self._popen.stdin.write(protocol.encode_line(msg) + "\n")
            self._popen.stdin.flush()
        except (BrokenPipeError, OSError):
            pass  # child already gone; the harness observes this via read_line/poll

    def poll(self) -> int | None:
        return self._popen.poll()

    def terminate(self) -> None:
        if self._popen.poll() is None:
            try:
                self._popen.terminate()
                self._popen.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._popen.kill()
                # Unlike the first wait() above, a second timeout here isn't
                # caught by a broader `except` that would also swallow the
                # coming OSError case - without its own try/except, a child
                # that's still unkillable after SIGKILL (rare: a D-state
                # process stuck in uninterruptible I/O) raises TimeoutExpired
                # straight out of terminate(), skipping the stream-close and
                # temp-dir cleanup below entirely, and - since match_runner.py
                # calls terminate() on each side independently specifically to
                # avoid this - would otherwise be the one path that could still
                # leak both sides at once if this method call is the one both
                # callers happen to share.
                try:
                    self._popen.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    pass
            except OSError:
                pass
        for stream in (self._popen.stdin, self._popen.stdout, self._popen.stderr):
            try:
                stream.close()
            except OSError:
                pass
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def debug_output(self) -> str:
        with self._debug_lock:
            text = "".join(self._debug_chunks)
        return text[-_MAX_DEBUG_LOG_CHARS:]
