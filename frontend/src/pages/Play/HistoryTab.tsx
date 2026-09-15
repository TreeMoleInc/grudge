import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { listMyTournaments } from "../../api/tournaments";
import { groupHistoryByTournament } from "./groupHistoryByTournament";
import { Panel } from "../../components/Panel";
import styles from "./HistoryTab.module.css";

const TYPE_LABEL: Record<string, string> = { ranked: "Ranked", unranked: "Unranked", sim: "Sim" };

// Spans ALL of the user's automata (unlike the Automata page's history
// section, which is already scoped to one). GET /me/tournaments returns one
// row per (tournament, automaton) pair, so this groups sim tournaments (which
// can hold more than one of the caller's own automata) back into one row per
// tournament instance.
export function HistoryTab() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["my-tournaments"],
    queryFn: () => listMyTournaments(),
  });

  const groups = groupHistoryByTournament(data ?? []);

  if (isLoading) return <p className={styles.hint}>Loading…</p>;
  if (groups.length === 0) {
    return <p className={styles.hint}>No tournaments played yet.</p>;
  }

  return (
    <Panel>
      <ul className={styles.list}>
        {groups.map((group) => (
          <li key={group.tournament_id}>
            <button
              type="button"
              className={styles.row}
              onClick={() => navigate(`/results/${group.tournament_id}`)}
            >
              <span className={styles.entrants}>
                {group.entries.map((entry) => (
                  <span key={entry.automaton_id} className={styles.entrantLine}>
                    {entry.automaton_name ?? "—"}
                    {entry.voided
                      ? " — voided"
                      : entry.placement
                        ? ` — #${entry.placement}`
                        : " — in progress"}
                  </span>
                ))}
              </span>
              <span className={styles.typeBadge}>
                {TYPE_LABEL[group.tournament_type] ?? group.tournament_type}
              </span>
              <span>{new Date(group.created_at).toLocaleDateString()}</span>
            </button>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
