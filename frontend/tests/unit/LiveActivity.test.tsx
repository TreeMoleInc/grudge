import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { LiveActivity } from "../../src/components/LiveActivity";
import { API_BASE_URL } from "../../src/api/client";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("LiveActivity", () => {
  it("renders nothing before the stats load", () => {
    server.use(
      http.get(`${API_BASE_URL}/stats/live`, () =>
        HttpResponse.json({ online_count: 3, in_activity_count: 1 })
      )
    );
    const { container } = renderWithQueryClient(<LiveActivity />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows both counts once loaded", async () => {
    server.use(
      http.get(`${API_BASE_URL}/stats/live`, () =>
        HttpResponse.json({ online_count: 5, in_activity_count: 2 })
      )
    );
    renderWithQueryClient(<LiveActivity />);
    await waitFor(() => expect(screen.getByText("5")).toBeInTheDocument());
    expect(screen.getByText("online", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText(/in a match or queue/)).toBeInTheDocument();
  });

  it("renders a zero count plainly, not as empty", async () => {
    server.use(
      http.get(`${API_BASE_URL}/stats/live`, () =>
        HttpResponse.json({ online_count: 0, in_activity_count: 0 })
      )
    );
    renderWithQueryClient(<LiveActivity />);
    await waitFor(() => expect(screen.getAllByText("0")).toHaveLength(2));
  });
});
