import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createSimRoom,
  getSimRoom,
  inviteFriendToSimRoom,
  joinSimRoom,
  leaveSimRoom,
  listMySimRoomInvites,
  removeSimRoomEntry,
  startSimRoom,
} from "../../api/simRooms";
import { listFriends } from "../../api/friends";
import type { SimRoomEntryRead, UUID } from "../../api/types";
import { useSimRoomSocket } from "../../ws/useSimRoomSocket";
import { ApiError } from "../../api/client";
import { useAuth } from "../../auth/useAuth";
import { AutomatonPicker } from "../../components/AutomatonPicker";
import { Button } from "../../components/Button";
import { Panel } from "../../components/Panel";
import styles from "./SimulateTab.module.css";

const MIN_ENTRANTS = 2; // matches backend/src/grudge_backend/services/sim_rooms.py's floor

export function SimulateTab() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const [roomId, setRoomId] = useState<UUID | null>(null);
  const [ownerUserId, setOwnerUserId] = useState<UUID | null>(null);
  const [inviteCode, setInviteCode] = useState<string | null>(null);
  const [entries, setEntries] = useState<SimRoomEntryRead[]>([]);
  const [codeInput, setCodeInput] = useState("");
  const [automatonId, setAutomatonId] = useState<UUID | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Guards handleCreateRoom/handleJoin against a double-click firing two
  // requests before the first response updates roomId - without it, the
  // second one's own real room/entry is never tracked or shown, leaving the
  // player an untracked owner of a stray room (or double-joined) with no
  // way to see or leave it from the UI.
  const [busy, setBusy] = useState(false);
  const roomIdRef = useRef<UUID | null>(null);
  const startedRef = useRef(false);
  useEffect(() => {
    roomIdRef.current = roomId;
  }, [roomId]);

  // Refetches the room's entries directly from the server, rather than
  // relying solely on the WS `entries_update` broadcast. This closes a real
  // race: a client's own action (join/remove) can complete - and the
  // server's broadcast can fire - before that same client's own WebSocket
  // has finished connecting (a fresh `useSimRoomSocket(roomId, ...)` handshake
  // takes a moment after roomId is first set), so the client misses its own
  // broadcast entirely and its entry silently never appears - this is what
  // showed up as "the host can't add automata." A direct GET is idempotent
  // (it replaces the whole list wholesale) so calling it alongside the WS
  // broadcast can never produce duplicate entries, unlike combining a create
  // response with the broadcast (see the join-by-code comment on handleJoin,
  // and this file's own prior duplicate-entries fix from live-testing).
  async function refreshRoom(id: UUID) {
    try {
      const room = await getSimRoom(id);
      setEntries(room.entries);
    } catch {
      // Best-effort - the next WS broadcast or poll tick will catch up.
    }
  }

  useEffect(() => {
    if (!roomId) return;
    // Deliberately not `refreshRoom(roomId)` here: react-hooks' set-state-in-
    // effect check flags a direct top-level call to a named async function
    // that (anywhere in its own body) sets state, even though that setState
    // only ever runs after `refreshRoom`'s own internal await - it doesn't
    // flag the exact same eventual setEntries call when it's written as an
    // inline `.then()`, which is a boundary the check does recognize.
    getSimRoom(roomId)
      .then((room) => setEntries(room.entries))
      .catch(() => {
        // Best-effort - the poll effect below or a WS broadcast will catch up.
      });
  }, [roomId]);

  // Backstop for a WebSocket that never connects at all (a flaky network, or
  // a proxy/firewall that strips the wss:// upgrade) - without this, a
  // player in that situation never sees anyone else join either, not just
  // their own entries. Mirrors RoomInvitesList's own poll below. Stops once
  // the tournament starts (startedRef flips before the navigate() away).
  useEffect(() => {
    if (!roomId) return;
    const interval = setInterval(() => {
      if (!startedRef.current) refreshRoom(roomId);
    }, 5000);
    return () => clearInterval(interval);
  }, [roomId]);

  function resetToInitial() {
    setRoomId(null);
    setOwnerUserId(null);
    setInviteCode(null);
    setEntries([]);
    setCodeInput("");
  }

  useSimRoomSocket(roomId, (message) => {
    if (message.type === "entries_update") {
      setEntries(message.data.entries);
    } else if (message.type === "started") {
      startedRef.current = true;
      navigate(`/processing/${message.data.tournament_id}`);
    } else if (message.type === "owner_changed") {
      setOwnerUserId(message.data.owner_user_id);
    } else if (message.type === "room_closed") {
      // Realistically only reaches a client other than whoever closed it if
      // the room's last owner left while someone else was still connected
      // but entry-less (an edge case, not the common path) - harmless to
      // reset either way, since resetToInitial() on an already-reset state
      // is a no-op.
      resetToInitial();
    }
  });

  // Leaves the room (removing every automaton the user entered, and handing
  // off/closing ownership server-side as needed - see services/sim_rooms.py's
  // leave_room) whenever this tab unmounts while still in an unstarted room -
  // covers both navigating away and an implicit "disconnect" (switching Play
  // sub-tabs, leaving the page). The explicit "Leave room" button below calls
  // the same endpoint directly without waiting for an unmount.
  useEffect(() => {
    return () => {
      const room = roomIdRef.current;
      if (!room || startedRef.current) return;
      leaveSimRoom(room).catch(() => {
        // Best-effort - the room stays open either way (e.g. tab closing
        // mid-request).
      });
    };
  }, []);

  async function handleCreateRoom() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const room = await createSimRoom();
      setRoomId(room.id);
      setOwnerUserId(room.owner_user_id);
      setInviteCode(room.invite_code);
      setCodeInput(room.invite_code);
    } finally {
      setBusy(false);
    }
  }

  async function handleJoin() {
    if (!automatonId || !codeInput || busy) return;
    setBusy(true);
    setError(null);
    try {
      const entry = await joinSimRoom(codeInput, automatonId);
      if (!roomId) {
        // Sets roomId, which triggers the hydration effect above - that
        // already refetches entries, so no need to do it again here.
        setRoomId(entry.sim_room_id);
      } else {
        // Already in the room (e.g. the owner adding a second automaton) -
        // roomId isn't changing, so nothing else will refetch. See
        // refreshRoom's own comment for why this can't be left to the WS
        // broadcast alone.
        await refreshRoom(roomId);
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError("That automaton is already in this room.");
      } else {
        setError("Could not join that room. Check the code and try again.");
        // A failed join (most commonly: the room's owner left/closed it
        // before this player joined) means any pending invite pointing at
        // this same code is now dead too - refetch immediately rather than
        // leaving a stale, now-unusable invite sitting in the list until the
        // next poll or page reload.
        await queryClient.invalidateQueries({ queryKey: ["sim-room-invites"] });
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove(entryId: UUID) {
    if (!roomId) return;
    await removeSimRoomEntry(roomId, entryId);
    await refreshRoom(roomId);
  }

  async function handleStart() {
    if (!roomId) return;
    try {
      await startSimRoom(roomId);
    } catch {
      setError(`At least ${MIN_ENTRANTS} entrants are required to start.`);
    }
  }

  async function handleLeaveRoom() {
    if (!roomId) return;
    try {
      await leaveSimRoom(roomId);
    } catch {
      // Best-effort - still reset the local view either way, since there's
      // nothing more useful to do with a failed leave request than retry by
      // creating/joining another room.
    }
    resetToInitial();
  }

  const isOwner = user && ownerUserId === user.id;

  return (
    <Panel>
      {!roomId && !inviteCode ? (
        <div className={styles.entry}>
          <Button variant="primary" onClick={handleCreateRoom} disabled={busy}>
            Create a room
          </Button>
          <div className={styles.divider}>or</div>
          <div className={styles.joinForm}>
            <input
              className={styles.codeInput}
              placeholder="Invite code"
              value={codeInput}
              onChange={(event) => setCodeInput(event.target.value)}
            />
            <AutomatonPicker value={automatonId} onChange={setAutomatonId} />
            <Button variant="secondary" onClick={handleJoin} disabled={!automatonId || !codeInput}>
              Join
            </Button>
          </div>
          {error && <p className={styles.error}>{error}</p>}
          <RoomInvitesList onSelectCode={setCodeInput} />
        </div>
      ) : (
        <div className={styles.room}>
          <div className={styles.roomHeader}>
            {inviteCode ? (
              <p className={styles.inviteCode}>
                Invite code: <strong>{inviteCode}</strong>
              </p>
            ) : (
              <span />
            )}
            <Button variant="secondary" onClick={handleLeaveRoom}>
              Leave room
            </Button>
          </div>
          {/* Always shown, not just before a first join - a room can
              plausibly take more than one of this user's automata (see
              services/sim_rooms.py's comment on that), and hiding this after
              one join made it impossible to add a second. */}
          <div className={styles.joinForm}>
            <AutomatonPicker value={automatonId} onChange={setAutomatonId} />
            <Button variant="secondary" onClick={handleJoin} disabled={!automatonId || busy}>
              Join with this automaton
            </Button>
          </div>
          {isOwner && roomId && <InviteFriendControl roomId={roomId} />}
          <ul className={styles.entryList}>
            {entries.map((entry) => {
              const isMine = user && entry.user_id === user.id;
              return (
                <li key={entry.id}>
                  {entry.automaton_name}{" "}
                  <span className={styles.ownerName}>({entry.owner_username})</span>
                  {(isOwner || isMine) && (
                    <button type="button" onClick={() => handleRemove(entry.id)}>
                      {isMine ? "leave" : "remove"}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
          {isOwner && (
            <Button
              variant="primary"
              onClick={handleStart}
              disabled={entries.length < MIN_ENTRANTS}
            >
              Start ({entries.length} entrants)
            </Button>
          )}
          {error && <p className={styles.error}>{error}</p>}
        </div>
      )}
    </Panel>
  );
}

// Pending invites from friends who've directly invited you to their room -
// an alternative to sharing the code out-of-band. No realtime push (Phase 5's
// friends system deliberately has none - see CLAUDE.md S2), so a stale
// invite (e.g. the owner left/closed the room before this player joined)
// would otherwise sit in the list until something happened to refetch it.
// handleJoin already invalidates this on a failed join for the interactive
// case; this short poll covers the passive case - just sitting on this tab
// while the invite silently dies - without needing a real push channel.
function RoomInvitesList({ onSelectCode }: { onSelectCode: (code: string) => void }) {
  const { data } = useQuery({
    queryKey: ["sim-room-invites"],
    queryFn: listMySimRoomInvites,
    refetchInterval: 4000,
    // TanStack Query pauses refetchInterval by default once the tab isn't
    // visible (document.hidden) - reasonable for most polling, but this list
    // is small/cheap and the whole point is a stale invite disappearing
    // without the player needing to do anything, including re-focus the tab.
    refetchIntervalInBackground: true,
  });

  if (!data || data.length === 0) return null;

  return (
    <div className={styles.invites}>
      <h3 className={styles.invitesHeading}>Room invites</h3>
      <ul className={styles.invitesList}>
        {data.map((invite) => (
          <li key={invite.id} className={styles.inviteRow}>
            <span>{invite.owner_username}&rsquo;s room</span>
            <Button variant="secondary" onClick={() => onSelectCode(invite.invite_code)}>
              Use code
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}

// Owner-only control for directly inviting a friend to the currently open
// room, instead of only sharing the invite code.
function InviteFriendControl({ roomId }: { roomId: UUID }) {
  const queryClient = useQueryClient();
  const { data: friends } = useQuery({ queryKey: ["friends"], queryFn: listFriends });
  const [selectedFriendId, setSelectedFriendId] = useState<UUID | "">("");
  const [status, setStatus] = useState<string | null>(null);

  async function handleInvite() {
    if (!selectedFriendId) return;
    setStatus(null);
    try {
      await inviteFriendToSimRoom(roomId, selectedFriendId);
      setStatus("Invited.");
      await queryClient.invalidateQueries({ queryKey: ["sim-room-invites"] });
    } catch (err) {
      setStatus(err instanceof ApiError ? String(err.detail) : "Could not send invite.");
    }
  }

  if (!friends || friends.length === 0) return null;

  return (
    <div className={styles.inviteFriend}>
      <select
        className={styles.friendSelect}
        value={selectedFriendId}
        onChange={(event) => setSelectedFriendId(event.target.value)}
      >
        <option value="" disabled>
          Invite a friend…
        </option>
        {friends.map((friend) => (
          <option key={friend.friend_user_id} value={friend.friend_user_id}>
            {friend.username}
          </option>
        ))}
      </select>
      <Button variant="secondary" onClick={handleInvite} disabled={!selectedFriendId}>
        Invite
      </Button>
      {status && <span className={styles.hint}>{status}</span>}
    </div>
  );
}
