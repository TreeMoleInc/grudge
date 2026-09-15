import { useQuery } from "@tanstack/react-query";
import { listAutomata } from "../api/automata";
import type { UUID } from "../api/types";
import styles from "./AutomataMultiPicker.module.css";

interface AutomataMultiPickerProps {
  value: UUID[];
  onChange: (ids: UUID[]) => void;
  disabled?: boolean;
}

// The "choose specific automata" allow-list picker, shared by the Settings
// page's global visibility allow-list and the Friends page's per-friend
// override allow-list (CLAUDE.md S2). Always the caller's own automata (same
// owner-scoped GET /automata as AutomatonPicker) - a checkbox list rather
// than a native <select multiple>, easier to style with the sharp-corners
// tokens and clearer to interact with for a handful of items.
export function AutomataMultiPicker({ value, onChange, disabled }: AutomataMultiPickerProps) {
  const { data, isLoading } = useQuery({ queryKey: ["automata"], queryFn: () => listAutomata() });

  if (isLoading) return <p className={styles.hint}>Loading your automata…</p>;
  if (!data || data.length === 0) {
    return <p className={styles.hint}>You don't have any automata yet - create one first.</p>;
  }

  function toggle(automatonId: UUID, checked: boolean) {
    onChange(checked ? [...value, automatonId] : value.filter((id) => id !== automatonId));
  }

  return (
    <ul className={styles.list}>
      {data.map((automaton) => (
        <li key={automaton.id}>
          <label className={styles.option}>
            <input
              type="checkbox"
              checked={value.includes(automaton.id)}
              disabled={disabled}
              onChange={(event) => toggle(automaton.id, event.target.checked)}
            />
            {automaton.name}
          </label>
        </li>
      ))}
    </ul>
  );
}
