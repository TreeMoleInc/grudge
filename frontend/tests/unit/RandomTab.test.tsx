import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { RandomTab } from "../../src/pages/Play/RandomTab";
import { API_BASE_URL } from "../../src/api/client";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderTab() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <RandomTab />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function selectTheOnlyAutomaton() {
  const user = userEvent.setup();
  // Two comboboxes exist: queue-type (Unranked/Ranked) and the
  // AutomatonPicker's own select, in that DOM order.
  await waitFor(() => expect(screen.getAllByRole("combobox")).toHaveLength(2));
  const automatonSelect = screen.getAllByRole("combobox")[1];
  await user.selectOptions(automatonSelect, "bot-1");
  return user;
}

describe("RandomTab join failures", () => {
  it("renders the server's actual detail message for a pre-flight failure, not a generic fallback", async () => {
    server.use(
      http.get(`${API_BASE_URL}/automata`, () =>
        HttpResponse.json([
          {
            id: "bot-1",
            name: "My Bot",
            user_id: "u1",
            folder_id: null,
            sort_order: 0,
            active_version_id: "v1",
            created_at: "2026-08-30T00:00:00Z",
            updated_at: "2026-08-30T00:00:00Z",
          },
        ])
      ),
      http.post(`${API_BASE_URL}/matchmaking/unranked/join`, () =>
        HttpResponse.json(
          { detail: "Timed out on round 3 of the pre-flight check." },
          { status: 400 }
        )
      )
    );
    renderTab();
    const user = await selectTheOnlyAutomaton();
    await user.click(screen.getByRole("button", { name: /join queue/i }));

    await waitFor(() =>
      expect(screen.getByText("Timed out on round 3 of the pre-flight check.")).toBeInTheDocument()
    );
    expect(
      screen.queryByText("Could not join the queue. Please try again.")
    ).not.toBeInTheDocument();
  });

  it("falls back to a generic message when the server gives no detail string", async () => {
    server.use(
      http.get(`${API_BASE_URL}/automata`, () =>
        HttpResponse.json([
          {
            id: "bot-1",
            name: "My Bot",
            user_id: "u1",
            folder_id: null,
            sort_order: 0,
            active_version_id: "v1",
            created_at: "2026-08-30T00:00:00Z",
            updated_at: "2026-08-30T00:00:00Z",
          },
        ])
      ),
      http.post(
        `${API_BASE_URL}/matchmaking/unranked/join`,
        () => new HttpResponse(null, { status: 500 })
      )
    );
    renderTab();
    const user = await selectTheOnlyAutomaton();
    await user.click(screen.getByRole("button", { name: /join queue/i }));

    await waitFor(() =>
      expect(screen.getByText("Could not join the queue. Please try again.")).toBeInTheDocument()
    );
  });
});
