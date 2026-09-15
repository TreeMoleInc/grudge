import { useState } from "react";
import type { MatchResultData, TournamentEntrant } from "../api/types";
import { RoundLog } from "./RoundLog";
import styles from "./MatchList.module.css";

interface MatchListProps {
  matches: MatchResultData[];
  entrants: TournamentEntrant[];
  // Notifies a parent (AutomatonMatchDrilldown) whenever a round log opens or
  // closes, so it can hide/restore sibling automaton sections. Optional and
  // unused by any other caller.
  onMatchExpandedChange?: (expanded: boolean) => void;
}

// Match-by-match view (Results page). Expanding one match reveals its
// game-by-game RoundLog - already fully supported by result.matches, no
// backend gap here (only the round-level drill-down needed a backend change).
export function MatchList({ matches, entrants, onMatchExpandedChange }: MatchListProps) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const nameFor = (automatonId: string) =>
    entrants.find((e) => e.automaton_id === automatonId)?.automaton_name ?? automatonId;

  function toggle(index: number) {
    const next = expandedIndex === index ? null : index;
    setExpandedIndex(next);
    onMatchExpandedChange?.(next !== null);
  }

  return (
    <ul className={styles.list}>
      {matches.map((match, index) => {
        const nameA = nameFor(match.automaton_a_id);
        const nameB = nameFor(match.automaton_b_id);
        const isExpanded = expandedIndex === index;
        return (
          <li key={`${match.automaton_a_id}-${match.automaton_b_id}`} className={styles.item}>
            <button type="button" className={styles.row} onClick={() => toggle(index)}>
              <span>
                {nameA} vs {nameB}
              </span>
              <span>
                {match.status === "voided" ? (
                  <span className={styles.voided}>voided — {match.void_reason}</span>
                ) : (
                  `${match.score_a} – ${match.score_b} (${match.games_played} rounds)`
                )}
              </span>
            </button>
            {isExpanded && match.rounds.length > 0 && (
              <div className={styles.detail}>
                <RoundLog rounds={match.rounds} nameA={nameA} nameB={nameB} />
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
