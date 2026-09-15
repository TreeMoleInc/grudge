import { apiFetch } from "./client";
import type { UUID, VersionCreate, VersionRead, VersionSummary, VersionUpdate } from "./types";

export async function listVersions(automatonId: UUID): Promise<VersionSummary[]> {
  return apiFetch<VersionSummary[]>(`/automata/${automatonId}/versions`);
}

export async function getVersion(automatonId: UUID, versionId: UUID): Promise<VersionRead> {
  return apiFetch<VersionRead>(`/automata/${automatonId}/versions/${versionId}`);
}

export async function createVersion(
  automatonId: UUID,
  payload: VersionCreate
): Promise<VersionRead> {
  return apiFetch<VersionRead>(`/automata/${automatonId}/versions`, {
    method: "POST",
    body: payload,
  });
}

// In-place edit/autosave - never creates a new row (the mutable save-slot
// behavior, CLAUDE.md §2).
export async function updateVersion(
  automatonId: UUID,
  versionId: UUID,
  payload: VersionUpdate
): Promise<VersionRead> {
  return apiFetch<VersionRead>(`/automata/${automatonId}/versions/${versionId}`, {
    method: "PATCH",
    body: payload,
  });
}

export async function deleteVersion(automatonId: UUID, versionId: UUID): Promise<void> {
  await apiFetch<void>(`/automata/${automatonId}/versions/${versionId}`, { method: "DELETE" });
}
