import { useWebSocket } from "./useWebSocket";
import type { SimRoomEntryRead, UUID } from "../api/types";

export type SimRoomMessage =
  | { type: "entries_update"; data: { entries: SimRoomEntryRead[]; count: number } }
  | { type: "started"; data: { tournament_id: UUID } }
  | { type: "owner_changed"; data: { owner_user_id: UUID } }
  | { type: "room_closed"; data: Record<string, never> };

export function useSimRoomSocket(
  roomId: UUID | null,
  onMessage: (message: SimRoomMessage) => void
): void {
  useWebSocket<SimRoomMessage>(roomId ? `/sim-rooms/${roomId}/ws` : null, onMessage);
}
