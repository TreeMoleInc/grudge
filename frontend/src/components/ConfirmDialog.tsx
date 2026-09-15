import { useCallback, useState, type ReactNode } from "react";
import { Button } from "./Button";
import { Panel } from "./Panel";
import styles from "./Dialog.module.css";

interface ConfirmState {
  message: string;
  danger?: boolean;
  resolve: (value: boolean) => void;
}

/** In-site replacement for `window.confirm`. Render the returned `dialog`
 * node once, near the root of whichever component owns the hook instance.
 */
export function useConfirmDialog(): {
  dialog: ReactNode;
  confirm: (message: string, options?: { danger?: boolean }) => Promise<boolean>;
} {
  const [state, setState] = useState<ConfirmState | null>(null);

  const confirm = useCallback((message: string, options?: { danger?: boolean }) => {
    return new Promise<boolean>((resolve) => {
      setState({ message, danger: options?.danger, resolve });
    });
  }, []);

  function respond(value: boolean) {
    state?.resolve(value);
    setState(null);
  }

  const dialog = state && (
    <div className={styles.overlay} onClick={() => respond(false)}>
      <Panel raised className={styles.dialog} onClick={(e) => e.stopPropagation()}>
        <p className={styles.message}>{state.message}</p>
        <div className={styles.actions}>
          <Button variant="secondary" onClick={() => respond(false)}>
            Cancel
          </Button>
          <Button variant={state.danger ? "danger" : "primary"} onClick={() => respond(true)}>
            Confirm
          </Button>
        </div>
      </Panel>
    </div>
  );

  return { dialog, confirm };
}
