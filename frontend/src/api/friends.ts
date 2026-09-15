import { apiFetch } from "./client";
import type {
  FriendAutomatonCodeRead,
  FriendProfileRead,
  FriendRead,
  FriendRequestRead,
  FriendSettingsRead,
  FriendSettingsUpdate,
  FriendVisibilityOverrideRead,
  FriendVisibilityOverrideUpdate,
  UUID,
} from "./types";

export async function sendFriendRequest(username: string): Promise<FriendRequestRead> {
  return apiFetch<FriendRequestRead>("/friends/requests", { method: "POST", body: { username } });
}

export async function listIncomingRequests(): Promise<FriendRequestRead[]> {
  return apiFetch<FriendRequestRead[]>("/friends/requests/incoming");
}

export async function listOutgoingRequests(): Promise<FriendRequestRead[]> {
  return apiFetch<FriendRequestRead[]>("/friends/requests/outgoing");
}

export async function acceptFriendRequest(requestId: UUID): Promise<FriendRead> {
  return apiFetch<FriendRead>(`/friends/requests/${requestId}/accept`, { method: "POST" });
}

// Cancel (by the sender) or decline (by the recipient) - same call either side.
export async function removeFriendRequest(requestId: UUID): Promise<void> {
  await apiFetch<void>(`/friends/requests/${requestId}`, { method: "DELETE" });
}

export async function listFriends(): Promise<FriendRead[]> {
  return apiFetch<FriendRead[]>("/friends");
}

export async function unfriend(friendUserId: UUID): Promise<void> {
  await apiFetch<void>(`/friends/${friendUserId}`, { method: "DELETE" });
}

export async function getFriendProfile(friendUserId: UUID): Promise<FriendProfileRead> {
  return apiFetch<FriendProfileRead>(`/friends/${friendUserId}/profile`);
}

export async function getFriendAutomatonCode(
  friendUserId: UUID,
  automatonId: UUID
): Promise<FriendAutomatonCodeRead> {
  return apiFetch<FriendAutomatonCodeRead>(`/friends/${friendUserId}/automata/${automatonId}/code`);
}

export async function getFriendSettings(): Promise<FriendSettingsRead> {
  return apiFetch<FriendSettingsRead>("/friends/settings");
}

export async function updateFriendSettings(
  payload: FriendSettingsUpdate
): Promise<FriendSettingsRead> {
  return apiFetch<FriendSettingsRead>("/friends/settings", { method: "PATCH", body: payload });
}

export async function getFriendVisibilityOverride(
  friendUserId: UUID
): Promise<FriendVisibilityOverrideRead> {
  return apiFetch<FriendVisibilityOverrideRead>(`/friends/${friendUserId}/visibility-override`);
}

export async function updateFriendVisibilityOverride(
  friendUserId: UUID,
  payload: FriendVisibilityOverrideUpdate
): Promise<FriendVisibilityOverrideRead> {
  return apiFetch<FriendVisibilityOverrideRead>(`/friends/${friendUserId}/visibility-override`, {
    method: "PATCH",
    body: payload,
  });
}
