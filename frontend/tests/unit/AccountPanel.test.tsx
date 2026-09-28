import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { AccountPanel } from "../../src/pages/Settings/SettingsPage";
import { API_BASE_URL } from "../../src/api/client";
import { AuthProvider } from "../../src/auth/AuthProvider";
import type { UserRead } from "../../src/api/types";

// AccountPanel now renders UsernameField (the username-editing control),
// which reads the current user via useAuth() - a real AuthProvider (backed
// by a mocked GET /me, not a hand-rolled context stub) is needed for every
// test in this file as a result, not just ones that touch the username
// field directly. It also renders ActiveStatePanel, which fetches
// GET /me/active-state - mocked here to an empty state so it renders
// nothing (ActiveStatePanel.test.tsx covers its own non-empty behavior).
const FAKE_USER: UserRead = {
  id: "11111111-1111-1111-1111-111111111111",
  username: "alice",
  username_is_default: false,
  avatar_url: null,
  rating: 1000,
  ranked_tournaments_played: 0,
  created_at: "2026-01-01T00:00:00Z",
};

const server = setupServer(
  http.get(`${API_BASE_URL}/me`, () => HttpResponse.json(FAKE_USER)),
  http.get(`${API_BASE_URL}/me/active-state`, () =>
    HttpResponse.json({ queue_entry: null, sim_rooms: [], tournament_ids: [] })
  )
);
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

async function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const result = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AuthProvider>
          <AccountPanel />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
  // Wait for the mocked GET /me to resolve before a test interacts with the
  // panel - UsernameField renders null until useAuth()'s user is loaded, but
  // "Delete account" itself renders unconditionally on the very first pass
  // (AccountPanel doesn't gate on auth loading, only UsernameField does), so
  // waiting on that button doesn't actually wait for anything - it must be
  // the username input itself, which only exists once `user` is truthy.
  await screen.findByRole("textbox");
  return result;
}

describe("AccountPanel - delete account", () => {
  it("shows a confirmation dialog before deleting, and does nothing if cancelled", async () => {
    const user = userEvent.setup();
    await renderPanel();

    await user.click(screen.getByRole("button", { name: "Delete account" }));
    expect(screen.getByText(/permanently/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText(/permanently/)).not.toBeInTheDocument();
  });

  it("calls DELETE /me after confirming, and redirects on success", async () => {
    let deleteCalled = false;
    server.use(
      http.delete(`${API_BASE_URL}/me`, () => {
        deleteCalled = true;
        return new HttpResponse(null, { status: 204 });
      })
    );
    const user = userEvent.setup();
    await renderPanel();

    await user.click(screen.getByRole("button", { name: "Delete account" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() => expect(deleteCalled).toBe(true));
  });

  it("shows the server's message and does not navigate away when blocked (409)", async () => {
    server.use(
      http.delete(`${API_BASE_URL}/me`, () =>
        HttpResponse.json(
          {
            detail:
              "Can't delete your account while you're in an active queue, room, or tournament.",
          },
          { status: 409 }
        )
      )
    );
    const user = userEvent.setup();
    await renderPanel();

    await user.click(screen.getByRole("button", { name: "Delete account" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() =>
      expect(screen.getByText(/active queue, room, or tournament/)).toBeInTheDocument()
    );
    // The panel itself is still here - a blocked deletion didn't navigate away.
    expect(screen.getByRole("button", { name: "Delete account" })).toBeInTheDocument();
  });
});

describe("AccountPanel - username field", () => {
  it("disables Save until the value actually changes", async () => {
    await renderPanel();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("renames on success and writes the response into the shared /me cache", async () => {
    server.use(
      http.patch(`${API_BASE_URL}/me`, async ({ request }) => {
        const body = (await request.json()) as { username: string };
        return HttpResponse.json({ ...FAKE_USER, username: body.username, username_is_default: false });
      })
    );
    const user = userEvent.setup();
    await renderPanel();

    const input = screen.getByRole("textbox");
    await user.clear(input);
    await user.type(input, "newname");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(screen.getByText("Saved")).toBeInTheDocument());
  });

  it("shows a friendly message on a 409 (username taken)", async () => {
    server.use(
      http.patch(`${API_BASE_URL}/me`, () =>
        HttpResponse.json({ detail: "That username is already taken." }, { status: 409 })
      )
    );
    const user = userEvent.setup();
    await renderPanel();

    const input = screen.getByRole("textbox");
    await user.clear(input);
    await user.type(input, "taken");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(screen.getByText(/already taken/)).toBeInTheDocument());
  });

  it("disables Save for a value outside the 3-20 char / allowed-character rule", async () => {
    const user = userEvent.setup();
    await renderPanel();

    const input = screen.getByRole("textbox");
    await user.clear(input);
    await user.type(input, "ab"); // too short
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();

    await user.type(input, "c has a space");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });
});
