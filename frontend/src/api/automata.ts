import { apiFetch } from "./client";
import type {
  AutomatonCreate,
  AutomatonCreateResponse,
  AutomatonRead,
  AutomatonUpdate,
  UUID,
} from "./types";

export async function listAutomata(folderId?: UUID): Promise<AutomatonRead[]> {
  return apiFetch<AutomatonRead[]>("/automata", { query: { folder_id: folderId } });
}

export async function getAutomaton(id: UUID): Promise<AutomatonRead> {
  return apiFetch<AutomatonRead>(`/automata/${id}`);
}

export async function createAutomaton(payload: AutomatonCreate): Promise<AutomatonCreateResponse> {
  return apiFetch<AutomatonCreateResponse>("/automata", { method: "POST", body: payload });
}

export async function updateAutomaton(id: UUID, payload: AutomatonUpdate): Promise<AutomatonRead> {
  return apiFetch<AutomatonRead>(`/automata/${id}`, { method: "PATCH", body: payload });
}

export async function deleteAutomaton(id: UUID): Promise<void> {
  await apiFetch<void>(`/automata/${id}`, { method: "DELETE" });
}

export async function setActiveVersion(id: UUID, versionId: UUID): Promise<AutomatonRead> {
  return apiFetch<AutomatonRead>(`/automata/${id}/active-version`, {
    method: "PATCH",
    body: { version_id: versionId },
  });
}
