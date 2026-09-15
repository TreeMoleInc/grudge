import { apiFetch } from "./client";
import type { MyTournamentEntryRead, TournamentRead, UUID } from "./types";

export async function getTournament(id: UUID): Promise<TournamentRead> {
  return apiFetch<TournamentRead>(`/tournaments/${id}`);
}

export async function listMyTournaments(limit = 50, offset = 0): Promise<MyTournamentEntryRead[]> {
  return apiFetch<MyTournamentEntryRead[]>("/me/tournaments", { query: { limit, offset } });
}
