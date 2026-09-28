import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchActiveState } from "../api/auth";
import { leaveQueue } from "../api/matchmaking";
import { leaveSimRoom } from "../api/simRooms";
import type { UUID } from "../api/types";
import { Button } from "./Button";
import styles from "./ActiveStatePanel.module.css";

const ACTIVE_STATE_QUERY_KEY = ["active-state"];

/** Shows exactly what's currently blocking account deletion
 * (services/account.py's get_active_state - the same three conditions
 * DELETE /me's own 409 refers to), with a Leave/Cancel button for each, so a
 * player who's stuck can clear it themselves instead of needing a database
 * query. Real support case this closes, 2026-09-28: a Simulate room's id
 * lives only in SimulateTab's own React state, never persisted anywhere -
 * a room orphaned by a dropped connection or a hard-closed tab (the owner
 * never got to click "Leave room") was previously undiscoverable from the
 * UI at all, even though the room is easy to leave once you know its id.
 * Renders nothing when nothing is active - the common case.
 */
export function ActiveStatePanel() {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ACTIVE_STATE_QUERY_KEY, queryFn: fetchActiveState });
  const [busyId, setBusyId] = useState<UUID | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function withRow(id: UUID, action: () => Promise<unknown>) {
    setBusyId(id);
    setError(null);
    try {
      await action();
    } catch {
      setError("Could not leave that - try again.");
    } finally {
      setBusyId(null);
      // Always refetch, even on error - if the item was already gone (e.g.
      // it cleared itself in the background), the panel should still catch
      // up to that rather than keep showing a stale row.
      await queryClient.invalidateQueries({ queryKey: ACTIVE_STATE_QUERY_KEY });
    }
  }

  if (!data) return null;
  const { queue_entry: queueEntry, sim_rooms: simRooms, tournament_ids: tournamentIds } = data;
  const hasAnything = queueEntry !== null || simRooms.length > 0 || tournamentIds.length > 0;
  if (!hasAnything) return null;

  return (
    <div className={styles.panel}>
      <p className={styles.heading}>
        This is what&rsquo;s currently blocking account deletion - leave each one, then try again.
      </p>
      <ul className={styles.list}>
        {queueEntry && (
          <li>
            <span>Waiting in the {queueEntry.queue_type} queue</span>
            <Button
              variant="secondary"
              disabled={busyId === queueEntry.id}
              onClick={() => withRow(queueEntry.id, () => leaveQueue(queueEntry.id))}
            >
              Leave queue
            </Button>
          </li>
        )}
        {simRooms.map((room) => (
          <li key={room.id}>
            <span>
              {room.is_owner ? "You own" : "You're in"} a Simulate room (code {room.invite_code})
            </span>
            <Button
              variant="secondary"
              disabled={busyId === room.id}
              onClick={() => withRow(room.id, () => leaveSimRoom(room.id))}
            >
              {room.is_owner ? "Cancel room" : "Leave room"}
            </Button>
          </li>
        ))}
        {tournamentIds.map((id) => (
          <li key={id}>
            <span>A tournament is in progress</span>
            <Link to={`/processing/${id}`}>View</Link>
          </li>
        ))}
      </ul>
      {error && <p className={styles.error}>{error}</p>}
    </div>
  );
}
