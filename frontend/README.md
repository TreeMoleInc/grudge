# grudge-frontend

Phase 4 of Grudge: the React/Vite SPA - Home, Automata (editor + sidebar +
version history + stats), Play (Random/Simulate/History), Processing, Results.
See the repo root [CLAUDE.md](../CLAUDE.md) for the full product spec and
[the phased build plan](../CLAUDE.md#4-phased-build-plan).

No OS-level requirement here (unlike `engine/`'s `nsjail` tier) - runs natively
on Windows like `backend/` does.

## Dev setup

```bash
cd frontend
npm install
cp .env.example .env        # VITE_API_BASE_URL - defaults to http://localhost:8000
npm run dev                  # http://localhost:5173
```

Requires the backend running too (`backend/README.md`), with CORS configured
to allow `http://localhost:5173` (already the default in both `.env.example`
files) - and for anything touching tournaments (Play/Processing/Results), the
worker (`python -m grudge_backend.worker`) also needs to be running, since
that's what actually executes a tournament once a room fills/starts.

## Lint/format

**ESLint + Prettier**, not Biome - Biome's Windows binary is blocked by Smart
App Control on this dev machine (confirmed: `Get-WinEvent` showed Code
Integrity event 3077 rejecting `biome.exe` as unsigned/low-reputation).
Turning Smart App Control off would fix it but is a one-way toggle for the
whole Windows install (no re-enabling without a clean reinstall) - not worth
trading away for a formatter, so this project uses the pure-JS ESLint+Prettier
stack instead (two tools instead of `ruff`'s one, but no native-binary/OS
policy interaction at all).

```bash
npm run lint        # eslint + prettier --check
npm run lint:fix     # eslint --fix + prettier --write
```

## Testing

Two tiers:

- **Unit/component** (`tests/unit/`, Vitest + React Testing Library + MSW):
  pure logic first - `buildFolderTree` (flat-list-to-tree, no DOM needed),
  `processingReducer` (the Processing screen's WS message handling, extracted
  as a plain reducer function so it's testable without a real socket - mirrors
  how `backend/src/grudge_backend/services/matchmaking.py`'s window-radius
  math is unit-tested without a DB). Component tests for `MatchList` (the
  match-by-match/game-by-game expand behavior) and `StandingsTable` render
  real markup via RTL; `AutomatonPicker` uses MSW to stub the `/automata` GET
  rather than mocking `fetch` ad hoc.
  ```bash
  npm run test        # vitest run
  npm run test:watch
  ```
- **E2E** (`tests/e2e/`, Playwright, against the **real running stack** -
  uvicorn + worker + WSL2-hosted Postgres + this dev server): the backend's
  own WebSocket endpoints have zero automated coverage (documented in the
  backend's TODO.md - `httpx.ASGITransport` can't do the WS upgrade), so this
  is the first thing that exercises them for real at all; browser-level WS
  mocking would be lower-value than just running the real thing. Covers the
  two flows named in the Phase 4 plan: automaton create→edit→autosave→new
  version→activate, and sim-room create→join→start→Processing→Results
  (including expanding a match into its round-by-round log).

  OAuth login itself isn't E2E-tested (a real third-party redirect) - tests
  log in via `backend/scripts/seed_e2e_user.py`, a dev/E2E-only script that
  creates a user directly against the DB and prints a raw session token,
  which `tests/e2e/fixtures.ts` sets as a cookie before navigating. Mirrors
  how the backend's own integration tests seed a session row directly rather
  than driving a real OAuth provider.

  ```bash
  npx playwright install chromium   # one-time
  npm run test:e2e                   # needs uvicorn + worker + Postgres already running
  ```

## Layout

See the repo root CLAUDE.md §6 (Conventions) for the established package
layout and testing approach. Structure: `src/{api,ws,auth,pages,components,
styles}/` - `api/types.ts` is hand-written TS mirrors of the backend's
Pydantic schemas (kept in sync by hand for now; codegen from `/openapi.json`
is a cheap future upgrade, not needed yet). Styling is CSS Modules + a single
`styles/tokens.css` of custom properties (no utility framework/component
library - see CLAUDE.md §5 for why: most ship rounded corners by default,
which fights the sharp-corners brief directly).
