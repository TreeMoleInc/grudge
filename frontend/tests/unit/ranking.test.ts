import { describe, expect, it } from "vitest";
import { rankWithTies } from "../../src/lib/ranking";

describe("rankWithTies", () => {
  it("assigns sequential ranks when there are no ties", () => {
    const ranks = rankWithTies([
      { automaton_id: "a", points_per_game: 3 },
      { automaton_id: "b", points_per_game: 2 },
      { automaton_id: "c", points_per_game: 1 },
    ]);
    expect(ranks.get("a")).toBe(1);
    expect(ranks.get("b")).toBe(2);
    expect(ranks.get("c")).toBe(3);
  });

  it("gives equal points_per_game the same rank, skipping the next rank (1, 1, 3)", () => {
    const ranks = rankWithTies([
      { automaton_id: "a", points_per_game: 3 },
      { automaton_id: "b", points_per_game: 3 },
      { automaton_id: "c", points_per_game: 1 },
    ]);
    expect(ranks.get("a")).toBe(1);
    expect(ranks.get("b")).toBe(1);
    expect(ranks.get("c")).toBe(3);
  });

  it("handles every entrant tied", () => {
    const ranks = rankWithTies([
      { automaton_id: "a", points_per_game: 2 },
      { automaton_id: "b", points_per_game: 2 },
      { automaton_id: "c", points_per_game: 2 },
    ]);
    expect(ranks.get("a")).toBe(1);
    expect(ranks.get("b")).toBe(1);
    expect(ranks.get("c")).toBe(1);
  });
});
