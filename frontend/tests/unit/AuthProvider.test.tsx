import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { delay, http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { AuthProvider } from "../../src/auth/AuthProvider";
import { ME_QUERY_KEY } from "../../src/auth/AuthContext";
import { useAuth } from "../../src/auth/useAuth";
import { API_BASE_URL } from "../../src/api/client";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// Records every isLoading value it is rendered with, so a test can prove the
// page never went back into "loading" after its first settle - the exact thing
// that blanked the logged-out home page (HomePage renders nothing while
// isLoading) each time a visitor returned to the tab.
const seenLoading: boolean[] = [];
function Probe() {
  const { user, isLoading } = useAuth();
  seenLoading.push(isLoading);
  return <p>{isLoading ? "loading" : user ? `user:${user.username}` : "logged-out"}</p>;
}

function setup() {
  seenLoading.length = 0;
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>
  );
  return queryClient;
}

describe("AuthProvider", () => {
  it("treats a 401 as 'logged out', not as a failure", async () => {
    server.use(http.get(`${API_BASE_URL}/me`, () => new HttpResponse(null, { status: 401 })));
    setup();

    await screen.findByText("logged-out");
  });

  it("does not go back to loading when a logged-out visitor's check re-runs", async () => {
    let calls = 0;
    server.use(
      http.get(`${API_BASE_URL}/me`, async () => {
        calls += 1;
        await delay(40);
        return new HttpResponse(null, { status: 401 });
      })
    );
    const queryClient = setup();
    await screen.findByText("logged-out");

    const settledAt = seenLoading.length;
    // What a tab regaining focus / the network reconnecting does.
    // Deliberately not wrapped in act(): act() flushes React's updates only at
    // the end, merging the brief in-between "loading" render away - and that
    // brief render is exactly the flicker this test exists to catch. The
    // handler above is slow enough (40ms) to leave that state observable.
    await queryClient.refetchQueries({ queryKey: ME_QUERY_KEY });
    await waitFor(() => expect(calls).toBeGreaterThanOrEqual(2));

    expect(screen.getByText("logged-out")).toBeInTheDocument();
    expect(seenLoading.slice(settledAt).some(Boolean)).toBe(false);
  });

  it("keeps rendering when the check fails for a real reason (server down) and re-runs", async () => {
    let calls = 0;
    server.use(
      http.get(`${API_BASE_URL}/me`, async () => {
        calls += 1;
        await delay(40);
        return HttpResponse.error();
      })
    );
    const queryClient = setup();
    await screen.findByText("logged-out");

    const settledAt = seenLoading.length;
    // Deliberately not wrapped in act(): act() flushes React's updates only at
    // the end, merging the brief in-between "loading" render away - and that
    // brief render is exactly the flicker this test exists to catch. The
    // handler above is slow enough (40ms) to leave that state observable.
    await queryClient.refetchQueries({ queryKey: ME_QUERY_KEY });
    await waitFor(() => expect(calls).toBeGreaterThanOrEqual(2));

    expect(seenLoading.slice(settledAt).some(Boolean)).toBe(false);
  });

  it("still returns the user when logged in", async () => {
    server.use(
      http.get(`${API_BASE_URL}/me`, () =>
        HttpResponse.json({
          id: "11111111-1111-1111-1111-111111111111",
          username: "alice",
          username_is_default: false,
          avatar_url: null,
          rating: 1000,
          ranked_tournaments_played: 0,
          created_at: "2026-01-01T00:00:00Z",
        })
      )
    );
    setup();

    await screen.findByText("user:alice");
  });
});
