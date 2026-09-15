"""Plain-subprocess sandbox backend. INSECURE - provides no OS-level isolation, no
enforced CPU/memory limits, no filesystem/network restriction. Exists purely so
the protocol/game/tournament logic can be built and tested on any platform
(including native Windows, where nsjail cannot run at all) before the real
nsjail-backed backend (nsjail_backend.py) is available. Implements the exact same
SandboxBackend/SandboxProcess interface, so match_runner and everything above it
need zero changes when this is swapped for a real isolation backend.

NEVER use this backend to run real/untrusted user code outside local dev.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

from grudge_engine.sandbox.base import SandboxBackend, SandboxProcess
from grudge_engine.sandbox.popen_process import PopenSandboxProcess, write_automaton_source

# .../engine/src - added to the child's PYTHONPATH so `python -m
# grudge_engine.shim.runtime` resolves even without an editable install.
_SRC_DIR = str(Path(__file__).resolve().parents[2])


class DevSandboxBackend(SandboxBackend):
    SECURITY_LEVEL = "none"

    def __init__(self) -> None:
        warnings.warn(
            "DevSandboxBackend provides no OS-level isolation and must never be "
            "used to run untrusted code outside local development/testing.",
            stacklevel=2,
        )

    def spawn(
        self, source_code: str, *, automaton_id: str, seed: int | None = None
    ) -> SandboxProcess:
        tmp_dir, source_path = write_automaton_source(automaton_id, source_code)

        env = dict(os.environ)
        env["PYTHONPATH"] = _SRC_DIR + os.pathsep + env.get("PYTHONPATH", "")
        if seed is not None:
            env["GRUDGE_SEED"] = str(seed)

        try:
            popen = subprocess.Popen(
                [sys.executable, "-m", "grudge_engine.shim.runtime", source_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
            )
        except OSError:
            # Nothing owns tmp_dir until PopenSandboxProcess exists to clean it
            # up in terminate() - a Popen failure here (e.g. a transient
            # fork/exec error) would otherwise leak the temp dir (and the
            # player source it holds) permanently.
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise
        return PopenSandboxProcess(popen, tmp_dir)
