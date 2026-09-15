import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { joinQueue, leaveQueue } from "../../api/matchmaking";
import { ApiError } from "../../api/client";
import type { QueueType, UUID } from "../../api/types";
import { useMatchmakingSocket } from "../../ws/useMatchmakingSocket";
import { AutomatonPicker } from "../../components/AutomatonPicker";
import { Button } from "../../components/Button";
import { Panel } from "../../components/Panel";
import { WaitingRoomStatus } from "../../components/WaitingRoomStatus";
import styles from "./RandomTab.module.css";

const HEARTBEAT_INTERVAL_MS = 20_000; // under the backend's 30s stale threshold

export function RandomTab() {
  const navigate = useNavigate();
  const [queueType, setQueueType] = useState<QueueType>("unranked");
  const [automatonId, setAutomatonId] = useState<UUID | null>(null);
  const [entryId, setEntryId] = useState<UUID | null>(null);
  const [status, setStatus] = useState<{ memberCount: number; capacity: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [joining, setJoining] = useState(false);
  const heartbeatTimer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  // Mirrors entryId for the unmount cleanup below - a plain effect dependent
  // on entryId would re-run leaveQueue on every entryId change, not just on
  // unmount, so the current value is read from a ref inside the cleanup instead.
  const entryIdRef = useRef<UUID | null>(null);
  useEffect(() => {
    entryIdRef.current = entryId;
  }, [entryId]);

  const { sendHeartbeat } = useMatchmakingSocket(entryId, (message) => {
    if (message.type === "count_update") {
      setStatus({ memberCount: message.data.member_count, capacity: message.data.capacity });
    } else if (message.type === "matched") {
      navigate(`/processing/${message.data.tournament_id}`);
    }
  });

  useEffect(() => {
    if (!entryId) return;
    heartbeatTimer.current = setInterval(sendHeartbeat, HEARTBEAT_INTERVAL_MS);
    return () => clearInterval(heartbeatTimer.current);
  }, [entryId, sendHeartbeat]);

  // Leaves the queue automatically when navigating away while still waiting -
  // without this, the entry stayed "waiting" server-side until the 30s
  // stale-heartbeat sweep, so an immediate rejoin hit AlreadyQueuedError and
  // surfaced as a confusing "Couldn't join the queue" error.
  useEffect(() => {
    return () => {
      if (entryIdRef.current) {
        leaveQueue(entryIdRef.current).catch(() => {
          // Best-effort - the entry will fall out via the stale-heartbeat
          // sweep if this fails (e.g. tab closing mid-request).
        });
      }
    };
  }, []);

  async function handleJoin() {
    // Guards against a double-click firing two joins before entryId is set
    // from the first response - without it, the second join's own real
    // queue entry is never tracked/displayed and just sits until the
    // backend's 30s stale-heartbeat sweep evicts it.
    if (!automatonId || joining) return;
    setJoining(true);
    setError(null);
    try {
      const response = await joinQueue(queueType, automatonId);
      if (response.tournament_id) {
        navigate(`/processing/${response.tournament_id}`);
        return;
      }
      // Set immediately from the join response itself, not just from the
      // WS count_update broadcast - that broadcast fires server-side before
      // this client's own WebSocket has finished connecting (it only starts
      // once entryId is set below), so for a lone first joiner it was never
      // seen and the screen was stuck on "Joining…" forever.
      setStatus({ memberCount: response.member_count, capacity: response.capacity });
      setEntryId(response.entry_id);
    } catch (err) {
      // Every service-layer exception this endpoint can raise (already
      // queued, no active version, failed pre-flight) already returns a
      // complete, professional-sentence-case detail string - render it
      // directly rather than guessing which one occurred client-side. This
      // is what surfaces a pre-flight failure's actual reason to the player.
      if (err instanceof ApiError && err.status === 400 && typeof err.detail === "string") {
        setError(err.detail);
      } else {
        setError("Could not join the queue. Please try again.");
      }
    } finally {
      setJoining(false);
    }
  }

  async function handleCancel() {
    if (!entryId) return;
    entryIdRef.current = null;
    await leaveQueue(entryId);
    setEntryId(null);
    setStatus(null);
  }

  return (
    <Panel>
      {!entryId ? (
        <div className={styles.form}>
          <label className={styles.field}>
            <span>Queue</span>
            <select
              value={queueType}
              onChange={(event) => setQueueType(event.target.value as QueueType)}
            >
              <option value="unranked">Unranked</option>
              <option value="ranked">Ranked</option>
            </select>
          </label>
          <label className={styles.field}>
            <span>Automaton</span>
            <AutomatonPicker value={automatonId} onChange={setAutomatonId} />
          </label>
          <Button variant="primary" onClick={handleJoin} disabled={!automatonId || joining}>
            Join queue
          </Button>
          {error && <p className={styles.error}>{error}</p>}
        </div>
      ) : (
        <div className={styles.waiting}>
          {status ? (
            <WaitingRoomStatus
              kind="count"
              memberCount={status.memberCount}
              capacity={status.capacity}
            />
          ) : (
            <p>Joining…</p>
          )}
          <Button variant="secondary" onClick={handleCancel}>
            Cancel
          </Button>
        </div>
      )}
    </Panel>
  );
}
