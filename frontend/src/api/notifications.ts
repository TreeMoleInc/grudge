import { apiFetch } from "./client";
import type { NotificationRead, UUID } from "./types";

export async function listNotifications(): Promise<NotificationRead[]> {
  return apiFetch<NotificationRead[]>("/notifications");
}

export async function markNotificationRead(notificationId: UUID): Promise<void> {
  await apiFetch<void>(`/notifications/${notificationId}/read`, { method: "POST" });
}

export async function markAllNotificationsRead(): Promise<void> {
  await apiFetch<void>("/notifications/read-all", { method: "POST" });
}
