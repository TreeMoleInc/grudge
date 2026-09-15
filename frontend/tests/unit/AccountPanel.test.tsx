import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { AccountPanel } from "../../src/pages/Settings/SettingsPage";
import { API_BASE_URL } from "../../src/api/client";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AccountPanel />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AccountPanel - delete account", () => {
  it("shows a confirmation dialog before deleting, and does nothing if cancelled", async () => {
    const user = userEvent.setup();
    renderPanel();

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
    renderPanel();

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
    renderPanel();

    await user.click(screen.getByRole("button", { name: "Delete account" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() =>
      expect(screen.getByText(/active queue, room, or tournament/)).toBeInTheDocument()
    );
    // The panel itself is still here - a blocked deletion didn't navigate away.
    expect(screen.getByRole("button", { name: "Delete account" })).toBeInTheDocument();
  });
});
