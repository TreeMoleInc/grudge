import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { NotificationsMenu } from "../../src/components/NotificationsMenu";
import { API_BASE_URL } from "../../src/api/client";
import type { NotificationRead } from "../../src/api/types";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderMenu() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <NotificationsMenu />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const UNREAD = {
  id: "n1",
  type: "automaton_flagged",
  tournament_id: "t1",
  automaton_id: "a1",
  automaton_name: "My Bot",
  reason: "Timed out on round 12.",
  read_at: null,
  created_at: "2026-08-30T00:00:00Z",
};

describe("NotificationsMenu", () => {
  it("shows no badge when there are no notifications", async () => {
    server.use(http.get(`${API_BASE_URL}/notifications`, () => HttpResponse.json([])));
    renderMenu();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /notifications/i })).toBeInTheDocument()
    );
    expect(screen.queryByText("1")).not.toBeInTheDocument();
  });

  it("shows an unread count badge reflecting unread notifications", async () => {
    server.use(
      http.get(`${API_BASE_URL}/notifications`, () =>
        HttpResponse.json([UNREAD, { ...UNREAD, id: "n2", read_at: "2026-08-30T01:00:00Z" }])
      )
    );
    renderMenu();
    await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());
  });

  it("mark-all-read clears the badge", async () => {
    const user = userEvent.setup();
    // Stateful handlers (not a mid-test server.use() swap) - the POST mutates
    // the same object the GET reads from, avoiding a race between the click's
    // async handler and re-registering a new mock mid-flight.
    const state: { notifications: NotificationRead[] } = { notifications: [{ ...UNREAD }] };
    server.use(
      http.get(`${API_BASE_URL}/notifications`, () => HttpResponse.json(state.notifications)),
      http.post(`${API_BASE_URL}/notifications/read-all`, () => {
        state.notifications = state.notifications.map((n) => ({
          ...n,
          read_at: "2026-08-30T01:00:00Z",
        }));
        return new HttpResponse(null, { status: 204 });
      })
    );
    renderMenu();
    await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /notifications/i }));
    await user.click(screen.getByRole("button", { name: /mark all read/i }));

    await waitFor(() => expect(screen.queryByText("1")).not.toBeInTheDocument());
  });
});
