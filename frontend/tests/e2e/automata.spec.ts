import { expect, test } from "./fixtures";

test("create an automaton, edit and autosave it, create a new version, and activate it", async ({
  page,
  loggedInAs,
}) => {
  await loggedInAs(`e2e_automata_${Date.now()}`);

  await page.goto("/automata");

  // The Sidebar's "New automaton" flow uses the purpose-built NewAutomatonDialog
  // (name + a "share with friends" checkbox, not window.prompt() - see
  // CLAUDE.md S2 "In-site dialogs"), so fill its name field and submit rather
  // than intercepting a native browser dialog.
  await page.getByRole("button", { name: "+ Automaton" }).click();
  // Excludes the checkbox input (":not([type=checkbox])") - the dialog has
  // two <input> elements. Not getByRole("textbox") either, since the
  // CodeMirror editor's contenteditable div also has role="textbox" once
  // it's on the page.
  await page.locator('input:not([type="checkbox"])').fill("E2E Tit for Tat");
  await page.getByRole("button", { name: "OK" }).click();

  await expect(page.getByRole("heading", { name: "E2E Tit for Tat" })).toBeVisible();
  await expect(page.getByRole("combobox")).toHaveValue(/.+/); // a version is selected

  // Edit the code and wait for autosave to report "Saved".
  const editor = page.locator(".cm-content");
  await editor.click();
  await page.keyboard.press("End");
  await page.keyboard.type("  # e2e edit");
  await expect(page.getByText("Saved")).toBeVisible({ timeout: 5000 });

  // Reload and confirm the edit actually persisted server-side, not just in
  // local component state.
  await page.reload();
  await expect(editor).toContainText("# e2e edit");

  // Create a new version (forks current code by default) and activate it.
  await page.getByRole("button", { name: "New version" }).click();
  await page.locator("input").fill("v2");
  await page.getByRole("button", { name: "OK" }).click();
  await expect(page.locator("select option:checked")).toHaveText("v2");
  await expect(page.getByRole("button", { name: "Set active" })).toBeEnabled();

  await page.getByRole("button", { name: "Set active" }).click();
  await expect(page.getByRole("button", { name: "Active" })).toBeDisabled();
});
