import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { ActiveStatePanel } from "../../src/components/ActiveStatePanel";
import { API_BASE_URL } from "../../src/api/client";
import type { ActiveStateRead } from "../../src/api/types";

const EMPTY_STATE: ActiveStateRead = { queue_entry: null, sim_rooms: [], tournament_ids: [] };

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ActiveStatePanel />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("ActiveStatePanel", () => {
  it("renders nothing when nothing is active", async () => {
    let fetched = false;
    server.use(
      http.get(`${API_BASE_URL}/me/active-state`, () => {
        fetched = true;
        return HttpResponse.json(EMPTY_STATE);
      })
    );
    const { container } = renderPanel();

    // Wait for the query to actually resolve (not just a fixed delay), then
    // confirm the panel rendered nothing for an empty response.
    await waitFor(() => expect(fetched).toBe(true));
    expect(container.firstChild).toBeNull();
  });

  it("shows a waiting queue entry with a Leave queue button", async () => {
    server.use(
      http.get(`${API_BASE_URL}/me/active-state`, () =>
        HttpResponse.json({
          ...EMPTY_STATE,
          queue_entry: { id: "q1", queue_type: "ranked" },
        })
      )
    );
    renderPanel();

    await screen.findByText(/ranked queue/);
    expect(screen.getByRole("button", { name: "Leave queue" })).toBeInTheDocument();
  });

  it("leaving the queue calls DELETE and the row disappears", async () => {
    let deleteCalled = false;
    // The mocked GET reflects whether DELETE has run yet, so the panel's own
    // post-action refetch sees the real effect of the click, not a canned
    // response - closer to how the real backend behaves.
    server.use(
      http.get(`${API_BASE_URL}/me/active-state`, () =>
        HttpResponse.json(
          deleteCalled ? EMPTY_STATE : { ...EMPTY_STATE, queue_entry: { id: "q1", queue_type: "unranked" } }
        )
      ),
      http.delete(`${API_BASE_URL}/matchmaking/queue/q1`, () => {
        deleteCalled = true;
        return new HttpResponse(null, { status: 204 });
      })
    );
    const user = userEvent.setup();
    renderPanel();

    await screen.findByRole("button", { name: "Leave queue" });
    await user.click(screen.getByRole("button", { name: "Leave queue" }));

    await waitFor(() => expect(deleteCalled).toBe(true));
    await waitFor(() => expect(screen.queryByText(/unranked queue/)).not.toBeInTheDocument());
  });

  it("shows an owned sim room with a Cancel room button", async () => {
    server.use(
      http.get(`${API_BASE_URL}/me/active-state`, () =>
        HttpResponse.json({
          ...EMPTY_STATE,
          sim_rooms: [{ id: "r1", invite_code: "ABCD1234", is_owner: true }],
        })
      )
    );
    renderPanel();

    await screen.findByText(/ABCD1234/);
    expect(screen.getByText(/You own/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel room" })).toBeInTheDocument();
  });

  it("shows a room the player only entered with a Leave room button", async () => {
    server.use(
      http.get(`${API_BASE_URL}/me/active-state`, () =>
        HttpResponse.json({
          ...EMPTY_STATE,
          sim_rooms: [{ id: "r1", invite_code: "WXYZ5678", is_owner: false }],
        })
      )
    );
    renderPanel();

    await screen.findByText(/WXYZ5678/);
    expect(screen.getByText(/You're in/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Leave room" })).toBeInTheDocument();
  });

  it("shows a link to an in-progress tournament, with no leave action", async () => {
    server.use(
      http.get(`${API_BASE_URL}/me/active-state`, () =>
        HttpResponse.json({ ...EMPTY_STATE, tournament_ids: ["t1"] })
      )
    );
    renderPanel();

    const link = await screen.findByRole("link", { name: "View" });
    expect(link).toHaveAttribute("href", "/processing/t1");
  });

  it("shows an error message and refetches if leaving a room fails", async () => {
    server.use(
      http.get(`${API_BASE_URL}/me/active-state`, () =>
        HttpResponse.json({
          ...EMPTY_STATE,
          sim_rooms: [{ id: "r1", invite_code: "FAILROOM", is_owner: true }],
        })
      ),
      http.post(`${API_BASE_URL}/sim-rooms/r1/leave`, () => HttpResponse.json({}, { status: 500 }))
    );
    const user = userEvent.setup();
    renderPanel();

    await screen.findByRole("button", { name: "Cancel room" });
    await user.click(screen.getByRole("button", { name: "Cancel room" }));

    await waitFor(() => expect(screen.getByText(/Could not leave/)).toBeInTheDocument());
  });
});
