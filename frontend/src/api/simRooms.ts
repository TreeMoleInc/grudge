import { apiFetch } from "./client";
import type {
  LeaveSimRoomResponse,
  SimRoomEntryRead,
  SimRoomInviteRead,
  SimRoomRead,
  SimRoomWithEntriesRead,
  StartSimRoomResponse,
  UUID,
} from "./types";

export async function createSimRoom(): Promise<SimRoomRead> {
  return apiFetch<SimRoomRead>("/sim-rooms", { method: "POST" });
}

export async function getSimRoom(roomId: UUID): Promise<SimRoomWithEntriesRead> {
  return apiFetch<SimRoomWithEntriesRead>(`/sim-rooms/${roomId}`);
}

export async function joinSimRoom(code: string, automatonId: UUID): Promise<SimRoomEntryRead> {
  return apiFetch<SimRoomEntryRead>("/sim-rooms/join", {
    method: "POST",
    body: { code, automaton_id: automatonId },
  });
}

export async function removeSimRoomEntry(roomId: UUID, entryId: UUID): Promise<void> {
  await apiFetch<void>(`/sim-rooms/${roomId}/entries/${entryId}`, { method: "DELETE" });
}

export async function startSimRoom(roomId: UUID): Promise<StartSimRoomResponse> {
  return apiFetch<StartSimRoomResponse>(`/sim-rooms/${roomId}/start`, { method: "POST" });
}

export async function leaveSimRoom(roomId: UUID): Promise<LeaveSimRoomResponse> {
  return apiFetch<LeaveSimRoomResponse>(`/sim-rooms/${roomId}/leave`, { method: "POST" });
}

export async function inviteFriendToSimRoom(
  roomId: UUID,
  friendUserId: UUID
): Promise<SimRoomInviteRead> {
  return apiFetch<SimRoomInviteRead>(`/sim-rooms/${roomId}/invites`, {
    method: "POST",
    body: { friend_user_id: friendUserId },
  });
}

export async function listMySimRoomInvites(): Promise<SimRoomInviteRead[]> {
  return apiFetch<SimRoomInviteRead[]>("/sim-rooms/invites");
}
