import type { RoundLogEntry } from "../api/types";
import styles from "./RoundLog.module.css";

interface RoundLogProps {
  rounds: RoundLogEntry[];
  nameA: string;
  nameB: string;
}

// Game-by-game (round-level) view of one match - the Results page drill-down
// this needed the backend to stop stripping round data (see the Phase 4 plan
// and TODO.md's now-superseded "no round-by-round logs" item).
export function RoundLog({ rounds, nameA, nameB }: RoundLogProps) {
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th>Round</th>
          <th>{nameA}</th>
          <th>{nameB}</th>
          <th>Points</th>
        </tr>
      </thead>
      <tbody>
        {rounds.map((round) => (
          <tr key={round.round_index}>
            <td>{round.round_index + 1}</td>
            <td className={round.move_a === "DEFECT" ? styles.defect : styles.cooperate}>
              {round.move_a}
            </td>
            <td className={round.move_b === "DEFECT" ? styles.defect : styles.cooperate}>
              {round.move_b}
            </td>
            <td>
              {round.points_a} – {round.points_b}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
