import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../../api/client";
import { listFolders, createFolder, updateFolder, deleteFolder } from "../../api/folders";
import {
  listAutomata,
  createAutomaton,
  updateAutomaton,
  deleteAutomaton,
} from "../../api/automata";
import type { AutomatonRead, FolderRead, UUID } from "../../api/types";
import { buildFolderTree, type FolderNode } from "./buildFolderTree";
import { Button } from "../../components/Button";
import { usePromptDialog } from "../../components/PromptDialog";
import { useConfirmDialog } from "../../components/ConfirmDialog";
import { useNewAutomatonDialog } from "../../components/NewAutomatonDialog";
import styles from "./Sidebar.module.css";

interface SidebarProps {
  selectedAutomatonId: UUID | null;
}

interface ContextMenuState {
  kind: "folder" | "automaton";
  id: UUID;
  x: number;
  y: number;
}

// Flat, indented list of folders for the "move to" submenu below - simplest
// way to offer every folder (including nested ones) in one list.
function flattenFolders(nodes: FolderNode[], depth = 0): { folder: FolderRead; depth: number }[] {
  return nodes.flatMap((node) => [
    { folder: node.folder, depth },
    ...flattenFolders(node.children, depth + 1),
  ]);
}

function duplicateNameMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError && err.status === 409 ? String(err.detail) : fallback;
}

export function Sidebar({ selectedAutomatonId }: SidebarProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [collapsed, setCollapsed] = useState<Set<UUID>>(new Set());
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [moveMenuOpen, setMoveMenuOpen] = useState(false);
  // Shown inline rather than relying solely on a dismissible browser alert()
  // for something as easy to miss as a duplicate-name rejection.
  const [error, setError] = useState<string | null>(null);
  const { dialog: promptDialog, prompt } = usePromptDialog();
  const { dialog: confirmDialog, confirm } = useConfirmDialog();
  const { dialog: newAutomatonDialog, promptNewAutomaton } = useNewAutomatonDialog();

  const foldersQuery = useQuery({ queryKey: ["folders"], queryFn: listFolders });
  const automataQuery = useQuery({ queryKey: ["automata"], queryFn: () => listAutomata() });

  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["folders"] }),
      queryClient.invalidateQueries({ queryKey: ["automata"] }),
    ]);
  }

  function toggleCollapsed(folderId: UUID) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(folderId)) next.delete(folderId);
      else next.add(folderId);
      return next;
    });
  }

  function openContextMenu(event: React.MouseEvent, kind: "folder" | "automaton", id: UUID) {
    event.preventDefault();
    event.stopPropagation();
    setError(null);
    setMoveMenuOpen(false);
    setContextMenu({ kind, id, x: event.clientX, y: event.clientY });
  }

  function closeContextMenu() {
    setContextMenu(null);
    setMoveMenuOpen(false);
  }

  async function handleNewAutomaton(folderId: UUID | null) {
    const result = await promptNewAutomaton();
    if (!result) return;
    setError(null);
    try {
      const created = await createAutomaton({
        name: result.name,
        folder_id: folderId ?? undefined,
        share_with_friends: result.shareWithFriends,
      });
      await refresh();
      navigate(`/automata/${created.id}`);
    } catch (err) {
      setError(duplicateNameMessage(err, "Could not create automaton."));
    }
  }

  async function handleNewFolder(parentId: UUID | null) {
    const name = await prompt("Folder name?");
    if (!name) return;
    await createFolder({ name, parent_id: parentId ?? undefined });
    await refresh();
  }

  async function handleRenameAutomaton(automaton: AutomatonRead) {
    const name = await prompt("Rename automaton", automaton.name);
    if (!name || name === automaton.name) return;
    setError(null);
    try {
      await updateAutomaton(automaton.id, { name });
      await refresh();
    } catch (err) {
      setError(duplicateNameMessage(err, "Could not rename automaton."));
    }
  }

  async function handleDeleteAutomaton(automaton: AutomatonRead) {
    if (!(await confirm(`Delete "${automaton.name}"? This can't be undone.`, { danger: true })))
      return;
    await deleteAutomaton(automaton.id);
    await refresh();
  }

  async function handleMoveAutomaton(automaton: AutomatonRead, folderId: UUID | null) {
    if (folderId === automaton.folder_id) return;
    await updateAutomaton(automaton.id, { folder_id: folderId });
    await refresh();
  }

  async function handleRenameFolder(folder: FolderRead) {
    const name = await prompt("Rename folder", folder.name);
    if (!name || name === folder.name) return;
    await updateFolder(folder.id, { name });
    await refresh();
  }

  async function handleDeleteFolder(folder: FolderRead) {
    if (!(await confirm(`Delete folder "${folder.name}"?`, { danger: true }))) return;
    setError(null);
    try {
      await deleteFolder(folder.id);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Could not delete folder.");
    }
  }

  async function handleMoveFolder(folder: FolderRead, parentId: UUID | null) {
    if (parentId === folder.parent_id) return;
    setError(null);
    try {
      await updateFolder(folder.id, { parent_id: parentId });
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Could not move folder.");
    }
  }

  const { roots, rootAutomata } = useMemo(
    () => buildFolderTree(foldersQuery.data ?? [], automataQuery.data ?? []),
    [foldersQuery.data, automataQuery.data]
  );

  const allFoldersFlat = useMemo(() => flattenFolders(roots), [roots]);

  const contextTarget: FolderRead | AutomatonRead | undefined =
    contextMenu?.kind === "folder"
      ? (foldersQuery.data ?? []).find((f) => f.id === contextMenu.id)
      : (automataQuery.data ?? []).find((a) => a.id === contextMenu?.id);

  async function handleContextRename() {
    if (!contextMenu || !contextTarget) return;
    if (contextMenu.kind === "folder") await handleRenameFolder(contextTarget as FolderRead);
    else await handleRenameAutomaton(contextTarget as AutomatonRead);
    closeContextMenu();
  }

  async function handleContextDelete() {
    if (!contextMenu || !contextTarget) return;
    if (contextMenu.kind === "folder") await handleDeleteFolder(contextTarget as FolderRead);
    else await handleDeleteAutomaton(contextTarget as AutomatonRead);
    closeContextMenu();
  }

  async function handleContextMoveTo(targetFolderId: UUID | null) {
    if (!contextMenu || !contextTarget) return;
    if (contextMenu.kind === "folder") {
      await handleMoveFolder(contextTarget as FolderRead, targetFolderId);
    } else {
      await handleMoveAutomaton(contextTarget as AutomatonRead, targetFolderId);
    }
    closeContextMenu();
  }

  if (foldersQuery.isLoading || automataQuery.isLoading) {
    return <p className={styles.hint}>Loading…</p>;
  }

  const moveTargets =
    contextMenu?.kind === "folder"
      ? allFoldersFlat.filter((entry) => entry.folder.id !== contextMenu.id)
      : allFoldersFlat;

  return (
    <div className={styles.sidebar} onClick={closeContextMenu}>
      <div className={styles.toolbar}>
        <Button variant="secondary" onClick={() => handleNewFolder(null)}>
          + Folder
        </Button>
        <Button variant="primary" onClick={() => handleNewAutomaton(null)}>
          + Automaton
        </Button>
      </div>
      {error && <p className={styles.error}>{error}</p>}
      <div className={styles.tree}>
        {roots.map((node) => (
          <FolderRow
            key={node.folder.id}
            node={node}
            depth={0}
            collapsed={collapsed}
            onToggleCollapsed={toggleCollapsed}
            selectedAutomatonId={selectedAutomatonId}
            onSelectAutomaton={(id) => navigate(`/automata/${id}`)}
            onContextMenu={openContextMenu}
          />
        ))}
        {rootAutomata.map((automaton) => (
          <AutomatonRow
            key={automaton.id}
            automaton={automaton}
            depth={0}
            selected={automaton.id === selectedAutomatonId}
            onSelect={() => navigate(`/automata/${automaton.id}`)}
            onContextMenu={openContextMenu}
          />
        ))}
      </div>

      {contextMenu && (
        <div
          className={styles.contextMenu}
          style={{ top: contextMenu.y, left: contextMenu.x }}
          onClick={(e) => e.stopPropagation()}
        >
          {!moveMenuOpen ? (
            <>
              <button type="button" onClick={handleContextRename}>
                Rename
              </button>
              <button type="button" onClick={() => setMoveMenuOpen(true)}>
                Move to…
              </button>
              <button
                type="button"
                className={styles.contextMenuDanger}
                onClick={handleContextDelete}
              >
                Delete
              </button>
            </>
          ) : (
            <>
              <button type="button" onClick={() => handleContextMoveTo(null)}>
                (root)
              </button>
              {moveTargets.map((entry) => (
                <button
                  key={entry.folder.id}
                  type="button"
                  onClick={() => handleContextMoveTo(entry.folder.id)}
                >
                  {"—".repeat(entry.depth)} {entry.folder.name}
                </button>
              ))}
            </>
          )}
        </div>
      )}
      {promptDialog}
      {confirmDialog}
      {newAutomatonDialog}
    </div>
  );
}

function CollapseChevron({ expanded }: { expanded: boolean }) {
  return (
    <svg
      className={[styles.chevron, expanded ? styles.chevronExpanded : ""].join(" ")}
      width="10"
      height="10"
      viewBox="0 0 10 10"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M3 1.5L7 5L3 8.5"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function FolderRow({
  node,
  depth,
  collapsed,
  onToggleCollapsed,
  selectedAutomatonId,
  onSelectAutomaton,
  onContextMenu,
}: {
  node: FolderNode;
  depth: number;
  collapsed: Set<UUID>;
  onToggleCollapsed: (id: UUID) => void;
  selectedAutomatonId: UUID | null;
  onSelectAutomaton: (id: UUID) => void;
  onContextMenu: (event: React.MouseEvent, kind: "folder" | "automaton", id: UUID) => void;
}) {
  const isCollapsed = collapsed.has(node.folder.id);

  return (
    <div>
      <div
        className={styles.folderRow}
        style={{ paddingLeft: depth * 16 }}
        onContextMenu={(e) => onContextMenu(e, "folder", node.folder.id)}
      >
        <button
          type="button"
          className={styles.collapseToggle}
          onClick={() => onToggleCollapsed(node.folder.id)}
          title={isCollapsed ? "Expand" : "Collapse"}
        >
          <CollapseChevron expanded={!isCollapsed} />
        </button>
        <span className={styles.folderName}>{node.folder.name}</span>
      </div>
      {!isCollapsed && (
        <>
          {node.children.map((child) => (
            <FolderRow
              key={child.folder.id}
              node={child}
              depth={depth + 1}
              collapsed={collapsed}
              onToggleCollapsed={onToggleCollapsed}
              selectedAutomatonId={selectedAutomatonId}
              onSelectAutomaton={onSelectAutomaton}
              onContextMenu={onContextMenu}
            />
          ))}
          {node.automata.map((automaton) => (
            <AutomatonRow
              key={automaton.id}
              automaton={automaton}
              depth={depth + 1}
              selected={automaton.id === selectedAutomatonId}
              onSelect={() => onSelectAutomaton(automaton.id)}
              onContextMenu={onContextMenu}
            />
          ))}
        </>
      )}
    </div>
  );
}

function AutomatonRow({
  automaton,
  depth,
  selected,
  onSelect,
  onContextMenu,
}: {
  automaton: AutomatonRead;
  depth: number;
  selected: boolean;
  onSelect: () => void;
  onContextMenu: (event: React.MouseEvent, kind: "folder" | "automaton", id: UUID) => void;
}) {
  return (
    <div className={styles.automatonRowWrapper} style={{ paddingLeft: depth * 16 }}>
      <button
        type="button"
        className={[styles.automatonRow, selected ? styles.selected : ""].join(" ")}
        onClick={onSelect}
        onContextMenu={(e) => onContextMenu(e, "automaton", automaton.id)}
      >
        {automaton.name}
      </button>
    </div>
  );
}
