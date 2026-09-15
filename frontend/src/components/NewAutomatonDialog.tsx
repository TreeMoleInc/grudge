import { useCallback, useState, type ReactNode } from "react";
import { Button } from "./Button";
import { Panel } from "./Panel";
import styles from "./Dialog.module.css";

export interface NewAutomatonResult {
  name: string;
  shareWithFriends: boolean;
}

interface NewAutomatonState {
  resolve: (value: NewAutomatonResult | null) => void;
}

// Purpose-built dialog for the automaton-creation flow's "name + optional
// share with friends" checkbox (CLAUDE.md S2) - deliberately NOT a
// generalization of PromptDialog, whose 3 other callers (rename automaton,
// rename folder, new version) don't want a checkbox and shouldn't have their
// return contract changed for this one case.
export function useNewAutomatonDialog(): {
  dialog: ReactNode;
  promptNewAutomaton: () => Promise<NewAutomatonResult | null>;
} {
  const [state, setState] = useState<NewAutomatonState | null>(null);
  const [name, setName] = useState("");
  const [shareWithFriends, setShareWithFriends] = useState(false);

  const promptNewAutomaton = useCallback(() => {
    return new Promise<NewAutomatonResult | null>((resolve) => {
      setName("");
      setShareWithFriends(false);
      setState({ resolve });
    });
  }, []);

  function submit() {
    if (!name.trim()) return;
    state?.resolve({ name, shareWithFriends });
    setState(null);
  }

  function cancel() {
    state?.resolve(null);
    setState(null);
  }

  const dialog = state && (
    <div className={styles.overlay} onClick={cancel}>
      <Panel raised className={styles.dialog} onClick={(e) => e.stopPropagation()}>
        <p className={styles.message}>Name for the new automaton?</p>
        <input
          autoFocus
          className={styles.input}
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
            if (e.key === "Escape") cancel();
          }}
        />
        <label className={styles.checkboxRow}>
          <input
            type="checkbox"
            checked={shareWithFriends}
            onChange={(e) => setShareWithFriends(e.target.checked)}
          />
          Share with friends
        </label>
        <div className={styles.actions}>
          <Button variant="secondary" onClick={cancel}>
            Cancel
          </Button>
          <Button variant="primary" onClick={submit} disabled={!name.trim()}>
            OK
          </Button>
        </div>
      </Panel>
    </div>
  );

  return { dialog, promptNewAutomaton };
}
