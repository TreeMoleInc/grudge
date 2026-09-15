"""Real OS-level isolation tests against an actual nsjail binary. Linux/WSL2-only
- skipped everywhere else. Two kinds of coverage here:

1. Functional: the shim/protocol works correctly when actually run through
   nsjail, not just the insecure dev backend (test_dev_backend.py already covers
   the shim itself in depth; here we're checking the nsjail wrapping doesn't
   break anything).
2. Adversarial, OS-level, bypassing the AST validator entirely: these invoke
   nsjail directly with a raw `python3 -c ...` payload rather than going through
   match_runner/the shim, specifically BECAUSE the AST validator would reject
   `import socket` etc. before it ever reached a sandboxed process. CLAUDE.md is
   explicit that OS-level isolation is the *primary* defense and must hold
   "regardless of what the Python code inside tries to do" - these tests prove
   that independently of whatever the AST layer catches.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile

import pytest

from grudge_engine.automaton import Automaton
from grudge_engine.match_runner import run_match
from grudge_engine.protocol import round_message, shutdown_message
from grudge_engine.reference_bots import ALWAYS_COOPERATE_SOURCE, TIT_FOR_TAT_SOURCE
from grudge_engine.sandbox import nsjail_backend
from grudge_engine.sandbox.nsjail_backend import NsjailSandboxBackend

pytestmark = pytest.mark.nsjail

_SKIP_REASON = "set GRUDGE_TEST_NSJAIL=1 and ensure an nsjail binary is on PATH to run these"
requires_nsjail = pytest.mark.skipif(
    not (os.environ.get("GRUDGE_TEST_NSJAIL") == "1" and nsjail_backend.is_available()),
    reason=_SKIP_REASON,
)


@pytest.fixture
def nsjail_sandbox() -> NsjailSandboxBackend:
    return NsjailSandboxBackend()


def _run_raw_in_nsjail(python_code: str, *, timeout: float = 10.0) -> subprocess.CompletedProcess:
    """Runs `python_code` via `python3 -c` directly through nsjail, bypassing
    grudge_engine entirely (no shim, no AST validation) - used only to probe
    nsjail's own OS-level guarantees in isolation from our application code.
    """
    nsjail_path = nsjail_backend.NsjailSandboxBackend()._nsjail_path
    argv = [
        nsjail_path,
        "--mode",
        "o",
        "--quiet",
        "--chroot",
        "/",
        "--rlimit_as",
        "128",
        "--rlimit_cpu",
        "5",
        "--",
        sys.executable,
        "-c",
        python_code,
    ]
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={"PATH": "/usr/bin:/bin"},
        check=False,  # a killed/failed process is the expected outcome here
    )


# -- functional: shim/protocol works correctly through real nsjail ---------------


@requires_nsjail
def test_ready_and_move_exchange_via_nsjail(nsjail_sandbox):
    proc = nsjail_sandbox.spawn(TIT_FOR_TAT_SOURCE, automaton_id="tft")
    try:
        assert proc.read_line(timeout=10)["type"] == "ready"
        proc.send_line(round_message(0, None))
        msg = proc.read_line(timeout=10)
        assert msg["type"] == "move"
        assert msg["move"] == "COOPERATE"
        proc.send_line(shutdown_message())
    finally:
        proc.terminate()


@requires_nsjail
def test_full_match_via_nsjail_matches_dev_backend_result(nsjail_sandbox):
    tft = Automaton(id="tft", source=TIT_FOR_TAT_SOURCE)
    allc = Automaton(id="allc", source=ALWAYS_COOPERATE_SOURCE)
    result = run_match(tft, allc, nsjail_sandbox, length_override=5)
    assert result.status == "completed"
    assert result.score_a == 15
    assert result.score_b == 15


# -- adversarial: OS-level isolation, independent of the AST validator -----------


@requires_nsjail
def test_network_access_is_blocked_at_os_level():
    result = _run_raw_in_nsjail(
        "import socket\n"
        "s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "s.settimeout(3)\n"
        "s.connect(('8.8.8.8', 53))\n"
        "print('CONNECTED')\n"
    )
    assert "CONNECTED" not in result.stdout


@requires_nsjail
def test_filesystem_writes_are_blocked_at_os_level(tmp_path):
    marker = tmp_path / "should_not_be_created.txt"
    result = _run_raw_in_nsjail(f"open({str(marker)!r}, 'w').write('pwned')\nprint('WROTE')\n")
    assert "WROTE" not in result.stdout
    assert not marker.exists()


@requires_nsjail
def test_pid_namespace_isolates_the_process():
    # Inside a fresh PID namespace the jailed process is (close to) PID 1/2 -
    # nowhere near the real host's process count, which on a running WSL distro
    # is comfortably in the dozens+.
    result = _run_raw_in_nsjail("import os\nprint(os.getpid())\n")
    pid = int(result.stdout.strip())
    assert pid <= 5


@requires_nsjail
def test_memory_rlimit_is_enforced_at_os_level():
    # 128MB RLIMIT_AS (matching CLAUDE.md's MEMORY_LIMIT_MB) vs. a ~500MB
    # allocation - must fail or be killed, not silently succeed.
    result = _run_raw_in_nsjail("x = bytearray(500 * 1024 * 1024)\nprint('ALLOCATED', len(x))\n")
    assert "ALLOCATED" not in result.stdout


@requires_nsjail
def test_shadow_paths_hide_home_directory_contents(tmp_path):
    # A file that genuinely exists on the host, outside anything nsjail
    # itself needs to run - if shadow_paths (default includes "/home") is
    # working, the jailed process must not be able to see it, even though
    # this exact same nsjail invocation still successfully runs Python (the
    # interpreter's own /home-resident venv, if any, is selectively
    # re-exposed - see NsjailSandboxBackend._paths_needing_reexposure).
    # Asks whether the marker file exists rather than listing the home
    # directory: when nothing under /home is re-exposed (production, where the
    # code and venv live in /opt), the home directory doesn't exist inside the
    # jail at all, so a listing raises instead of answering - a false failure
    # that a dress rehearsal of ops/README.md's sandbox check caught.
    home = os.path.expanduser("~")
    marker_name = f"grudge_shadow_test_marker_{os.getpid()}.txt"
    marker_path = os.path.join(home, marker_name)
    with open(marker_path, "w", encoding="utf-8") as f:
        f.write("should not be readable inside the jail")
    try:
        backend = nsjail_backend.NsjailSandboxBackend()
        argv = backend.isolation_argv_prefix() + [
            sys.executable,
            "-c",
            f"import os\nprint('MARKER_VISIBLE', os.path.exists({marker_path!r}))\n",
        ]
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=10.0,
            env={"PATH": "/usr/bin:/bin"},
            check=False,
        )
        assert "MARKER_VISIBLE True" not in result.stdout
        assert "MARKER_VISIBLE False" in result.stdout
    finally:
        os.remove(marker_path)


@requires_nsjail
def test_shadowed_home_still_allows_the_interpreter_to_run(nsjail_sandbox):
    # The interpreter running the probe above is itself very likely installed
    # somewhere under /home (this project's own WSL2 dev/test venv is,
    # per engine/README.md) - if the selective re-exposure logic were broken,
    # shadowing /home would have broken every other test in this file, not
    # just this one. This test asserts that directly: a real automaton match
    # via the actual sandbox backend (not the raw-nsjail probe helper) still
    # completes normally with shadow_paths active.
    proc = nsjail_sandbox.spawn(ALWAYS_COOPERATE_SOURCE, automaton_id="shadow_smoke")
    try:
        assert proc.read_line(timeout=10)["type"] == "ready"
        proc.send_line(round_message(0, None))
        msg = proc.read_line(timeout=10)
        assert msg["type"] == "move"
        assert msg["move"] == "COOPERATE"
        proc.send_line(shutdown_message())
    finally:
        proc.terminate()


def _run_with_backend_flags(python_code: str) -> subprocess.CompletedProcess:
    """Runs `python_code` under the real backend's own isolation flags
    (`isolation_argv_prefix()`, shadow paths included) - unlike
    `_run_raw_in_nsjail`'s minimal flag set, for checks that depend on exactly
    what production spawns see.
    """
    argv = nsjail_backend.NsjailSandboxBackend().isolation_argv_prefix() + [
        sys.executable,
        "-c",
        python_code,
    ]
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=10.0,
        env={"PATH": "/usr/bin:/bin"},
        check=False,
    )


@requires_nsjail
def test_shadow_paths_block_unix_sockets_left_in_tmp():
    # A listening Unix socket another process left in /tmp. Neither the
    # read-only root bind nor the jail's own network namespace stops a
    # connect() to a socket *file* - only hiding the directory does. Same shape
    # as the real hole this guards: Postgres's socket in /run/postgresql, which
    # with Ubuntu's default peer auth let a jailed process log straight into
    # the database as the host user (see nsjail_backend.py's docstring).
    sock_dir = tempfile.mkdtemp(prefix="grudge_socket_probe_", dir="/tmp")
    sock_path = os.path.join(sock_dir, "probe.sock")
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        listener.bind(sock_path)
        listener.listen(1)
        result = _run_with_backend_flags(
            "import socket\n"
            "s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
            "try:\n"
            f"    s.connect({sock_path!r})\n"
            "    print('CONNECTED')\n"
            "except OSError:\n"
            "    print('BLOCKED')\n"
        )
        assert "CONNECTED" not in result.stdout
        assert "BLOCKED" in result.stdout
    finally:
        listener.close()
        if os.path.exists(sock_path):
            os.remove(sock_path)
        os.rmdir(sock_dir)


@requires_nsjail
def test_shadow_paths_hide_run_directory():
    # /run is where system services keep their local-connection sockets
    # (Postgres, D-Bus, ...) - never empty on a real host, empty inside the jail.
    assert os.listdir("/run"), "expected a non-empty /run on the host"
    result = _run_with_backend_flags("import os\nprint('RUN_ENTRIES', len(os.listdir('/run')))\n")
    assert "RUN_ENTRIES 0" in result.stdout


@requires_nsjail
def test_seccomp_policy_blocks_ptrace():
    # ptrace has no legitimate use for a Prisoner's Dilemma strategy and is a
    # well-known process-introspection/escape primitive - one of the syscalls
    # grudge_sandbox.kafel's denylist covers. Calling it directly via ctypes
    # (bypassing Python's own lack of a ptrace() builtin) proves the seccomp
    # filter itself is active, not just that nothing in the restricted
    # environment happens to expose ptrace.
    result = _run_with_backend_flags(
        "import ctypes\n"
        "libc = ctypes.CDLL('libc.so.6', use_errno=True)\n"
        "r = libc.ptrace(0, 0, 0, 0)\n"
        "print('CALLED', r)\n"
    )
    assert "CALLED" not in result.stdout


@requires_nsjail
def test_seccomp_policy_blocks_mount():
    # Namespaces already make a real mount() pointless from inside the jail,
    # but the seccomp filter should still kill the attempt outright rather
    # than letting it reach the namespace layer and fail there instead - the
    # two are independent defenses, and this confirms the syscall-level one
    # specifically (see the module docstring's SECCOMP note).
    result = _run_with_backend_flags(
        "import ctypes\n"
        "libc = ctypes.CDLL('libc.so.6', use_errno=True)\n"
        "r = libc.mount(b'none', b'/tmp', b'tmpfs', 0, 0)\n"
        "print('CALLED', r)\n"
    )
    assert "CALLED" not in result.stdout


@requires_nsjail
def test_seccomp_policy_still_allows_every_whitelisted_module_and_a_real_match(nsjail_sandbox):
    # The denylist shape (default ALLOW, explicit KILL_PROCESS list - see
    # grudge_sandbox.kafel) is meant to never need updating just because a
    # legitimate strategy uses more of the Python subset - this exercises
    # every module CLAUDE.md's Python-subset whitelist actually allows, not
    # just the couple of reference bots the other tests here happen to use.
    kitchen_sink = (
        "import random, math, statistics, collections, itertools, functools, re, copy, enum\n"
        "_counter = collections.Counter()\n"
        "def decide(history):\n"
        "    _counter['calls'] += 1\n"
        "    avg = statistics.mean([1, 2, 3])\n"
        "    total = math.floor(sum(itertools.chain([1], [2])) + functools.reduce(lambda a, b: a + b, [1, 2]))\n"
        "    _ = re.match(r'^a+$', 'aaa')\n"
        "    _ = copy.copy(history)\n"
        "    return COOPERATE if random.random() < avg + total else DEFECT\n"
    )
    proc = nsjail_sandbox.spawn(kitchen_sink, automaton_id="kitchen_sink")
    try:
        assert proc.read_line(timeout=10)["type"] == "ready"
        proc.send_line(round_message(0, None))
        msg = proc.read_line(timeout=10)
        assert msg["type"] == "move"
        proc.send_line(shutdown_message())
    finally:
        proc.terminate()


@requires_nsjail
def test_other_host_processes_are_not_visible():
    # /proc inside the jail's own PID namespace should only show the jailed
    # process tree, not the dozens of real processes running on the WSL host.
    result = _run_raw_in_nsjail(
        "import os\nprint(len([d for d in os.listdir('/proc') if d.isdigit()]))\n"
    )
    visible_pids = int(result.stdout.strip())
    assert visible_pids <= 5
