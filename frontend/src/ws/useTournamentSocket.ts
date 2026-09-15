import { useWebSocket } from "./useWebSocket";
import type { UUID } from "../api/types";

export type TournamentMessage =
  | { type: "progress"; data: { completed_matches: number; total_matches: number; pct: number } }
  | { type: "completed"; data: { redirect_url: string } }
  | { type: "error"; data: { reason: string; message: string } }
  | { type: "automaton_flagged"; data: { automaton_id: UUID; reason: string } };

export function useTournamentSocket(
  tournamentId: UUID | null,
  onMessage: (message: TournamentMessage) => void
): void {
  useWebSocket<TournamentMessage>(
    tournamentId ? `/tournaments/${tournamentId}/ws` : null,
    onMessage
  );
}
