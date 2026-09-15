import { useCallback, useState, type ReactNode } from "react";
import { Button } from "./Button";
import { Panel } from "./Panel";
import styles from "./Dialog.module.css";

interface PromptState {
  message: string;
  resolve: (value: string | null) => void;
}

/** In-site replacement for `window.prompt`. Returns the same
 * null-means-cancelled / string-means-submitted (possibly empty) contract,
 * so existing call sites only need their `window.prompt(...)` call swapped
 * for `await prompt(...)`. Render the returned `dialog` node once, near the
 * root of whichever component owns the hook instance.
 */
export function usePromptDialog(): {
  dialog: ReactNode;
  prompt: (message: string, initialValue?: string) => Promise<string | null>;
} {
  const [state, setState] = useState<PromptState | null>(null);
  const [value, setValue] = useState("");

  const prompt = useCallback((message: string, initialValue = "") => {
    return new Promise<string | null>((resolve) => {
      setValue(initialValue);
      setState({ message, resolve });
    });
  }, []);

  function submit() {
    state?.resolve(value);
    setState(null);
  }

  function cancel() {
    state?.resolve(null);
    setState(null);
  }

  const dialog = state && (
    <div className={styles.overlay} onClick={cancel}>
      <Panel raised className={styles.dialog} onClick={(e) => e.stopPropagation()}>
        <p className={styles.message}>{state.message}</p>
        <input
          autoFocus
          className={styles.input}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
            if (e.key === "Escape") cancel();
          }}
        />
        <div className={styles.actions}>
          <Button variant="secondary" onClick={cancel}>
            Cancel
          </Button>
          <Button variant="primary" onClick={submit}>
            OK
          </Button>
        </div>
      </Panel>
    </div>
  );

  return { dialog, prompt };
}
