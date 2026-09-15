import { apiFetch } from "./client";
import type { AutomatonRecordRead, HeadToHeadRead, OpponentSummaryRead, UUID } from "./types";

export async function getAutomatonRecord(automatonId: UUID): Promise<AutomatonRecordRead> {
  return apiFetch<AutomatonRecordRead>(`/automata/${automatonId}/stats`);
}

export async function getAutomatonOpponents(automatonId: UUID): Promise<OpponentSummaryRead[]> {
  return apiFetch<OpponentSummaryRead[]>(`/automata/${automatonId}/opponents`);
}

export async function getHeadToHead(
  automatonId: UUID,
  opponentAutomatonId: UUID
): Promise<HeadToHeadRead> {
  return apiFetch<HeadToHeadRead>(`/automata/${automatonId}/head-to-head/${opponentAutomatonId}`);
}
