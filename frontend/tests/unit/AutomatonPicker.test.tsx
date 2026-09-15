import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { AutomatonPicker } from "../../src/components/AutomatonPicker";
import { API_BASE_URL } from "../../src/api/client";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("AutomatonPicker", () => {
  it("shows a loading hint, then the caller's automata as options", async () => {
    server.use(
      http.get(`${API_BASE_URL}/automata`, () =>
        HttpResponse.json([
          {
            id: "1",
            user_id: "u",
            folder_id: null,
            name: "Tit for Tat",
            active_version_id: null,
            created_at: "",
            updated_at: "",
          },
          {
            id: "2",
            user_id: "u",
            folder_id: null,
            name: "Always Defect",
            active_version_id: null,
            created_at: "",
            updated_at: "",
          },
        ])
      )
    );
    renderWithQueryClient(<AutomatonPicker value={null} onChange={vi.fn()} />);

    expect(screen.getByText(/Loading your automata/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("combobox")).toBeInTheDocument());
    expect(screen.getByRole("option", { name: "Tit for Tat" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Always Defect" })).toBeInTheDocument();
  });

  it("shows a create-one-first hint when the user has no automata", async () => {
    server.use(http.get(`${API_BASE_URL}/automata`, () => HttpResponse.json([])));
    renderWithQueryClient(<AutomatonPicker value={null} onChange={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByText(/don't have any automata yet/)).toBeInTheDocument()
    );
  });

  it("calls onChange with the selected automaton's id", async () => {
    server.use(
      http.get(`${API_BASE_URL}/automata`, () =>
        HttpResponse.json([
          {
            id: "1",
            user_id: "u",
            folder_id: null,
            name: "Tit for Tat",
            active_version_id: null,
            created_at: "",
            updated_at: "",
          },
        ])
      )
    );
    const onChange = vi.fn();
    const user = userEvent.setup();
    renderWithQueryClient(<AutomatonPicker value={null} onChange={onChange} />);
    await waitFor(() => expect(screen.getByRole("combobox")).toBeInTheDocument());
    await user.selectOptions(screen.getByRole("combobox"), "1");
    expect(onChange).toHaveBeenCalledWith("1");
  });
});
