import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MatchList } from "../../src/components/MatchList";
import type { MatchResultData, TournamentEntrant } from "../../src/api/types";

function entrant(id: string, name: string): TournamentEntrant {
  return {
    user_id: "u1",
    automaton_id: id,
    automaton_version_id: null,
    automaton_name: name,
    automaton_version_name: "v1",
    owner_username: "someone",
    rating_snapshot: 1000,
    code_snapshot: "def decide(history):\n    return COOPERATE\n",
    rating_delta: null,
  };
}

const match: MatchResultData = {
  automaton_a_id: "a",
  automaton_b_id: "b",
  games_played: 2,
  score_a: 5,
  score_b: 1,
  status: "completed",
  voided_side: null,
  void_reason: null,
  rounds: [
    { round_index: 0, move_a: "DEFECT", move_b: "COOPERATE", points_a: 5, points_b: 0 },
    { round_index: 1, move_a: "DEFECT", move_b: "DEFECT", points_a: 1, points_b: 1 },
  ],
};

describe("MatchList", () => {
  it("resolves names from entrants instead of showing raw automaton ids", () => {
    render(
      <MatchList
        matches={[match]}
        entrants={[entrant("a", "Always Defect"), entrant("b", "Tit for Tat")]}
      />
    );
    expect(screen.getByText("Always Defect vs Tit for Tat")).toBeInTheDocument();
  });

  it("falls back to the raw id when an entrant isn't found", () => {
    render(<MatchList matches={[match]} entrants={[]} />);
    expect(screen.getByText("a vs b")).toBeInTheDocument();
  });

  it("does not show the round log until the match row is clicked", () => {
    render(<MatchList matches={[match]} entrants={[entrant("a", "A"), entrant("b", "B")]} />);
    expect(screen.queryByText("Round")).not.toBeInTheDocument();
  });

  it("shows the full round-by-round log after clicking the match row, and hides it again on a second click", async () => {
    const user = userEvent.setup();
    render(<MatchList matches={[match]} entrants={[entrant("a", "A"), entrant("b", "B")]} />);

    await user.click(screen.getByText("A vs B"));
    expect(screen.getByText("Round")).toBeInTheDocument();
    // round 0: DEFECT/COOPERATE, round 1: DEFECT/DEFECT -> 3 DEFECT cells, 1 COOPERATE cell
    expect(screen.getAllByText("DEFECT")).toHaveLength(3);
    expect(screen.getByText("COOPERATE")).toBeInTheDocument();

    await user.click(screen.getByText("A vs B"));
    expect(screen.queryByText("Round")).not.toBeInTheDocument();
  });

  it("shows a voided match's reason instead of a score", () => {
    const voided: MatchResultData = {
      ...match,
      status: "voided",
      void_reason: "timed out",
      rounds: [],
    };
    render(<MatchList matches={[voided]} entrants={[entrant("a", "A"), entrant("b", "B")]} />);
    expect(screen.getByText("voided — timed out")).toBeInTheDocument();
  });
});
