import { useEffect, useReducer } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getTournament } from "../../api/tournaments";
import { useTournamentSocket } from "../../ws/useTournamentSocket";
import { ME_QUERY_KEY } from "../../auth/AuthContext";
import { AppHeader } from "../../components/AppHeader";
import { Panel } from "../../components/Panel";
import { ProgressBar } from "../../components/ProgressBar";
import { VoidedFlaggedBanner } from "../../components/VoidedFlaggedBanner";
import { initialProcessingState, reduceProcessingMessage } from "./processingReducer";
import styles from "./ProcessingPage.module.css";

export function ProcessingPage() {
  const { tournamentId } = useParams<{ tournamentId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [state, dispatch] = useReducer(reduceProcessingMessage, initialProcessingState);

  // Handles refresh: if the tournament already finished/failed by the time
  // this page loads, skip straight to the outcome instead of opening a
  // socket that will never see the event that already happened.
  const tournamentQuery = useQuery({
    queryKey: ["tournament", tournamentId],
    queryFn: () => getTournament(tournamentId as string),
    enabled: !!tournamentId,
  });

  const alreadyDone = tournamentQuery.data?.status === "completed";
  const alreadyVoided = tournamentQuery.data?.status === "failed_voided";

  useEffect(() => {
    if (alreadyDone && tournamentId) {
      navigate(`/results/${tournamentId}`, { replace: true });
    }
  }, [alreadyDone, tournamentId, navigate]);

  // The reducer only computes `redirectTo` as data - navigating (and
  // invalidating the shared ["tournament", id] cache entry the Results page
  // also reads, so it refetches instead of serving this page's own
  // pre-completion snapshot) are side effects, so they belong here, not in
  // the pure reducer. Also invalidating ME_QUERY_KEY here (not just relying
  // on its own staleTime to eventually lapse) is what makes a ranked
  // tournament's rating change show up in the header immediately on landing
  // on Results, instead of however long it happens to take for the next
  // background refetch to fire - harmless no-op for unranked/sim, where
  // rating genuinely didn't change.
  useEffect(() => {
    if (state.redirectTo) {
      queryClient.invalidateQueries({ queryKey: ["tournament", tournamentId] });
      queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY });
      navigate(state.redirectTo);
    }
  }, [state.redirectTo, tournamentId, queryClient, navigate]);

  useTournamentSocket(
    tournamentQuery.data && !alreadyDone && !alreadyVoided ? (tournamentId ?? null) : null,
    dispatch
  );

  return (
    <div>
      <AppHeader />
      <div className={styles.content}>
        <Panel>
          {alreadyVoided || state.tournamentError ? (
            <VoidedFlaggedBanner scope="tournament" message={state.tournamentError ?? undefined} />
          ) : (
            <>
              <h2>Tournament in progress…</h2>
              <ProgressBar pct={state.progress?.pct ?? 0} />
              <p className={styles.detail}>
                {state.progress
                  ? `${state.progress.completed} / ${state.progress.total} matches complete`
                  : "Starting…"}
              </p>
            </>
          )}
        </Panel>
        {state.flaggedMessage && (
          <div className={styles.flagged}>
            <VoidedFlaggedBanner scope="automaton" message={state.flaggedMessage} />
          </div>
        )}
      </div>
    </div>
  );
}
