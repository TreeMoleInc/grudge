import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StandingsTable } from "../../src/components/StandingsTable";
import type { FaultedEntryData, StandingEntryData, TournamentEntrant } from "../../src/api/types";

function entrant(id: string, name: string, ratingDelta: number | null = null): TournamentEntrant {
  return {
    user_id: "u1",
    automaton_id: id,
    automaton_version_id: null,
    automaton_name: name,
    automaton_version_name: "v1",
    owner_username: "alice",
    rating_snapshot: 1200,
    code_snapshot: "def decide(history):\n    return COOPERATE\n",
    rating_delta: ratingDelta,
  };
}

describe("StandingsTable", () => {
  it("renders standings in the order given (already sorted server-side), not re-sorted", () => {
    const standings: StandingEntryData[] = [
      { automaton_id: "b", total_points: 300, total_games: 100, points_per_game: 3.0 },
      { automaton_id: "a", total_points: 100, total_games: 100, points_per_game: 1.0 },
    ];
    render(
      <StandingsTable
        entrants={[entrant("a", "Alpha"), entrant("b", "Beta")]}
        standings={standings}
        faulted={[]}
      />
    );
    const rows = screen.getAllByRole("row").slice(1); // drop header row
    expect(rows[0]).toHaveTextContent("Beta");
    expect(rows[1]).toHaveTextContent("Alpha");
  });

  it("renders faulted entrants separately with a voided reason, not a placement", () => {
    const faulted: FaultedEntryData[] = [
      { automaton_id: "c", reason: "timed out", voided_match_ids: [] },
    ];
    render(
      <StandingsTable entrants={[entrant("c", "Charlie")]} standings={[]} faulted={faulted} />
    );
    expect(screen.getByText(/Voided — timed out/)).toBeInTheDocument();
  });

  it("calls onSelectAutomaton with the automaton id when a name is clicked", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const standings: StandingEntryData[] = [
      { automaton_id: "a", total_points: 100, total_games: 100, points_per_game: 1.0 },
    ];
    render(
      <StandingsTable
        entrants={[entrant("a", "Alpha")]}
        standings={standings}
        faulted={[]}
        onSelectAutomaton={onSelect}
      />
    );
    await user.click(screen.getByText("Alpha"));
    expect(onSelect).toHaveBeenCalledWith("a");
  });

  it("falls back to the raw automaton id when no matching entrant exists", () => {
    const standings: StandingEntryData[] = [
      { automaton_id: "ghost-id", total_points: 0, total_games: 0, points_per_game: 0 },
    ];
    render(<StandingsTable entrants={[]} standings={standings} faulted={[]} />);
    expect(screen.getByText("ghost-id")).toBeInTheDocument();
  });

  it("shows a signed rating delta for ranked entrants, and a dash when there isn't one", () => {
    const standings: StandingEntryData[] = [
      { automaton_id: "a", total_points: 400, total_games: 100, points_per_game: 4.0 },
      { automaton_id: "b", total_points: 100, total_games: 100, points_per_game: 1.0 },
    ];
    render(
      <StandingsTable
        entrants={[entrant("a", "Alpha", 14.6), entrant("b", "Beta", -8.2)]}
        standings={standings}
        faulted={[]}
      />
    );
    // Rounded for display - ratings themselves are integers.
    expect(screen.getByText("+15")).toBeInTheDocument();
    expect(screen.getByText("-8")).toBeInTheDocument();
  });

  it("shows a dash for a rating delta of null (unranked/sim, or a faulted entrant)", () => {
    const standings: StandingEntryData[] = [
      { automaton_id: "a", total_points: 100, total_games: 100, points_per_game: 1.0 },
    ];
    render(
      <StandingsTable entrants={[entrant("a", "Alpha", null)]} standings={standings} faulted={[]} />
    );
    const row = screen.getAllByRole("row")[1];
    expect(row).toHaveTextContent("—");
  });
});
