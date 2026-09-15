# grudge-engine

Phase 1 of Grudge: the sandbox + tournament engine. No web server, no database, no
UI — see the repo root [CLAUDE.md](../CLAUDE.md) for the full product spec and
[the phased build plan](../CLAUDE.md#4-phased-build-plan).

## Dev setup

Pure stdlib package, no runtime dependencies.

```bash
cd engine
python -m venv .venv
.venv\Scripts\activate       # Windows; use `source .venv/bin/activate` on Linux/WSL2
pip install -e .[dev]
pytest -v
```

Everything the portable test suite covers runs on native Windows Python today via
`DevSandboxBackend` (`sandbox/dev_backend.py`) — a plain, **insecure**
`subprocess.Popen` wrapper with no OS-level isolation, used only so the
protocol/game/tournament logic can be built and tested before real isolation is
available. It must never be used to run real/untrusted user code.

## The nsjail-backed tier (Linux/WSL2 only)

`sandbox/nsjail_backend.py` wraps the same shim invocation in `nsjail` for real
OS-level isolation (namespaces, seccomp-bpf, resource limits) and is verified
working under WSL2/Ubuntu 24.04 — see the `STATUS` note at the top of that file
for what was actually confirmed (and the one known follow-up hardening item:
the chroot is currently a read-only bind of the whole host root, not yet a
minimal purpose-built jail). Its tests are skipped unless both are true:

- `GRUDGE_TEST_NSJAIL=1` is set
- an `nsjail` binary is on `PATH`

**Building nsjail** (no packaged binary for Ubuntu 24.04 — build from source):

```bash
sudo apt-get install -y git make gcc g++ pkg-config libprotobuf-dev \
    protobuf-compiler libnl-route-3-dev libcap-dev bison flex libnl-3-dev
git clone --depth 1 https://github.com/google/nsjail.git /tmp/nsjail
cd /tmp/nsjail && git submodule update --init --recursive && make -j$(nproc)
sudo cp nsjail /usr/local/bin/nsjail
```

**Running the WSL2 tier from a Windows checkout:** editable pip installs fail on
`/mnt/c/...` (DrvFs doesn't support the permission operations `pip install -e`
needs) — work from a copy on the Linux-native filesystem instead:

```bash
wsl bash -lc "
  rsync -a --delete /mnt/c/Users/Josep/Documents/Personal/Python/Projects/Grudge/engine/ ~/grudge-engine/ --exclude .venv &&
  cd ~/grudge-engine &&
  python3 -m venv ~/grudge-engine-venv &&
  ~/grudge-engine-venv/bin/pip install -q -e '.[dev]' &&
  GRUDGE_TEST_NSJAIL=1 ~/grudge-engine-venv/bin/python -m pytest -v -m nsjail
"
```

(A native Linux checkout, not synced from Windows at all, avoids this
entirely — this project just doesn't have one yet.)

## Manual smoke test

```bash
python scripts/run_demo_tournament.py
```

Runs one seeded 8-automaton round robin through the reference bots (plus two
extra Axelrod-flavored variants) and prints standings — useful for eyeballing
sane output beyond what the assertions in the test suite check.

## Layout

See the repo root CLAUDE.md §6 (Conventions) for the established package layout
and testing approach.
