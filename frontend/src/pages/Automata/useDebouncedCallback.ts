import { useEffect, useRef } from "react";

/** Returns a stable function that delays invoking `callback` until `delayMs`
 * have passed since the last call - used for the editor's autosave.
 */
export function useDebouncedCallback<TArgs extends unknown[]>(
  callback: (...args: TArgs) => void,
  delayMs: number
): (...args: TArgs) => void {
  const callbackRef = useRef(callback);
  // Ref mutations must happen in an effect (or event handler), not during
  // render itself - this keeps the ref one commit behind `callback`, which is
  // fine here since it's only ever invoked later, from a debounced timer.
  useEffect(() => {
    callbackRef.current = callback;
  });
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const pendingArgsRef = useRef<TArgs | null>(null);

  useEffect(
    () => () => {
      clearTimeout(timerRef.current);
      // Flush a still-pending call instead of dropping it. The editor keys
      // its autosave-owning component by versionId/automatonId (see
      // CodeEditorArea.tsx), so switching versions/automata within the
      // debounce window unmounts this hook - previously that just cleared
      // the timer, silently discarding the player's last edit with no
      // warning shown anywhere.
      if (pendingArgsRef.current) {
        callbackRef.current(...pendingArgsRef.current);
      }
    },
    []
  );

  return (...args: TArgs) => {
    clearTimeout(timerRef.current);
    pendingArgsRef.current = args;
    timerRef.current = setTimeout(() => {
      pendingArgsRef.current = null;
      callbackRef.current(...args);
    }, delayMs);
  };
}
