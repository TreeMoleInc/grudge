import { apiFetch } from "./client";
import type { JoinQueueResponse, QueueType, UUID } from "./types";

export async function joinQueue(
  queueType: QueueType,
  automatonId: UUID
): Promise<JoinQueueResponse> {
  return apiFetch<JoinQueueResponse>(`/matchmaking/${queueType}/join`, {
    method: "POST",
    body: { automaton_id: automatonId },
  });
}

export async function leaveQueue(entryId: UUID): Promise<void> {
  await apiFetch<void>(`/matchmaking/queue/${entryId}`, { method: "DELETE" });
}
