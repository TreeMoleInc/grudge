import { useQuery } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getAutomatonOpponents, getAutomatonRecord, getHeadToHead } from "../../api/matchHistory";
import { listMyTournaments } from "../../api/tournaments";
import type { UUID } from "../../api/types";
import { Panel } from "../../components/Panel";
import styles from "./Stats.module.css";

const TYPE_LABEL: Record<string, string> = { ranked: "Ranked", unranked: "Unranked", sim: "Sim" };

interface StatsProps {
  automatonId: UUID;
}

export function Stats({ automatonId }: StatsProps) {
  const navigate = useNavigate();
  const [expandedOpponentId, setExpandedOpponentId] = useState<UUID | null>(null);

  const recordQuery = useQuery({
    queryKey: ["automaton-record", automatonId],
    queryFn: () => getAutomatonRecord(automatonId),
  });
  const opponentsQuery = useQuery({
    queryKey: ["automaton-opponents", automatonId],
    queryFn: () => getAutomatonOpponents(automatonId),
  });
  const headToHeadQuery = useQuery({
    queryKey: ["head-to-head", automatonId, expandedOpponentId],
    queryFn: () => getHeadToHead(automatonId, expandedOpponentId as UUID),
    enabled: expandedOpponentId !== null,
  });
  const historyQuery = useQuery({
    queryKey: ["my-tournaments"],
    queryFn: () => listMyTournaments(),
  });

  // Automata page history is already scoped to one automaton (no automaton
  // name shown per row - just version, date, placement, per the Phase 4
  // plan). GET /me/tournaments has no automaton_id filter yet, so this
  // filters client-side.
  const rows = (historyQuery.data ?? []).filter((row) => row.automaton_id === automatonId);
  const record = recordQuery.data;
  const opponents = opponentsQuery.data ?? [];

  return (
    <div className={styles.stats}>
      <Panel>
        <h3>Lifetime record</h3>
        {recordQuery.isLoading && <p className={styles.hint}>Loading…</p>}
        {record && record.matches_played === 0 && (
          <p className={styles.hint}>This version hasn't played a match yet.</p>
        )}
        {record && record.matches_played > 0 && (
          <dl className={styles.recordGrid}>
            <div>
              <dt>Record</dt>
              <dd>
                {record.wins}-{record.losses}-{record.ties}
              </dd>
            </div>
            <div>
              <dt>Avg pts/game</dt>
              <dd>{record.average_points_per_game.toFixed(2)}</dd>
            </div>
            <div>
              <dt>Matches played</dt>
              <dd>{record.matches_played}</dd>
            </div>
            <div>
              <dt>Voided</dt>
              <dd>{record.voided_matches}</dd>
            </div>
          </dl>
        )}
      </Panel>

      <Panel>
        <h3>Head-to-head</h3>
        {opponentsQuery.isLoading && <p className={styles.hint}>Loading…</p>}
        {!opponentsQuery.isLoading && opponents.length === 0 && (
          <p className={styles.hint}>No opponents faced yet.</p>
        )}
        {opponents.length > 0 && (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Opponent</th>
                  <th>Owner</th>
                  <th>Record</th>
                </tr>
              </thead>
              <tbody>
                {opponents.map((opponent) => (
                  <Fragment key={opponent.opponent_automaton_id}>
                    <tr>
                      <td>
                        <button
                          type="button"
                          className={styles.nameButton}
                          onClick={() =>
                            setExpandedOpponentId((current) =>
                              current === opponent.opponent_automaton_id
                                ? null
                                : opponent.opponent_automaton_id
                            )
                          }
                        >
                          {opponent.opponent_name ?? opponent.opponent_automaton_id}
                        </button>
                      </td>
                      <td>{opponent.opponent_owner_username ?? "—"}</td>
                      <td>
                        {opponent.wins}-{opponent.losses}-{opponent.ties}
                        {opponent.voided_matches > 0 && ` (${opponent.voided_matches} voided)`}
                      </td>
                    </tr>
                    {expandedOpponentId === opponent.opponent_automaton_id && (
                      <tr>
                        <td colSpan={3} className={styles.detailCell}>
                          {headToHeadQuery.isLoading && <p className={styles.hint}>Loading…</p>}
                          {headToHeadQuery.data && (
                            <ul className={styles.matchList}>
                              {headToHeadQuery.data.matches.map((match) => (
                                <li key={match.id} className={styles.matchRow}>
                                  <button
                                    type="button"
                                    className={styles.matchLink}
                                    onClick={() => navigate(`/results/${match.tournament_id}`)}
                                  >
                                    <span>{new Date(match.created_at).toLocaleDateString()}</span>
                                    <span>
                                      {match.status === "voided"
                                        ? `Voided — ${match.void_reason ?? "Unknown reason."}`
                                        : `${match.score_a}–${match.score_b} over ${match.games_played} games`}
                                    </span>
                                  </button>
                                </li>
                              ))}
                            </ul>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel>
        <h3>Tournament history</h3>
        {historyQuery.isLoading && <p className={styles.hint}>Loading…</p>}
        {!historyQuery.isLoading && rows.length === 0 && (
          <p className={styles.hint}>This version hasn't played in any tournaments yet.</p>
        )}
        <ul className={styles.historyList}>
          {rows.map((row) => (
            <li key={`${row.tournament_id}-${row.automaton_id}`}>
              <button
                type="button"
                className={styles.historyRow}
                onClick={() => navigate(`/results/${row.tournament_id}`)}
              >
                <span>{row.automaton_version_name ?? "—"}</span>
                <span className={styles.typeBadge}>
                  {TYPE_LABEL[row.tournament_type] ?? row.tournament_type}
                </span>
                <span>{new Date(row.created_at).toLocaleDateString()}</span>
                <span>
                  {row.voided ? "Voided" : row.placement ? `#${row.placement}` : "In progress"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
