import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteAccount, logout, updateUsername } from "../../api/auth";
import { ApiError } from "../../api/client";
import { getFriendSettings, updateFriendSettings } from "../../api/friends";
import type { FriendSettingsRead, GlobalVisibilityMode, UUID } from "../../api/types";
import { AppHeader } from "../../components/AppHeader";
import { AutomataMultiPicker } from "../../components/AutomataMultiPicker";
import { Button } from "../../components/Button";
import { Panel } from "../../components/Panel";
import { useConfirmDialog } from "../../components/ConfirmDialog";
import { USERNAME_PATTERN } from "../../components/UsernamePrompt";
import { useAuth } from "../../auth/useAuth";
import { ME_QUERY_KEY } from "../../auth/AuthContext";
import styles from "./SettingsPage.module.css";

export function SettingsPage() {
  return (
    <div>
      <AppHeader />
      <div className={styles.content}>
        <AccountPanel />
        <FriendVisibilityPanel />
      </div>
    </div>
  );
}

export function AccountPanel() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { dialog, confirm } = useConfirmDialog();
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function handleLogout() {
    await logout();
    // setQueryData, not invalidateQueries: invalidating only triggers a
    // background refetch, and React Query keeps the last-good `data` on a
    // background-refetch error rather than clearing it - so the /me 401 that
    // follows a real logout would leave `user` (and RequireAuth's check)
    // still pointing at the stale logged-in value. Writing null directly
    // updates the cache immediately, regardless of what /me returns next.
    queryClient.setQueryData(ME_QUERY_KEY, null);
    navigate("/");
  }

  async function handleDeleteAccount() {
    setDeleteError(null);
    const confirmed = await confirm(
      "Delete your account permanently? Your automata and personal info are removed for good. " +
        "Your past tournament and match results stay, but your name in them is replaced with " +
        "an anonymous label. This can't be undone.",
      { danger: true }
    );
    if (!confirmed) return;

    try {
      await deleteAccount();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setDeleteError(String(err.detail));
      } else {
        setDeleteError("Could not delete your account. Please try again.");
      }
      return;
    }
    await queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY });
    navigate("/");
  }

  return (
    <Panel>
      <h2>Account</h2>
      <UsernameField />
      <div className={styles.accountActions}>
        <Button variant="secondary" onClick={handleLogout}>
          Log out
        </Button>
        <Button variant="danger" onClick={handleDeleteAccount}>
          Delete account
        </Button>
      </div>
      {deleteError && <p className={styles.error}>{deleteError}</p>}
      {dialog}
    </Panel>
  );
}

function UsernameField() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [value, setValue] = useState(user?.username ?? "");
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");
  const [error, setError] = useState<string | null>(null);

  if (!user) return null;

  const isValid = USERNAME_PATTERN.test(value);
  const isUnchanged = value === user.username;

  async function handleSave() {
    if (!isValid || isUnchanged) return;
    setSaveState("saving");
    setError(null);
    try {
      // Writes the fresh server response straight into the shared /me cache
      // rather than invalidateQueries - a background refetch there can lag
      // behind (the exact Log-out bug this file's history already fixed),
      // and every other place that reads the username (AppHeader, this
      // field itself) should show the new name immediately, not on the
      // query's own next refetch.
      const updated = await updateUsername(value);
      queryClient.setQueryData(ME_QUERY_KEY, updated);
      setSaveState("saved");
    } catch (err) {
      setSaveState("idle");
      if (err instanceof ApiError && err.status === 409) {
        setError("That username is already taken.");
      } else {
        setError(
          "Usernames must be 3-20 characters: letters, numbers, underscores, or hyphens only."
        );
      }
    }
  }

  return (
    <div className={styles.form}>
      <label className={styles.formLabel}>
        Username
        <input
          className={styles.textInput}
          value={value}
          maxLength={20}
          onChange={(e) => {
            setValue(e.target.value);
            setSaveState("idle");
            setError(null);
          }}
        />
      </label>
      <p className={styles.hint}>3-20 characters: letters, numbers, underscores, or hyphens.</p>
      <div className={styles.actions}>
        <Button
          variant="primary"
          onClick={handleSave}
          disabled={!isValid || isUnchanged || saveState === "saving"}
        >
          {saveState === "saving" ? "Saving…" : "Save"}
        </Button>
        {saveState === "saved" && <span className={styles.hint}>Saved</span>}
      </div>
      {error && <p className={styles.error}>{error}</p>}
    </div>
  );
}

function FriendVisibilityPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["friend-settings"],
    queryFn: getFriendSettings,
  });

  return (
    <Panel>
      <h2>Friend visibility</h2>
      <p className={styles.hint}>
        Controls which of your friends can see your automata by default. Individual friends can
        still be overridden from the Friends page.
      </p>
      {isLoading || !data ? (
        <p className={styles.hint}>Loading…</p>
      ) : (
        <FriendVisibilityForm initial={data} />
      )}
    </Panel>
  );
}

function FriendVisibilityForm({ initial }: { initial: FriendSettingsRead }) {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<GlobalVisibilityMode>(initial.global_mode);
  const [automatonIds, setAutomatonIds] = useState<UUID[]>(initial.automaton_ids);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");

  async function handleSave() {
    setSaveState("saving");
    await updateFriendSettings({ global_mode: mode, automaton_ids: automatonIds });
    setSaveState("saved");
    await queryClient.invalidateQueries({ queryKey: ["friend-settings"] });
  }

  return (
    <div className={styles.form}>
      <label className={styles.formLabel}>
        Default visibility
        <select
          className={styles.select}
          value={mode}
          onChange={(e) => {
            setMode(e.target.value as GlobalVisibilityMode);
            setSaveState("idle");
          }}
        >
          <option value="hide">Hide from all friends</option>
          <option value="show">Show to all friends</option>
          <option value="specific">Choose specific automata</option>
        </select>
      </label>
      {mode === "specific" && (
        <AutomataMultiPicker
          value={automatonIds}
          onChange={(ids) => {
            setAutomatonIds(ids);
            setSaveState("idle");
          }}
        />
      )}
      <div className={styles.actions}>
        <Button variant="primary" onClick={handleSave}>
          {saveState === "saving" ? "Saving…" : "Save"}
        </Button>
        {saveState === "saved" && <span className={styles.hint}>Saved</span>}
      </div>
    </div>
  );
}
