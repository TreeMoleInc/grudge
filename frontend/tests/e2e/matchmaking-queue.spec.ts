import { expect, test, SESSION_COOKIE_NAME, seedSessionToken } from "./fixtures";
import type { Page } from "@playwright/test";

// Exercises /ws/matchmaking/queue/{id}, the one WebSocket endpoint the rest of
// the E2E suite doesn't reach (sim-room.spec.ts covers /ws/sim-rooms/{id} and
// /ws/tournaments/{id}/progress - see TODO.md's now-closed "matchmaking queue
// WS coverage" item). A real ranked/unranked room needs 4 players to fill
// (see CLAUDE.md S2's 2026-08-30 room-size revision) - driving that directly
// with 4 simultaneous browser contexts is more tractable than the original
// 8-player size was, but this test still goes through the capacity override
// rather than doing that, since the override isn't tied to whatever the
// current room size happens to be and keeps the test leaner (2 players
// instead of 4). Requires the backend to have been started with
// MATCHMAKING_ROOM_CAPACITY_OVERRIDE set to a small number (see config.py).
// Skipped entirely if that env var isn't set in THIS process too, since both
// the backend and this test need to agree on the same override for the test
// to make sense.
const overrideRaw = process.env.MATCHMAKING_ROOM_CAPACITY_OVERRIDE;
const capacity = overrideRaw ? Number.parseInt(overrideRaw, 10) : null;

test.skip(
  !capacity,
  "requires the backend to be started with MATCHMAKING_ROOM_CAPACITY_OVERRIDE=<n> " +
    "(and this test process to see the same env var) - see engine/README.md-style " +
    "skip pattern; not run by default since it changes real matchmaking behavior."
);

async function openLoggedInPage(page: Page, username: string): Promise<void> {
  const token = seedSessionToken(username);
  await page.context().addCookies([
    {
      name: SESSION_COOKIE_NAME,
      value: token,
      domain: "localhost",
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);
  await page.goto("/");
}

async function createAutomatonViaApi(page: Page, name: string): Promise<void> {
  await page.request.post("http://localhost:8000/automata", {
    data: { name, code: "def decide(history):\n    return COOPERATE\n" },
  });
}

test("matchmaking queue: two real players fill a (capacity-overridden) unranked room over WS", async ({
  page,
  context,
}) => {
  const suffix = Date.now();
  const usernameA = `e2e_mm_a_${suffix}`;
  const usernameB = `e2e_mm_b_${suffix}`;

  // Player A, in the test's own page/context.
  await openLoggedInPage(page, usernameA);
  await createAutomatonViaApi(page, "MM Bot A");
  await page.goto("/play");
  await page.getByRole("tab", { name: "Random" }).click();
  await page.getByRole("combobox").first().selectOption({ label: "Unranked" });
  await page.getByRole("combobox").nth(1).selectOption({ label: "MM Bot A" });
  await page.getByRole("button", { name: "Join queue" }).click();

  // The join HTTP response seeds status immediately (see RandomTab.tsx's
  // comment on why it doesn't wait on the WS broadcast for this) - confirms
  // the running backend really does have the override active before we
  // bother spinning up a second player.
  await expect(page.getByText(`1/${capacity} waiting…`)).toBeVisible();

  // Player B, in a second real browser context - a separate WS connection,
  // proving the "matched" broadcast in matchmaking.py's join_queue reaches
  // an actually-connected client over /ws/matchmaking/queue/{id}, not just
  // that the HTTP join sequence is correct (already covered by
  // backend/tests/integration/test_matchmaking_api.py).
  const pageB = await context.newPage();
  await openLoggedInPage(pageB, usernameB);
  await createAutomatonViaApi(pageB, "MM Bot B");
  await pageB.goto("/play");
  await pageB.getByRole("tab", { name: "Random" }).click();
  await pageB.getByRole("combobox").first().selectOption({ label: "Unranked" });
  await pageB.getByRole("combobox").nth(1).selectOption({ label: "MM Bot B" });
  await pageB.getByRole("button", { name: "Join queue" }).click();

  if (capacity === 2) {
    // The room fills on B's own join - B's HTTP response already carries a
    // tournament_id and redirects directly, without waiting on its own WS.
    await expect(pageB).toHaveURL(/\/processing\//, { timeout: 10_000 });
  }

  // Player A never re-joined or polled anything - this can only have
  // happened via the "matched" message pushed down A's already-open
  // /ws/matchmaking/queue/{id} socket.
  await expect(page).toHaveURL(/\/processing\//, { timeout: 10_000 });

  await pageB.close();
});
