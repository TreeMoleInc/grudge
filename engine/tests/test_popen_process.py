"""Unit tests for popen_process.py's shared helpers, isolated from any real
subprocess/nsjail - both the temp-dir-write helper and PopenSandboxProcess's
cleanup logic are pure Python-object-management concerns that a fake Popen
can exercise deterministically. See test_dev_backend.py/test_nsjail_backend.py
for the real-subprocess integration coverage of spawn()/terminate() together.
"""

from __future__ import annotations

import os
import subprocess

import pytest

from grudge_engine.sandbox.popen_process import PopenSandboxProcess, write_automaton_source


def test_write_automaton_source_creates_a_readable_source_file():
    tmp_dir, source_path = write_automaton_source("probe", "def decide(history):\n    pass\n")
    try:
        assert os.path.isdir(tmp_dir)
        with open(source_path, encoding="utf-8") as f:
            assert f.read() == "def decide(history):\n    pass\n"
    finally:
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_write_automaton_source_cleans_up_its_temp_dir_on_write_failure(monkeypatch):
    created_dirs: list[str] = []
    real_mkdtemp = __import__("tempfile").mkdtemp

    def tracking_mkdtemp(*args, **kwargs):
        d = real_mkdtemp(*args, **kwargs)
        created_dirs.append(d)
        return d

    def failing_open(*args, **kwargs):
        raise OSError("disk full (simulated)")

    monkeypatch.setattr("tempfile.mkdtemp", tracking_mkdtemp)
    monkeypatch.setattr("builtins.open", failing_open)

    with pytest.raises(OSError):
        write_automaton_source("probe", "irrelevant")

    assert len(created_dirs) == 1
    # Without the fix, this directory (which would have held the automaton's
    # plaintext source, had the write succeeded) is left behind forever.
    assert not os.path.exists(created_dirs[0])


class _FakeStream:
    """Iterable (empty) so the reader threads PopenSandboxProcess.__init__
    starts on stdout/stderr (`for line in stream:`) exit cleanly instead of
    raising in a background thread.
    """

    def __init__(self) -> None:
        self.closed = False

    def __iter__(self):
        return iter(())

    def close(self) -> None:
        self.closed = True


class _NeverDiesPopen:
    """Simulates a child that ignores both SIGTERM and SIGKILL (e.g. stuck in
    uninterruptible D-state) - `wait()` always times out, no matter how many
    times it's called.
    """

    def __init__(self) -> None:
        self.stdin = _FakeStream()
        self.stdout = _FakeStream()
        self.stderr = _FakeStream()
        self.terminate_called = False
        self.kill_called = False

    def poll(self) -> int | None:
        return None  # still "running" throughout

    def terminate(self) -> None:
        self.terminate_called = True

    def kill(self) -> None:
        self.kill_called = True

    def wait(self, timeout: float) -> None:
        raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)


def test_terminate_completes_and_still_cleans_up_when_the_child_never_dies(tmp_path):
    # 2026-09-14 fix: the second wait() (after kill()) previously had no
    # try/except of its own - an unkillable child raised TimeoutExpired
    # straight out of terminate(), skipping stream cleanup and the temp-dir
    # rmtree below, and (at the match_runner.py call site) skipping the
    # sibling process's own terminate() too.
    popen = _NeverDiesPopen()
    marker = tmp_path / "marker.txt"
    marker.write_text("automaton source")
    proc = PopenSandboxProcess(popen, str(tmp_path))

    proc.terminate()  # must not raise

    assert popen.terminate_called
    assert popen.kill_called
    assert popen.stdin.closed
    assert popen.stdout.closed
    assert popen.stderr.closed
    assert not tmp_path.exists()  # rmtree still ran
