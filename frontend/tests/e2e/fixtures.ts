import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test as base, expect } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BACKEND_DIR = path.resolve(__dirname, "../../../backend");
const BACKEND_PYTHON = path.join(BACKEND_DIR, ".venv", "Scripts", "python.exe");
export const SESSION_COOKIE_NAME = "grudge_session"; // must match backend/src/grudge_backend/config.py

/** Creates (or reuses) a user directly against the running backend's DB and
 * returns a fresh raw session token - bypasses the real OAuth dance
 * entirely, same rationale as the backend's own integration tests seeding a
 * session row directly rather than driving a real provider redirect.
 *
 * Exported (along with SESSION_COOKIE_NAME below) so a spec that needs more
 * than one simultaneously-logged-in browser context - e.g.
 * matchmaking-queue.spec.ts, which needs two real players to fill a room -
 * can log a second context in itself rather than being limited to the single
 * page/context the `loggedInAs` fixture below is bound to.
 */
export function seedSessionToken(username: string): string {
  const output = execFileSync(BACKEND_PYTHON, ["scripts/seed_e2e_user.py", username], {
    cwd: BACKEND_DIR,
    encoding: "utf-8",
  });
  return output.trim();
}

interface Fixtures {
  loggedInAs: (username: string) => Promise<void>;
}

export const test = base.extend<Fixtures>({
  loggedInAs: async ({ page, context }, use) => {
    await use(async (username: string) => {
      const token = seedSessionToken(username);
      await context.addCookies([
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
    });
  },
});

export { expect };
