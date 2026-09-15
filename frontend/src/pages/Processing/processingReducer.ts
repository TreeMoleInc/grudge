import type { TournamentMessage } from "../../ws/useTournamentSocket";

export interface ProcessingState {
  progress: { completed: number; total: number; pct: number } | null;
  tournamentError: string | null;
  flaggedMessage: string | null;
  redirectTo: string | null;
}

export const initialProcessingState: ProcessingState = {
  progress: null,
  tournamentError: null,
  flaggedMessage: null,
  redirectTo: null,
};

/** Pure function: given the current state and one incoming WS message, what's
 * the next state? No socket, no navigation, no React - testable as plain data
 * in, data out (mirrors how backend/src/grudge_backend/services/matchmaking.py's
 * window-radius math is unit-tested without a DB or WS).
 */
export function reduceProcessingMessage(
  state: ProcessingState,
  message: TournamentMessage
): ProcessingState {
  switch (message.type) {
    case "progress":
      return {
        ...state,
        progress: {
          completed: message.data.completed_matches,
          total: message.data.total_matches,
          pct: message.data.pct,
        },
      };
    case "completed":
      return { ...state, redirectTo: message.data.redirect_url };
    case "error":
      return { ...state, tournamentError: message.data.message };
    case "automaton_flagged":
      return { ...state, flaggedMessage: `Automaton removed: ${message.data.reason}` };
    default:
      return state;
  }
}
