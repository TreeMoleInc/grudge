import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getTournament } from "../../api/tournaments";
import { AppHeader } from "../../components/AppHeader";
import { Button } from "../../components/Button";
import { Panel } from "../../components/Panel";
import { StandingsTable } from "../../components/StandingsTable";
import { AutomatonMatchDrilldown } from "../../components/AutomatonMatchDrilldown";
import { CodeSnapshotViewer } from "../../components/CodeSnapshotViewer";
import { VoidedFlaggedBanner } from "../../components/VoidedFlaggedBanner";
import styles from "./ResultsPage.module.css";

const TYPE_LABEL: Record<string, string> = {
  ranked: "Ranked Tournament",
  unranked: "Unranked Tournament",
  sim: "Simulated Tournament",
};

export function ResultsPage() {
  const navigate = useNavigate();
  const { tournamentId } = useParams<{ tournamentId: string }>();
  const [selectedAutomatonId, setSelectedAutomatonId] = useState<string | null>(null);

  function toggleSelectedAutomaton(automatonId: string) {
    setSelectedAutomatonId((prev) => (prev === automatonId ? null : automatonId));
  }

  const { data: tournament, isLoading } = useQuery({
    queryKey: ["tournament", tournamentId],
    queryFn: () => getTournament(tournamentId as string),
    enabled: !!tournamentId,
  });

  if (isLoading) return <p className={styles.hint}>Loading…</p>;
  if (!tournament) return <p className={styles.hint}>Tournament not found.</p>;

  const selectedEntrant = tournament.entrants.find((e) => e.automaton_id === selectedAutomatonId);

  return (
    <div>
      <AppHeader />
      <div className={styles.content}>
        <div className={styles.titleRow}>
          <h1 className={styles.title}>
            {TYPE_LABEL[tournament.type] ?? "Tournament"}
            {tournament.type !== "ranked" && (
              <span className={styles.noRatingBadge}> · no rating change</span>
            )}
          </h1>
          <Button variant="secondary" onClick={() => navigate("/play")}>
            Return to Play
          </Button>
        </div>

        {tournament.status === "failed_voided" && (
          <VoidedFlaggedBanner scope="tournament" message={tournament.error_message ?? undefined} />
        )}

        {tournament.result && (
          <>
            <Panel>
              <h2>Standings</h2>
              <StandingsTable
                entrants={tournament.entrants}
                standings={tournament.result.standings}
                faulted={tournament.result.faulted}
                onSelectAutomaton={toggleSelectedAutomaton}
              />
            </Panel>

            {selectedEntrant?.code_snapshot && (
              <Panel>
                <div className={styles.codePanelHeader}>
                  <h2>{selectedEntrant.automaton_name ?? selectedEntrant.automaton_id}'s code</h2>
                  <button
                    type="button"
                    className={styles.closeButton}
                    onClick={() => setSelectedAutomatonId(null)}
                    aria-label="Close code panel"
                  >
                    ×
                  </button>
                </div>
                <p className={styles.hint}>
                  Frozen snapshot of what actually ran in this tournament - not their current
                  version.
                </p>
                <CodeSnapshotViewer code={selectedEntrant.code_snapshot} />
              </Panel>
            )}

            <Panel>
              <h2>Matches</h2>
              <AutomatonMatchDrilldown
                matches={tournament.result.matches}
                entrants={tournament.entrants}
              />
            </Panel>
          </>
        )}
      </div>
    </div>
  );
}
