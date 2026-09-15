import { apiFetch } from "./client";
import type { FolderCreate, FolderRead, FolderUpdate, UUID } from "./types";

export async function listFolders(): Promise<FolderRead[]> {
  return apiFetch<FolderRead[]>("/folders");
}

export async function createFolder(payload: FolderCreate): Promise<FolderRead> {
  return apiFetch<FolderRead>("/folders", { method: "POST", body: payload });
}

export async function updateFolder(id: UUID, payload: FolderUpdate): Promise<FolderRead> {
  return apiFetch<FolderRead>(`/folders/${id}`, { method: "PATCH", body: payload });
}

export async function deleteFolder(id: UUID): Promise<void> {
  await apiFetch<void>(`/folders/${id}`, { method: "DELETE" });
}
