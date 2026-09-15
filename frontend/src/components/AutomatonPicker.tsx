import { useQuery } from "@tanstack/react-query";
import { listAutomata } from "../api/automata";
import type { UUID } from "../api/types";
import styles from "./AutomatonPicker.module.css";

interface AutomatonPickerProps {
  value: UUID | null;
  onChange: (automatonId: UUID | null) => void;
  disabled?: boolean;
}

// Always the caller's own automata (GET /automata is owner-scoped server-side
// - see backend/src/grudge_backend/routers/automata.py) - shared by the Play
// page's Random-queue join and Simulate-room join, per the Phase 4 plan.
export function AutomatonPicker({ value, onChange, disabled }: AutomatonPickerProps) {
  const { data, isLoading } = useQuery({ queryKey: ["automata"], queryFn: () => listAutomata() });

  if (isLoading) return <p className={styles.hint}>Loading your automata…</p>;
  if (!data || data.length === 0) {
    return <p className={styles.hint}>You don't have any automata yet - create one first.</p>;
  }

  return (
    <select
      className={styles.select}
      value={value ?? ""}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value || null)}
    >
      <option value="" disabled>
        Choose an automaton…
      </option>
      {data.map((automaton) => (
        <option key={automaton.id} value={automaton.id}>
          {automaton.name}
        </option>
      ))}
    </select>
  );
}
