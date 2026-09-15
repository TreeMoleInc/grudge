import { useCallback } from "react";
import { useWebSocket } from "./useWebSocket";
import type { UUID } from "../api/types";

export type MatchmakingMessage =
  | { type: "count_update"; data: { room_id: UUID; member_count: number; capacity: number } }
  | { type: "matched"; data: { tournament_id: UUID } };

export function useMatchmakingSocket(
  queueEntryId: UUID | null,
  onMessage: (message: MatchmakingMessage) => void
): { sendHeartbeat: () => void } {
  const { send } = useWebSocket<MatchmakingMessage>(
    queueEntryId ? `/matchmaking/queue/${queueEntryId}/ws` : null,
    onMessage
  );

  const sendHeartbeat = useCallback(() => send({ type: "heartbeat" }), [send]);

  return { sendHeartbeat };
}
