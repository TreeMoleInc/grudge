import type {
  MyTournamentEntryRead,
  TournamentStatus,
  TournamentType,
  UUID,
} from "../../api/types";

export interface GroupedTournamentEntry {
  automaton_id: UUID;
  automaton_name: string | null;
  automaton_version_name: string | null;
  placement: number | null;
  voided: boolean;
}

export interface GroupedTournamentHistory {
  tournament_id: UUID;
  tournament_type: TournamentType;
  status: TournamentStatus;
  created_at: string;
  entries: GroupedTournamentEntry[];
}

// A sim can contain more than one of the caller's own automata, so
// GET /me/tournaments returns one row per (tournament, automaton) pair - this
// groups those back into one row per tournament instance for display,
// preserving the API's newest-first order (first row seen for a given
// tournament_id determines its position).
export function groupHistoryByTournament(
  rows: MyTournamentEntryRead[]
): GroupedTournamentHistory[] {
  const groups = new Map<UUID, GroupedTournamentHistory>();
  for (const row of rows) {
    let group = groups.get(row.tournament_id);
    if (!group) {
      group = {
        tournament_id: row.tournament_id,
        tournament_type: row.tournament_type,
        status: row.status,
        created_at: row.created_at,
        entries: [],
      };
      groups.set(row.tournament_id, group);
    }
    group.entries.push({
      automaton_id: row.automaton_id,
      automaton_name: row.automaton_name,
      automaton_version_name: row.automaton_version_name,
      placement: row.placement,
      voided: row.voided,
    });
  }
  return Array.from(groups.values());
}
