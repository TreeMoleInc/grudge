import type { FaultedEntryData, StandingEntryData, TournamentEntrant } from "../api/types";
import { rankWithTies } from "../lib/ranking";
import styles from "./StandingsTable.module.css";

export interface StandingsTableProps {
  entrants: TournamentEntrant[];
  standings: StandingEntryData[];
  faulted: FaultedEntryData[];
  onSelectAutomaton?: (automatonId: string) => void;
}

function formatRatingDelta(delta: number | null): string {
  if (delta === null) return "—";
  const rounded = Math.round(delta);
  return rounded > 0 ? `+${rounded}` : String(rounded);
}

// Used by the Results page's full per-player breakdown. `result.standings` is
// already sorted desc by points_per_game (TournamentResult's own contract,
// see engine/src/grudge_engine/results.py) - this component doesn't re-sort,
// just renders in the order given, appending faulted entrants at the end
// since they have no placement.
export function StandingsTable({
  entrants,
  standings,
  faulted,
  onSelectAutomaton,
}: StandingsTableProps) {
  const entrantByAutomatonId = new Map(entrants.map((e) => [e.automaton_id, e]));
  const ranks = rankWithTies(standings);

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>#</th>
            <th>Automaton</th>
            <th>Owner</th>
            <th>Avg pts/game (this tournament)</th>
            <th>Rating at entry</th>
            <th>Rating Δ</th>
          </tr>
        </thead>
        <tbody>
          {standings.map((standing) => {
            const entrant = entrantByAutomatonId.get(standing.automaton_id);
            return (
              <tr key={standing.automaton_id}>
                <td>{ranks.get(standing.automaton_id)}</td>
                <td>
                  {onSelectAutomaton ? (
                    <button
                      type="button"
                      className={styles.nameButton}
                      onClick={() => onSelectAutomaton(standing.automaton_id)}
                    >
                      {entrant?.automaton_name ?? standing.automaton_id}
                    </button>
                  ) : (
                    (entrant?.automaton_name ?? standing.automaton_id)
                  )}
                </td>
                <td>{entrant?.owner_username ?? "—"}</td>
                <td>{standing.points_per_game.toFixed(2)}</td>
                <td>{entrant?.rating_snapshot ?? "—"}</td>
                <td>{formatRatingDelta(entrant?.rating_delta ?? null)}</td>
              </tr>
            );
          })}
          {faulted.map((entry) => {
            const entrant = entrantByAutomatonId.get(entry.automaton_id);
            return (
              <tr key={entry.automaton_id} className={styles.voidedRow}>
                <td>—</td>
                <td>{entrant?.automaton_name ?? entry.automaton_id}</td>
                <td>{entrant?.owner_username ?? "—"}</td>
                <td colSpan={3} className={styles.voidedLabel}>
                  Voided — {entry.reason}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
