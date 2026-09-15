import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  acceptFriendRequest,
  getFriendAutomatonCode,
  getFriendProfile,
  getFriendVisibilityOverride,
  listFriends,
  listIncomingRequests,
  listOutgoingRequests,
  removeFriendRequest,
  sendFriendRequest,
  unfriend,
  updateFriendVisibilityOverride,
} from "../../api/friends";
import { ApiError } from "../../api/client";
import type {
  FriendRead,
  FriendVisibilityOverrideRead,
  OverrideVisibilityMode,
  UUID,
} from "../../api/types";
import { AppHeader } from "../../components/AppHeader";
import { AutomataMultiPicker } from "../../components/AutomataMultiPicker";
import { Button } from "../../components/Button";
import { CodeSnapshotViewer } from "../../components/CodeSnapshotViewer";
import { useConfirmDialog } from "../../components/ConfirmDialog";
import { Panel } from "../../components/Panel";
import { usePromptDialog } from "../../components/PromptDialog";
import { Tabs } from "../../components/Tabs";
import styles from "./FriendsPage.module.css";

type FriendsTabId = "friends" | "requests";

export function FriendsPage() {
  const [tab, setTab] = useState<FriendsTabId>("friends");
  const [error, setError] = useState<string | null>(null);
  const { dialog: promptDialog, prompt } = usePromptDialog();
  const queryClient = useQueryClient();

  async function handleAddFriend() {
    const username = await prompt("Username to friend?");
    if (!username) return;
    setError(null);
    try {
      await sendFriendRequest(username);
      await queryClient.invalidateQueries({ queryKey: ["friend-requests"] });
      setTab("requests");
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Could not send friend request.");
    }
  }

  return (
    <div>
      <AppHeader />
      <div className={styles.content}>
        <div className={styles.toolbar}>
          <Tabs
            tabs={[
              { id: "friends", label: "Friends" },
              { id: "requests", label: "Requests" },
            ]}
            active={tab}
            onChange={setTab}
          />
          <Button variant="primary" onClick={handleAddFriend}>
            + Add friend
          </Button>
        </div>
        {error && <p className={styles.error}>{error}</p>}
        {tab === "friends" ? <FriendsList /> : <RequestsPanels />}
      </div>
      {promptDialog}
    </div>
  );
}

function FriendsList() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["friends"], queryFn: listFriends });
  const [expanded, setExpanded] = useState<Set<UUID>>(new Set());
  const { dialog: confirmDialog, confirm } = useConfirmDialog();

  function toggleExpanded(friendUserId: UUID) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(friendUserId)) next.delete(friendUserId);
      else next.add(friendUserId);
      return next;
    });
  }

  async function handleUnfriend(friend: FriendRead) {
    if (!(await confirm(`Remove ${friend.username} as a friend?`, { danger: true }))) return;
    await unfriend(friend.friend_user_id);
    await queryClient.invalidateQueries({ queryKey: ["friends"] });
  }

  if (isLoading) return <p className={styles.hint}>Loading…</p>;
  if (!data || data.length === 0) {
    return <p className={styles.hint}>No friends yet - add one above.</p>;
  }

  return (
    <Panel>
      <ul className={styles.list}>
        {data.map((friend) => {
          const isExpanded = expanded.has(friend.friend_user_id);
          return (
            <li key={friend.friend_user_id} className={styles.item}>
              <button
                type="button"
                className={styles.row}
                onClick={() => toggleExpanded(friend.friend_user_id)}
              >
                <span>{friend.username}</span>
                <span className={styles.ratingCol}>{friend.rating}</span>
              </button>
              {isExpanded && (
                <div className={styles.detail}>
                  <FriendProfilePanel friendUserId={friend.friend_user_id} />
                  <VisibilityOverrideControl friendUserId={friend.friend_user_id} />
                  <Button variant="danger" onClick={() => handleUnfriend(friend)}>
                    Unfriend
                  </Button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {confirmDialog}
    </Panel>
  );
}

// The friend-profile view - username/rating + the automata visible to the
// current viewer under the two-tier visibility rules (CLAUDE.md S2). Lives
// inline in the Friends tab rather than a separate route, per product scope.
function FriendProfilePanel({ friendUserId }: { friendUserId: UUID }) {
  const { data, isLoading } = useQuery({
    queryKey: ["friend-profile", friendUserId],
    queryFn: () => getFriendProfile(friendUserId),
  });
  const [selectedAutomatonId, setSelectedAutomatonId] = useState<UUID | null>(null);

  if (isLoading) return <p className={styles.hint}>Loading profile…</p>;
  if (!data) return null;

  function toggleSelected(automatonId: UUID) {
    setSelectedAutomatonId((prev) => (prev === automatonId ? null : automatonId));
  }

  return (
    <div className={styles.profile}>
      <p className={styles.profileStats}>
        Rating: {data.rating} · Ranked tournaments played: {data.ranked_tournaments_played}
      </p>
      {data.visible_automata.length === 0 ? (
        <p className={styles.hint}>No automata visible to you.</p>
      ) : (
        <ul className={styles.automataList}>
          {data.visible_automata.map((automaton) => (
            <li key={automaton.id}>
              <button
                type="button"
                className={styles.automatonNameButton}
                onClick={() => toggleSelected(automaton.id)}
              >
                {automaton.name}
              </button>
            </li>
          ))}
        </ul>
      )}
      {selectedAutomatonId && (
        <FriendAutomatonCodePanel
          friendUserId={friendUserId}
          automatonId={selectedAutomatonId}
          onClose={() => setSelectedAutomatonId(null)}
        />
      )}
    </div>
  );
}

function FriendAutomatonCodePanel({
  friendUserId,
  automatonId,
  onClose,
}: {
  friendUserId: UUID;
  automatonId: UUID;
  onClose: () => void;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["friend-automaton-code", friendUserId, automatonId],
    queryFn: () => getFriendAutomatonCode(friendUserId, automatonId),
  });

  return (
    <div className={styles.codePanel}>
      <div className={styles.codePanelHeader}>
        <span className={styles.hint}>Code</span>
        <button
          type="button"
          className={styles.closeButton}
          onClick={onClose}
          aria-label="Close code panel"
        >
          ×
        </button>
      </div>
      {isLoading || !data ? (
        <p className={styles.hint}>Loading…</p>
      ) : (
        <CodeSnapshotViewer code={data.code} />
      )}
    </div>
  );
}

function VisibilityOverrideControl({ friendUserId }: { friendUserId: UUID }) {
  const { data, isLoading } = useQuery({
    queryKey: ["friend-override", friendUserId],
    queryFn: () => getFriendVisibilityOverride(friendUserId),
  });

  if (isLoading || !data) return <p className={styles.hint}>Loading visibility…</p>;
  // Keyed by friendUserId: a fresh mount per friend seeds local draft state
  // from that friend's own override, rather than syncing via an effect -
  // same pattern as CodeEditorArea's key={versionId}.
  return <VisibilityOverrideForm key={friendUserId} friendUserId={friendUserId} initial={data} />;
}

function VisibilityOverrideForm({
  friendUserId,
  initial,
}: {
  friendUserId: UUID;
  initial: FriendVisibilityOverrideRead;
}) {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<OverrideVisibilityMode>(initial.mode);
  const [automatonIds, setAutomatonIds] = useState<UUID[]>(initial.automaton_ids);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");

  async function handleSave() {
    setSaveState("saving");
    await updateFriendVisibilityOverride(friendUserId, { mode, automaton_ids: automatonIds });
    setSaveState("saved");
    await queryClient.invalidateQueries({ queryKey: ["friend-override", friendUserId] });
  }

  return (
    <div className={styles.overrideForm}>
      <label className={styles.overrideLabel}>
        Visibility for this friend
        <select
          className={styles.select}
          value={mode}
          onChange={(e) => {
            setMode(e.target.value as OverrideVisibilityMode);
            setSaveState("idle");
          }}
        >
          <option value="default">Default (inherit global)</option>
          <option value="show">Always show</option>
          <option value="hide">Always hide</option>
          <option value="specific">Choose specific automata</option>
        </select>
      </label>
      {mode === "specific" && (
        <AutomataMultiPicker
          value={automatonIds}
          onChange={(ids) => {
            setAutomatonIds(ids);
            setSaveState("idle");
          }}
        />
      )}
      <div className={styles.overrideActions}>
        <Button variant="secondary" onClick={handleSave}>
          {saveState === "saving" ? "Saving…" : "Save"}
        </Button>
        {saveState === "saved" && <span className={styles.savedHint}>Saved</span>}
      </div>
    </div>
  );
}

function RequestsPanels() {
  const queryClient = useQueryClient();
  const incoming = useQuery({
    queryKey: ["friend-requests", "incoming"],
    queryFn: listIncomingRequests,
  });
  const outgoing = useQuery({
    queryKey: ["friend-requests", "outgoing"],
    queryFn: listOutgoingRequests,
  });

  async function refreshAll() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["friend-requests"] }),
      queryClient.invalidateQueries({ queryKey: ["friends"] }),
    ]);
  }

  async function handleAccept(requestId: UUID) {
    await acceptFriendRequest(requestId);
    await refreshAll();
  }

  async function handleRemove(requestId: UUID) {
    await removeFriendRequest(requestId);
    await refreshAll();
  }

  return (
    <div className={styles.requestsGrid}>
      <Panel>
        <h3>Incoming</h3>
        {(incoming.data ?? []).length === 0 && <p className={styles.hint}>No incoming requests.</p>}
        <ul className={styles.list}>
          {(incoming.data ?? []).map((req) => (
            <li key={req.id} className={styles.requestRow}>
              <span>{req.from_username}</span>
              <div className={styles.requestActions}>
                <Button variant="primary" onClick={() => handleAccept(req.id)}>
                  Accept
                </Button>
                <Button variant="secondary" onClick={() => handleRemove(req.id)}>
                  Decline
                </Button>
              </div>
            </li>
          ))}
        </ul>
      </Panel>
      <Panel>
        <h3>Outgoing</h3>
        {(outgoing.data ?? []).length === 0 && <p className={styles.hint}>No outgoing requests.</p>}
        <ul className={styles.list}>
          {(outgoing.data ?? []).map((req) => (
            <li key={req.id} className={styles.requestRow}>
              <span>{req.to_username}</span>
              <Button variant="secondary" onClick={() => handleRemove(req.id)}>
                Cancel
              </Button>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
