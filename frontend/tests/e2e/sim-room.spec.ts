import { expect, test } from "./fixtures";

const COOPERATE_CODE = "def decide(history):\n    return COOPERATE\n";
const DEFECT_CODE = "def decide(history):\n    return DEFECT\n";

async function createAutomatonViaApi(
  page: import("@playwright/test").Page,
  name: string,
  code: string
) {
  const response = await page.request.post("http://localhost:8000/automata", {
    data: { name, code },
  });
  const body = await response.json();
  return body.id as string;
}

test("sim room: create, join with two automata, start, watch it run, and drill into results", async ({
  page,
  loggedInAs,
}) => {
  const username = `e2e_sim_${Date.now()}`;
  await loggedInAs(username);

  await createAutomatonViaApi(page, "E2E Cooperator", COOPERATE_CODE);
  await createAutomatonViaApi(page, "E2E Defector", DEFECT_CODE);

  await page.goto("/play");
  await page.getByRole("tab", { name: "Simulate" }).click();
  await page.getByRole("button", { name: "Create a room" }).click();

  await expect(page.getByText(/Invite code:/)).toBeVisible();

  // Join with the first automaton.
  await page.getByRole("combobox").selectOption({ label: "E2E Cooperator" });
  await page.getByRole("button", { name: "Join with this automaton" }).click();
  await expect(page.getByText("Start (1 entrants)")).toBeVisible();

  // Join with the second - the join form must still be available after the
  // first join (this was a real bug found during this session's manual
  // testing: the form used to disappear after one join).
  await page.getByRole("combobox").selectOption({ label: "E2E Defector" });
  await page.getByRole("button", { name: "Join with this automaton" }).click();
  await expect(page.getByRole("button", { name: /Start \(2 entrants\)/ })).toBeEnabled();

  // Exactly one row per entrant - regression check for the duplicate-entry
  // bug (state was updated from both the join response AND the WS broadcast).
  await expect(page.locator("ul li")).toHaveCount(2);

  await page.getByRole("button", { name: /Start \(2 entrants\)/ }).click();

  // Worker picks the job up and runs the real engine - Processing then
  // redirects to Results once the `completed` WS event arrives.
  await expect(page).toHaveURL(/\/results\//, { timeout: 15_000 });

  await expect(page.getByRole("heading", { name: "Simulated Tournament" })).toBeVisible();
  const defectorButton = page.getByRole("button", { name: "E2E Defector", exact: true });
  await expect(defectorButton).toBeVisible();
  await expect(page.getByRole("button", { name: "E2E Cooperator", exact: true })).toBeVisible();

  // Defector exploits the cooperator every round - strictly higher score.
  const standingsRows = page.getByRole("row");
  await expect(standingsRows.nth(1)).toContainText("E2E Defector"); // 1st place

  // Expand the code snapshot.
  await defectorButton.click();
  await expect(page.getByText(/Frozen snapshot/)).toBeVisible();
  await expect(page.locator(".cm-content")).toContainText("return DEFECT");

  // Matches are organized by automaton (see AutomatonMatchDrilldown) - expand
  // the automaton first (its row shows "<name> N matches", distinct from the
  // plain-name button in the standings table above) to reveal its own match
  // list, then expand that match into its round-by-round log.
  await page.getByRole("button", { name: /E2E Defector.*match/ }).click();
  await page.getByText(/E2E Defector vs E2E Cooperator|E2E Cooperator vs E2E Defector/).click();
  await expect(page.getByRole("columnheader", { name: "Round" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "DEFECT", exact: true }).first()).toBeVisible();
});
