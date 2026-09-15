import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { AutomataMultiPicker } from "../../src/components/AutomataMultiPicker";
import { API_BASE_URL } from "../../src/api/client";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

const AUTOMATA = [
  {
    id: "1",
    user_id: "u",
    folder_id: null,
    name: "Tit for Tat",
    sort_order: 0,
    active_version_id: null,
    created_at: "",
    updated_at: "",
  },
  {
    id: "2",
    user_id: "u",
    folder_id: null,
    name: "Always Defect",
    sort_order: 1,
    active_version_id: null,
    created_at: "",
    updated_at: "",
  },
];

describe("AutomataMultiPicker", () => {
  it("shows a loading hint, then a checkbox per automaton", async () => {
    server.use(http.get(`${API_BASE_URL}/automata`, () => HttpResponse.json(AUTOMATA)));
    renderWithQueryClient(<AutomataMultiPicker value={[]} onChange={vi.fn()} />);

    expect(screen.getByText(/Loading your automata/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Tit for Tat")).toBeInTheDocument());
    expect(screen.getByText("Always Defect")).toBeInTheDocument();
    expect(screen.getAllByRole("checkbox")).toHaveLength(2);
  });

  it("shows a create-one-first hint when the user has no automata", async () => {
    server.use(http.get(`${API_BASE_URL}/automata`, () => HttpResponse.json([])));
    renderWithQueryClient(<AutomataMultiPicker value={[]} onChange={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByText(/don't have any automata yet/)).toBeInTheDocument()
    );
  });

  it("checks boxes matching the value prop", async () => {
    server.use(http.get(`${API_BASE_URL}/automata`, () => HttpResponse.json(AUTOMATA)));
    renderWithQueryClient(<AutomataMultiPicker value={["2"]} onChange={vi.fn()} />);
    await waitFor(() => expect(screen.getAllByRole("checkbox")).toHaveLength(2));
    const checkboxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    expect(checkboxes[0].checked).toBe(false);
    expect(checkboxes[1].checked).toBe(true);
  });

  it("calls onChange with the id added when checking a box", async () => {
    server.use(http.get(`${API_BASE_URL}/automata`, () => HttpResponse.json(AUTOMATA)));
    const onChange = vi.fn();
    const user = userEvent.setup();
    renderWithQueryClient(<AutomataMultiPicker value={[]} onChange={onChange} />);
    await waitFor(() => expect(screen.getAllByRole("checkbox")).toHaveLength(2));
    await user.click(screen.getAllByRole("checkbox")[0]);
    expect(onChange).toHaveBeenCalledWith(["1"]);
  });

  it("calls onChange with the id removed when unchecking a box", async () => {
    server.use(http.get(`${API_BASE_URL}/automata`, () => HttpResponse.json(AUTOMATA)));
    const onChange = vi.fn();
    const user = userEvent.setup();
    renderWithQueryClient(<AutomataMultiPicker value={["1", "2"]} onChange={onChange} />);
    await waitFor(() => expect(screen.getAllByRole("checkbox")).toHaveLength(2));
    await user.click(screen.getAllByRole("checkbox")[0]);
    expect(onChange).toHaveBeenCalledWith(["2"]);
  });
});
