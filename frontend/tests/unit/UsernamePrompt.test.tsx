import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { UsernamePrompt } from "../../src/components/UsernamePrompt";
import { API_BASE_URL } from "../../src/api/client";
import { AuthProvider } from "../../src/auth/AuthProvider";
import type { UserRead } from "../../src/api/types";

const DEFAULT_USER: UserRead = {
  id: "11111111-1111-1111-1111-111111111111",
  username: "google_abc123",
  username_is_default: true,
  avatar_url: null,
  rating: 1000,
  ranked_tournaments_played: 0,
  created_at: "2026-01-01T00:00:00Z",
};

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderPrompt() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <UsernamePrompt />
      </AuthProvider>
    </QueryClientProvider>
  );
}

describe("UsernamePrompt", () => {
  it("shows the prompt for an account still on its default username", async () => {
    server.use(http.get(`${API_BASE_URL}/me`, () => HttpResponse.json(DEFAULT_USER)));
    renderPrompt();

    await waitFor(() => expect(screen.getByText(/Choose a username/)).toBeInTheDocument());
  });

  it("does not show for an account that already chose a real username", async () => {
    server.use(
      http.get(`${API_BASE_URL}/me`, () =>
        HttpResponse.json({ ...DEFAULT_USER, username_is_default: false })
      )
    );
    renderPrompt();

    // Give the /me fetch a tick to resolve, then confirm nothing rendered.
    await waitFor(() => expect(screen.queryByText(/Choose a username/)).not.toBeInTheDocument());
  });

  it("dismisses on Skip without calling the API", async () => {
    server.use(http.get(`${API_BASE_URL}/me`, () => HttpResponse.json(DEFAULT_USER)));
    let patchCalled = false;
    server.use(
      http.patch(`${API_BASE_URL}/me`, () => {
        patchCalled = true;
        return new HttpResponse();
      })
    );
    const user = userEvent.setup();
    renderPrompt();

    await screen.findByText(/Choose a username/);
    await user.click(screen.getByRole("button", { name: "Skip for now" }));

    expect(screen.queryByText(/Choose a username/)).not.toBeInTheDocument();
    expect(patchCalled).toBe(false);
  });

  it("saving a valid name closes the prompt", async () => {
    server.use(http.get(`${API_BASE_URL}/me`, () => HttpResponse.json(DEFAULT_USER)));
    server.use(
      http.patch(`${API_BASE_URL}/me`, async ({ request }) => {
        const body = (await request.json()) as { username: string };
        return HttpResponse.json({
          ...DEFAULT_USER,
          username: body.username,
          username_is_default: false,
        });
      })
    );
    const user = userEvent.setup();
    renderPrompt();

    await screen.findByText(/Choose a username/);
    const input = screen.getByRole("textbox");
    await user.clear(input);
    await user.type(input, "realname");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(screen.queryByText(/Choose a username/)).not.toBeInTheDocument());
  });

  it("shows a friendly message on a 409 and stays open", async () => {
    server.use(http.get(`${API_BASE_URL}/me`, () => HttpResponse.json(DEFAULT_USER)));
    server.use(
      http.patch(`${API_BASE_URL}/me`, () =>
        HttpResponse.json({ detail: "That username is already taken." }, { status: 409 })
      )
    );
    const user = userEvent.setup();
    renderPrompt();

    await screen.findByText(/Choose a username/);
    const input = screen.getByRole("textbox");
    await user.clear(input);
    await user.type(input, "taken");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(screen.getByText(/already taken/)).toBeInTheDocument());
    // Still open - a failed save doesn't dismiss the prompt.
    expect(screen.getByText(/Choose a username/)).toBeInTheDocument();
  });
});
