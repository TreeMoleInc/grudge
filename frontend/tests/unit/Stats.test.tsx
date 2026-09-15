import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { Stats } from "../../src/pages/Automata/Stats";
import { API_BASE_URL } from "../../src/api/client";
import type {
  AutomatonRecordRead,
  HeadToHeadRead,
  MyTournamentEntryRead,
  OpponentSummaryRead,
} from "../../src/api/types";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const AUTOMATON_ID = "auto-1";

const record: AutomatonRecordRead = {
  automaton_id: AUTOMATON_ID,
  matches_played: 3,
  wins: 1,
  losses: 1,
  ties: 1,
  voided_matches: 0,
  average_points_per_game: 2.5,
};

const opponents: OpponentSummaryRead[] = [
  {
    opponent_automaton_id: "opp-1",
    opponent_name: "Rival Bot",
    opponent_owner_username: "bob",
    matches_played: 1,
    wins: 0,
    losses: 1,
    ties: 0,
    voided_matches: 0,
  },
];

const headToHead: HeadToHeadRead = {
  opponent_automaton_id: "opp-1",
  opponent_name: "Rival Bot",
  opponent_owner_username: "bob",
  wins: 0,
  losses: 1,
  ties: 0,
  voided_matches: 0,
  matches: [
    {
      id: "match-1",
      tournament_id: "tourney-1",
      automaton_a_id: AUTOMATON_ID,
      automaton_b_id: "opp-1",
      games_played: 10,
      score_a: 10,
      score_b: 30,
      status: "completed",
      void_reason: null,
      created_at: "2026-01-01T00:00:00Z",
    },
  ],
};

const emptyHistory: MyTournamentEntryRead[] = [];

function mockServer(overrides?: {
  record?: AutomatonRecordRead;
  opponents?: OpponentSummaryRead[];
}) {
  server.use(
    http.get(`${API_BASE_URL}/automata/${AUTOMATON_ID}/stats`, () =>
      HttpResponse.json(overrides?.record ?? record)
    ),
    http.get(`${API_BASE_URL}/automata/${AUTOMATON_ID}/opponents`, () =>
      HttpResponse.json(overrides?.opponents ?? opponents)
    ),
    http.get(`${API_BASE_URL}/automata/${AUTOMATON_ID}/head-to-head/opp-1`, () =>
      HttpResponse.json(headToHead)
    ),
    http.get(`${API_BASE_URL}/me/tournaments`, () => HttpResponse.json(emptyHistory))
  );
}

function renderStats() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Stats automatonId={AUTOMATON_ID} />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Stats", () => {
  it("shows the lifetime win-loss-tie record and average points per game", async () => {
    mockServer();
    renderStats();
    await waitFor(() => expect(screen.getByText("1-1-1")).toBeInTheDocument());
    expect(screen.getByText("2.50")).toBeInTheDocument();
  });

  it("shows a no-matches hint instead of a record when nothing has been played", async () => {
    mockServer({
      record: { ...record, matches_played: 0, wins: 0, losses: 0, ties: 0 },
      opponents: [],
    });
    renderStats();
    await waitFor(() =>
      expect(screen.getByText("This version hasn't played a match yet.")).toBeInTheDocument()
    );
  });

  it("lists opponents with their head-to-head record", async () => {
    mockServer();
    renderStats();
    await waitFor(() => expect(screen.getByText("Rival Bot")).toBeInTheDocument());
    expect(screen.getByText("bob")).toBeInTheDocument();
    expect(screen.getByText("0-1-0")).toBeInTheDocument();
  });

  it("expands a match-by-match breakdown when an opponent is clicked", async () => {
    mockServer();
    const user = userEvent.setup();
    renderStats();
    await waitFor(() => expect(screen.getByText("Rival Bot")).toBeInTheDocument());

    await user.click(screen.getByText("Rival Bot"));
    await waitFor(() => expect(screen.getByText(/10–30 over 10 games/)).toBeInTheDocument());

    await user.click(screen.getByText("Rival Bot"));
    expect(screen.queryByText(/10–30 over 10 games/)).not.toBeInTheDocument();
  });
});
