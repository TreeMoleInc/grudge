"""Real OS-level isolation backend, wrapping the shim invocation in `nsjail`.
Linux-only (needs user/mount/pid/net namespaces + seccomp-bpf) - unusable on
native Windows, only inside WSL2 (or a real Linux host) with nsjail installed.

Implements the same SandboxBackend/SandboxProcess contract as dev_backend.py, so
match_runner/tournament_runner/preflight need no changes to use this instead -
that's the whole point of the pluggable-backend design (CLAUDE.md's documented
nsjail-to-gVisor upgrade path relies on the same property).

STATUS: built from source and verified end-to-end under WSL2 (Ubuntu 24.04) -
see tests/test_nsjail_backend.py, which confirms both the protocol working
through a real jailed process and, independently of the AST validator (via raw
`python3 -c` payloads that bypass grudge_engine entirely), that nsjail itself
blocks network access, blocks filesystem writes, isolates the PID namespace, and
enforces the memory rlimit. Two corrections from the original untested flag
guesses, worth knowing if this needs debugging again: `--disable_clone_newuser`
does the *opposite* of what its name suggests ("don't use a user namespace,
requires euid==0") - nsjail's whole unprivileged-sandboxing trick depends on
CLONE_NEWUSER, so that flag must NOT be passed when running as a normal user;
and env vars are NOT inherited into the jail by default (`--keep_env` would pass
everything through, which we deliberately avoid) - PYTHONPATH/GRUDGE_SEED are
forwarded explicitly via `--env`, not via subprocess.Popen's own `env=`, which
only affects nsjail's own process, not the jailed child.

KNOWN LIMITATION, partially hardened: `--chroot /` is a read-only bind of the
entire host root, not a minimal purpose-built jail - it correctly blocks writes
and reliably gives the interpreter everything it needs (stdlib, shared libs)
without hand-enumerating paths, but it means the jailed process can in
principle *read* anything the invoking user can read on the host. Rather than
rebuilding the chroot from a hand-enumerated allowlist (fragile - Python's
stdlib/shared-lib paths vary by distro and are easy to get subtly wrong, and
getting it wrong fails closed as a broken sandbox rather than an obviously
loud error), `NsjailConfig.shadow_paths` mounts an empty tmpfs
(`--tmpfsmount`) over specific known-sensitive directories - default
`("/home", "/root", "/mnt", "/run", "/tmp")`. `/mnt` is critical on this
Windows dev machine specifically because WSL2 exposes the entire Windows C:
drive at `/mnt/c`. `/run` and `/tmp` were added 2026-09-14, after a probe
showed that read-only doesn't stop *connecting*: a jailed process could still
connect to Unix socket files other programs left there (neither the read-only
bind nor the jail's separate network namespace covers a socket file). Postgres
keeps its socket in /run/postgresql, and with Ubuntu's default `peer` auth an
OS user with a same-named Postgres role - exactly production's
`grudge`/`grudge` pairing - got a working, passwordless psql session from
inside the jail; with both directories shadowed the same attempt fails with
"No such file or directory". `/tmp` also holds every running match's automaton
source directory (all owned by the same OS user) - with it shadowed, only the
jailed process's own directory is re-exposed (`_paths_needing_reexposure`).
This closes the concrete, known holes without touching anything Python needs
to actually run. It is still not a minimal purpose-built jail - other readable
host paths outside the shadow list remain visible - so this is a narrowing of
the gap, not a full close.

SECCOMP, wired up 2026-09-14: `NsjailConfig.seccomp_policy_file` previously
defaulted to `None`, and nothing else in the codebase ever set it - meaning
`--seccomp_policy` was silently never passed to the real nsjail invocation,
despite CLAUDE.md's "OS-level sandboxing tool" section describing seccomp-bpf
as part of what nsjail provides ("deny everything by default, allowlist only
a narrow set of syscalls"). A jailed automaton had the namespaces/rlimits/
chroot above but the *full host syscall surface* otherwise - a real gap, not
a documentation error, found during a pre-launch review. Now defaults to
`grudge_sandbox.kafel`, shipped next to this module: a denylist (default
ALLOW, explicit `KILL_PROCESS` on a fixed list), not the allowlist CLAUDE.md's
wording suggests - see that file's own header comment for why a denylist is
the safer choice to actually get right for a CPython workload, matching
Docker/runc's own default seccomp profile shape. Verified against the real
nsjail/kafel toolchain: a plain Python program and a full reference-bot match
both still run cleanly under it, and two representative denied syscalls
(`ptrace`, `mount`) are actually killed - see
`test_nsjail_backend.py`'s `test_seccomp_policy_*` tests.

Verification against the actual hosting provider's kernel (a different, still
open TODO.md item) remains separate - this confirms nsjail works under WSL2,
not on whatever ends up running production.

Tests for this module are skipped unless `GRUDGE_TEST_NSJAIL=1` is set and an
`nsjail` binary is on PATH (i.e., normally: skipped on native Windows, runs
under `wsl pytest -m nsjail`).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from grudge_engine.constants import MEMORY_LIMIT_MB, PER_MATCH_CUMULATIVE_CPU_MS
from grudge_engine.sandbox.base import SandboxBackend, SandboxProcess
from grudge_engine.sandbox.popen_process import PopenSandboxProcess, write_automaton_source

_SRC_DIR = str(Path(__file__).resolve().parents[2])  # .../engine/src
# Ships next to this module, not somewhere config-driven - it's a fixed part
# of the engine's own sandbox, not a per-deployment setting (see
# grudge_sandbox.kafel's own header comment for what it does and why).
_DEFAULT_SECCOMP_POLICY = str(Path(__file__).resolve().parent / "grudge_sandbox.kafel")


def is_available() -> bool:
    return shutil.which("nsjail") is not None


@dataclass(frozen=True)
class NsjailConfig:
    binary_path: str = "nsjail"
    rlimit_cpu_seconds: int = max(1, PER_MATCH_CUMULATIVE_CPU_MS // 1000)
    rlimit_as_mb: int = MEMORY_LIMIT_MB
    rlimit_nproc: int = 0
    # Extra host paths made available read-only inside the jail, beyond the
    # Python interpreter itself and the engine source tree (always included).
    # Needed so the sandboxed interpreter can find its stdlib.
    extra_ro_binds: tuple[str, ...] = field(default_factory=tuple)
    # Defaults to the real policy shipped with this package (added 2026-09-14
    # - see the module docstring's SECCOMP note) rather than None, so building
    # a NsjailSandboxBackend with no explicit config - the real production
    # code path, backend/src/grudge_backend/sandbox.py - actually gets the
    # syscall filter CLAUDE.md's "OS-level sandboxing tool" section describes
    # as part of nsjail's value, instead of silently running without one.
    # Pass None explicitly to disable it (tests probing nsjail's other
    # guarantees in isolation do this, so a seccomp kill can't be mistaken for
    # the guarantee actually under test).
    seccomp_policy_file: str | None = _DEFAULT_SECCOMP_POLICY
    # Host directories to shadow with an empty tmpfs inside the jail (see the
    # module docstring's KNOWN LIMITATION note) - hides their contents from the
    # jailed process without needing to hand-enumerate everything Python does
    # need. Paths that don't exist on the host are silently skipped (nsjail
    # errors on mounting tmpfs over a nonexistent mountpoint). /run and /tmp
    # hide other programs' local sockets - see the module docstring for the
    # real database login that closed. /dev/shm and /var/tmp are the same
    # class of hole: world-writable/socket-bearing tmpfs-backed paths a jailed
    # process could otherwise connect through, same as /run and /tmp - added
    # alongside them 2026-09-14 rather than found independently vulnerable,
    # but on the same reasoning.
    shadow_paths: tuple[str, ...] = (
        "/home",
        "/root",
        "/mnt",
        "/run",
        "/tmp",
        "/dev/shm",
        "/var/tmp",
    )


class NsjailSandboxBackend(SandboxBackend):
    SECURITY_LEVEL = "os-isolated"

    def __init__(self, config: NsjailConfig | None = None) -> None:
        self._config = config or NsjailConfig()
        resolved = shutil.which(self._config.binary_path)
        if not resolved:
            raise RuntimeError(
                f"nsjail binary '{self._config.binary_path}' not found on PATH - "
                "install nsjail inside WSL2/Linux before using this backend."
            )
        # Fail loudly on a missing policy file rather than nsjail itself
        # erroring later at spawn time (or, if the path were wrong in a
        # subtler way, silently running with no syscall filter at all) - the
        # whole point of shipping a default (above) is that this should never
        # be reachable outside deliberately passing seccomp_policy_file=None.
        if self._config.seccomp_policy_file and not os.path.isfile(
            self._config.seccomp_policy_file
        ):
            raise RuntimeError(
                f"seccomp policy file not found: {self._config.seccomp_policy_file!r}"
            )
        # Resolved to an absolute path up front: subprocess.Popen is given a
        # minimal, purpose-built env below (not the parent's PATH), so argv[0]
        # must already be absolute rather than relying on PATH lookup at spawn
        # time.
        self._nsjail_path = resolved

    def _paths_needing_reexposure(self, extra_context_dir: str | None) -> list[str]:
        """Paths that must stay readable for the interpreter to actually run
        (the engine source tree, the interpreter's own install prefixes, and
        - when spawning a real automaton - its freshly-written source file's
        directory), filtered down to just the ones that happen to fall under
        a shadowed prefix. Deliberately over-inclusive in the candidate set
        (sys.prefix == sys.base_prefix outside a venv, extra_context_dir is
        rarely under a shadow path) - harmless, since anything not actually
        under a shadow_paths entry is skipped below.
        """
        cfg = self._config
        candidates = {
            _SRC_DIR,
            sys.prefix,
            sys.exec_prefix,
            sys.base_prefix,
            sys.base_exec_prefix,
            os.path.dirname(os.path.realpath(sys.executable)),
        }
        if extra_context_dir:
            candidates.add(extra_context_dir)
        shadow_prefixes = tuple(p.rstrip("/") + "/" for p in cfg.shadow_paths)
        needed = []
        for path in candidates:
            if not path or not os.path.isdir(path):
                continue
            normalized = path.rstrip("/")
            if normalized in cfg.shadow_paths or normalized.startswith(shadow_prefixes):
                needed.append(normalized)
        return sorted(needed)

    def isolation_argv_prefix(
        self, *, seed: int | None = None, extra_context_dir: str | None = None
    ) -> list[str]:
        """Builds the nsjail invocation up to and including the `--`
        separator - chroot, rlimits, env, shadow tmpfs mounts, and their
        selective re-exposure - without the trailing command. `spawn()`
        appends the shim invocation; `tests/test_nsjail_backend.py` reuses
        this directly to probe the same isolation flags with a raw `python3
        -c` payload instead, so the adversarial tests exercise the exact
        flags real matches run under, not a re-implementation of them.
        `extra_context_dir` is the directory a caller's own trailing command
        needs read access to, beyond what this backend already needs for
        itself (real spawns pass the automaton's temp source dir).
        """
        cfg = self._config
        # Read-only bind of the whole host root, rather than a hand-picked
        # minimal chroot (the "real" hardened approach - tracked as follow-up
        # work, see the module docstring). This is enough to block writes to the
        # host FS and to avoid having to enumerate every shared-lib/stdlib path
        # Python needs, but it does mean the jailed process can in principle
        # *read* anything the invoking user can read - shadow_paths (below)
        # closes the specific known holes (home dirs, /mnt on this Windows dev
        # box) without hand-enumerating everything Python does need.
        argv = [
            self._nsjail_path,
            "--mode",
            "o",  # run the command once, wait for it to exit
            "--quiet",
            "--chroot",
            "/",
            "--rlimit_cpu",
            str(cfg.rlimit_cpu_seconds),
            "--rlimit_as",
            str(cfg.rlimit_as_mb),
            "--rlimit_nproc",
            str(cfg.rlimit_nproc),
            "--env",
            f"PYTHONPATH={_SRC_DIR}",
        ]
        if seed is not None:
            argv += ["--env", f"GRUDGE_SEED={seed}"]
        for shadow_path in cfg.shadow_paths:
            if os.path.isdir(shadow_path):
                argv += ["--tmpfsmount", shadow_path]
        # Re-exposed AFTER the tmpfs shadow flags above so these specific
        # subpaths win the mount stacking (last mount at a given path wins) -
        # confirmed empirically against the real nsjail binary, not just
        # assumed from docs. Sibling paths under the same shadowed directory
        # (e.g. another user's home dir) stay hidden.
        for needed_path in self._paths_needing_reexposure(extra_context_dir):
            argv += ["--bindmount_ro", f"{needed_path}:{needed_path}"]
        for host_path in cfg.extra_ro_binds:
            argv += ["--bindmount_ro", f"{host_path}:{host_path}"]
        if cfg.seccomp_policy_file:
            argv += ["--seccomp_policy", cfg.seccomp_policy_file]
        argv += ["--"]
        return argv

    def _build_argv(self, source_path: str, *, seed: int | None) -> list[str]:
        argv = self.isolation_argv_prefix(seed=seed, extra_context_dir=os.path.dirname(source_path))
        argv += [sys.executable, "-m", "grudge_engine.shim.runtime", source_path]
        return argv

    def spawn(
        self, source_code: str, *, automaton_id: str, seed: int | None = None
    ) -> SandboxProcess:
        tmp_dir, source_path = write_automaton_source(automaton_id, source_code)

        # This is nsjail's OWN process environment, not the jailed child's (which
        # gets none of this by default - see --env above for how the child's env
        # is actually populated). A minimal, known-good PATH is all nsjail itself
        # needs.
        env = {"PATH": "/usr/bin:/bin"}

        try:
            popen = subprocess.Popen(
                self._build_argv(source_path, seed=seed),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
            )
        except OSError:
            # Nothing owns tmp_dir until PopenSandboxProcess exists to clean it
            # up in terminate() - a Popen failure here (e.g. nsjail itself
            # transiently missing/unexecutable) would otherwise leak the temp
            # dir (and the player source it holds) permanently.
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise
        return PopenSandboxProcess(popen, tmp_dir)
