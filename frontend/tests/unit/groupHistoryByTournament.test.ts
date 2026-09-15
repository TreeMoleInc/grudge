import { describe, expect, it } from "vitest";
import { groupHistoryByTournament } from "../../src/pages/Play/groupHistoryByTournament";
import type { MyTournamentEntryRead } from "../../src/api/types";

function row(overrides: Partial<MyTournamentEntryRead>): MyTournamentEntryRead {
  return {
    tournament_id: "t1",
    tournament_type: "sim",
    status: "completed",
    created_at: "2026-01-01T00:00:00Z",
    automaton_id: "a1",
    automaton_name: "Bot A",
    automaton_version_id: "v1",
    automaton_version_name: "v1",
    placement: 1,
    voided: false,
    ...overrides,
  };
}

describe("groupHistoryByTournament", () => {
  it("keeps distinct tournaments as separate rows", () => {
    const groups = groupHistoryByTournament([
      row({ tournament_id: "t1" }),
      row({ tournament_id: "t2" }),
    ]);
    expect(groups.map((g) => g.tournament_id)).toEqual(["t1", "t2"]);
  });

  it("groups multiple of the caller's own automata in the same sim into one row", () => {
    const groups = groupHistoryByTournament([
      row({ tournament_id: "t1", automaton_id: "a1", automaton_name: "Bot A", placement: 1 }),
      row({ tournament_id: "t1", automaton_id: "a2", automaton_name: "Bot B", placement: 2 }),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0].entries).toHaveLength(2);
    expect(groups[0].entries.map((e) => e.automaton_name)).toEqual(["Bot A", "Bot B"]);
  });

  it("preserves the input's tournament order", () => {
    const groups = groupHistoryByTournament([
      row({ tournament_id: "t2" }),
      row({ tournament_id: "t1" }),
    ]);
    expect(groups.map((g) => g.tournament_id)).toEqual(["t2", "t1"]);
  });
});
