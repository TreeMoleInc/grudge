import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "../api/notifications";
import type { NotificationRead } from "../api/types";
import styles from "./NotificationsMenu.module.css";

// Same low-frequency-per-user-event polling shape as SimulateTab.tsx's
// RoomInvitesList - plain REST + polling, not a new realtime channel
// (CLAUDE.md's established no-realtime-for-low-frequency-events pattern).
// refetchIntervalInBackground so a notification clears/appears without the
// player needing to re-focus the tab - the whole point of "durable" is
// reaching someone who isn't actively watching.
export function NotificationsMenu() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: listNotifications,
    refetchInterval: 4000,
    refetchIntervalInBackground: true,
  });

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  const notifications = data ?? [];
  const unreadCount = notifications.filter((n) => !n.read_at).length;

  async function handleSelect(notification: NotificationRead) {
    setOpen(false);
    if (!notification.read_at) {
      await markNotificationRead(notification.id);
      await queryClient.invalidateQueries({ queryKey: ["notifications"] });
    }
    if (notification.tournament_id) {
      navigate(`/results/${notification.tournament_id}`);
    }
  }

  async function handleMarkAllRead() {
    await markAllNotificationsRead();
    await queryClient.invalidateQueries({ queryKey: ["notifications"] });
  }

  return (
    <div className={styles.container} ref={containerRef}>
      <button
        type="button"
        className={styles.trigger}
        onClick={() => setOpen((value) => !value)}
        aria-label="Notifications"
      >
        Notifications
        {unreadCount > 0 && <span className={styles.badge}>{unreadCount}</span>}
      </button>
      {open && (
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span>Notifications</span>
            {unreadCount > 0 && (
              <button type="button" className={styles.markAllButton} onClick={handleMarkAllRead}>
                Mark all read
              </button>
            )}
          </div>
          {notifications.length === 0 ? (
            <p className={styles.empty}>Nothing here yet.</p>
          ) : (
            <ul className={styles.list}>
              {notifications.map((notification) => (
                <li key={notification.id}>
                  <button
                    type="button"
                    className={notification.read_at ? styles.row : styles.rowUnread}
                    onClick={() => handleSelect(notification)}
                  >
                    <span className={styles.rowTitle}>
                      {notification.automaton_name ?? "An automaton"} was removed
                    </span>
                    <span className={styles.rowReason}>{notification.reason}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
