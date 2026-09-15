import { API_BASE_URL, apiFetch } from "./client";
import type { UserRead } from "./types";

// Full-page navigation, not a fetch call - hits the backend's OAuth redirect
// endpoint directly (see CLAUDE.md §2 and the Phase 4 plan). GitHub had one of
// these too until it was dropped as a sign-in provider, 2026-09-04.
export function googleLoginUrl(): string {
  return `${API_BASE_URL}/auth/google/login`;
}

export async function fetchMe(): Promise<UserRead> {
  return apiFetch<UserRead>("/me");
}

export async function logout(): Promise<void> {
  await apiFetch<void>("/auth/logout", { method: "POST" });
}

// Irreversible - see backend/services/account.py for exactly what this
// deletes vs. anonymizes. Throws ApiError(409) if the account is currently
// in an active queue/room/tournament.
export async function deleteAccount(): Promise<void> {
  await apiFetch<void>("/me", { method: "DELETE" });
}
