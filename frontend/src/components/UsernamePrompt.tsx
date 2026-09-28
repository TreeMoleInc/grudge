import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { updateUsername } from "../api/auth";
import { ApiError } from "../api/client";
import { ME_QUERY_KEY } from "../auth/AuthContext";
import { useAuth } from "../auth/useAuth";
import { Button } from "./Button";
import { Panel } from "./Panel";
import styles from "./Dialog.module.css";

// Mirrors backend/src/grudge_backend/schemas/user.py's USERNAME_PATTERN
// exactly - kept as one exported constant so this file and
// pages/Settings/SettingsPage.tsx's own username field can't drift apart.
export const USERNAME_PATTERN = /^[A-Za-z0-9_-]{3,20}$/;

/** One-time "choose a username" nudge shown right after sign-in, while the
 * account still has its provider-derived default name
 * (user.username_is_default - see backend/models/user.py, migration 0011:
 * every account starts here, since the initial name is always the OAuth
 * email prefix, never a deliberate choice).
 *
 * Mounted once near the app root (App.tsx), as a sibling of <Routes> rather
 * than inside RequireAuth per-route - if it lived inside each route's own
 * RequireAuth wrapper instead, it would unmount/remount (and its local
 * "skipped" state would reset) on every single page navigation, popping up
 * again on every click instead of once per session. "Skip for now" is a
 * purely local dismiss with no server write, so it does return on the next
 * full page load/sign-in - a deliberate low-stakes nudge, not a gate the
 * player has to clear once and for all.
 */
export function UsernamePrompt() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [dismissed, setDismissed] = useState(false);
  const [value, setValue] = useState(user?.username ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (!user || !user.username_is_default || dismissed) return null;

  const isValid = USERNAME_PATTERN.test(value);

  async function handleSave() {
    if (!isValid) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateUsername(value);
      // Writing the response directly into the shared /me cache (not
      // invalidateQueries) is what makes this component stop rendering the
      // instant the save succeeds - user.username_is_default flips to false
      // in the very same update, no separate refetch to wait on.
      queryClient.setQueryData(ME_QUERY_KEY, updated);
    } catch (err) {
      setSaving(false);
      if (err instanceof ApiError && err.status === 409) {
        setError("That username is already taken.");
      } else {
        setError("3-20 characters: letters, numbers, underscores, or hyphens only.");
      }
    }
  }

  function skip() {
    setDismissed(true);
  }

  return (
    <div className={styles.overlay} onClick={skip}>
      <Panel raised className={styles.dialog} onClick={(e) => e.stopPropagation()}>
        <p className={styles.message}>
          Choose a username - right now you&rsquo;re signed up as{" "}
          <strong>{user.username}</strong>. Pick something else, or keep it as is.
        </p>
        <input
          autoFocus
          className={styles.input}
          value={value}
          maxLength={20}
          onChange={(e) => {
            setValue(e.target.value);
            setError(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleSave();
            if (e.key === "Escape") skip();
          }}
        />
        {error && <p className={styles.message}>{error}</p>}
        <div className={styles.actions}>
          <Button variant="secondary" onClick={skip}>
            Skip for now
          </Button>
          <Button variant="primary" onClick={handleSave} disabled={!isValid || saving}>
            {saving ? "Saving…" : "Save"}
          </Button>
        </div>
      </Panel>
    </div>
  );
}
