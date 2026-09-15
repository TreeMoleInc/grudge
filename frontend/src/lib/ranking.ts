// Tie-aware placement, mirroring backend/src/grudge_backend/services/ranking.py's
// rank_with_ties (standard competition ranking: 1, 1, 3 - not dense 1, 1, 2).
// Duplicated rather than shared since the two can't share code across the
// Python/TS boundary.
export function rankWithTies(
  standings: { automaton_id: string; points_per_game: number }[]
): Map<string, number> {
  const ranks = new Map<string, number>();
  standings.forEach((entry, index) => {
    if (index > 0 && entry.points_per_game === standings[index - 1].points_per_game) {
      ranks.set(entry.automaton_id, ranks.get(standings[index - 1].automaton_id)!);
    } else {
      ranks.set(entry.automaton_id, index + 1);
    }
  });
  return ranks;
}
