import { useState } from "react";
import type { MatchResultData, TournamentEntrant } from "../api/types";
import { MatchList } from "./MatchList";
import styles from "./MatchList.module.css";

interface AutomatonMatchDrilldownProps {
  matches: MatchResultData[];
  entrants: TournamentEntrant[];
}

// Results page match log, organized by automaton: click an automaton to
// expand the list of matches IT played (reusing MatchList for that filtered
// subset, so the existing match-row/RoundLog expand behavior is unchanged),
// which can then expand into a game-by-game log. While a game log is open,
// sibling automata collapse out of view and reappear once it's closed.
export function AutomatonMatchDrilldown({ matches, entrants }: AutomatonMatchDrilldownProps) {
  const [expandedAutomatonId, setExpandedAutomatonId] = useState<string | null>(null);
  const [gameLogOpen, setGameLogOpen] = useState(false);

  function toggleAutomaton(automatonId: string) {
    const next = expandedAutomatonId === automatonId ? null : automatonId;
    setExpandedAutomatonId(next);
    setGameLogOpen(false);
  }

  const visibleEntrants =
    gameLogOpen && expandedAutomatonId
      ? entrants.filter((e) => e.automaton_id === expandedAutomatonId)
      : entrants;

  return (
    <ul className={styles.list}>
      {visibleEntrants.map((entrant) => {
        const isExpanded = entrant.automaton_id === expandedAutomatonId;
        const ownMatches = matches.filter(
          (m) =>
            m.automaton_a_id === entrant.automaton_id || m.automaton_b_id === entrant.automaton_id
        );
        return (
          <li key={entrant.automaton_id} className={styles.item}>
            <button
              type="button"
              className={styles.row}
              onClick={() => toggleAutomaton(entrant.automaton_id)}
            >
              <span>{entrant.automaton_name ?? entrant.automaton_id}</span>
              <span>
                {ownMatches.length} match{ownMatches.length === 1 ? "" : "es"}
              </span>
            </button>
            {isExpanded && (
              <div className={styles.detail}>
                <MatchList
                  matches={ownMatches}
                  entrants={entrants}
                  onMatchExpandedChange={setGameLogOpen}
                />
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
