import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getAutomaton, setActiveVersion } from "../../api/automata";
import { createVersion, deleteVersion, listVersions } from "../../api/versions";
import { ApiError } from "../../api/client";
import type { UUID } from "../../api/types";
import { Button } from "../../components/Button";
import { usePromptDialog } from "../../components/PromptDialog";
import { useConfirmDialog } from "../../components/ConfirmDialog";
import { CodeEditorArea } from "./CodeEditorArea";
import styles from "./Editor.module.css";

interface EditorProps {
  automatonId: UUID;
}

export function Editor({ automatonId }: EditorProps) {
  const queryClient = useQueryClient();
  const [manuallySelectedVersionId, setManuallySelectedVersionId] = useState<UUID | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { dialog: promptDialog, prompt } = usePromptDialog();
  const { dialog: confirmDialog, confirm } = useConfirmDialog();

  const automatonQuery = useQuery({
    queryKey: ["automaton", automatonId],
    queryFn: () => getAutomaton(automatonId),
  });
  const versionsQuery = useQuery({
    queryKey: ["versions", automatonId],
    queryFn: () => listVersions(automatonId),
  });

  // Derived directly during render (no effect needed): defaults to the
  // automaton's active version until the user picks a different one.
  const selectedVersionId =
    manuallySelectedVersionId ?? automatonQuery.data?.active_version_id ?? null;

  async function handleNewVersion() {
    const name = await prompt("Name for the new version? (leave blank for a default name)");
    if (name === null) return;
    const created = await createVersion(automatonId, { name: name || undefined });
    await queryClient.invalidateQueries({ queryKey: ["versions", automatonId] });
    setManuallySelectedVersionId(created.id);
  }

  async function handleSetActive() {
    if (!selectedVersionId) return;
    await setActiveVersion(automatonId, selectedVersionId);
    await queryClient.invalidateQueries({ queryKey: ["automaton", automatonId] });
  }

  async function handleDeleteVersion() {
    if (!selectedVersionId) return;
    const version = (versionsQuery.data ?? []).find((v) => v.id === selectedVersionId);
    if (!version) return;
    if (
      !(await confirm(`Delete version "${version.name}"? This can't be undone.`, { danger: true }))
    ) {
      return;
    }
    setError(null);
    try {
      await deleteVersion(automatonId, selectedVersionId);
      setManuallySelectedVersionId(null);
      await queryClient.invalidateQueries({ queryKey: ["versions", automatonId] });
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Could not delete version.");
    }
  }

  if (automatonQuery.isLoading || versionsQuery.isLoading) {
    return <p className={styles.hint}>Loading…</p>;
  }
  if (!automatonQuery.data) {
    return <p className={styles.hint}>Automaton not found.</p>;
  }

  const isActiveVersion = selectedVersionId === automatonQuery.data.active_version_id;
  const isOnlyVersion = (versionsQuery.data ?? []).length <= 1;

  return (
    <div className={styles.editor}>
      <div className={styles.toolbar}>
        <h2 className={styles.title}>{automatonQuery.data.name}</h2>
        <select
          className={styles.versionSelect}
          value={selectedVersionId ?? ""}
          onChange={(event) => setManuallySelectedVersionId(event.target.value)}
        >
          {(versionsQuery.data ?? []).map((version) => (
            <option key={version.id} value={version.id}>
              {version.name}
              {version.id === automatonQuery.data.active_version_id ? " (active)" : ""}
            </option>
          ))}
        </select>
        <Button variant="secondary" onClick={handleNewVersion}>
          New version
        </Button>
        <Button variant="primary" onClick={handleSetActive} disabled={isActiveVersion}>
          {isActiveVersion ? "Active" : "Set active"}
        </Button>
        <Button
          variant="danger"
          onClick={handleDeleteVersion}
          disabled={isActiveVersion || isOnlyVersion}
          title={
            isActiveVersion
              ? "Set a different version active first"
              : isOnlyVersion
                ? "An automaton needs at least one version"
                : undefined
          }
        >
          Delete version
        </Button>
      </div>
      {error && <p className={styles.error}>{error}</p>}
      <div className={styles.codeArea}>
        {selectedVersionId && (
          // Keyed by version id: switching versions mounts a fresh
          // CodeEditorArea with its own local `code` state seeded from that
          // version's content, rather than syncing state via an effect.
          <CodeEditorArea
            key={selectedVersionId}
            automatonId={automatonId}
            versionId={selectedVersionId}
          />
        )}
      </div>
      {promptDialog}
      {confirmDialog}
    </div>
  );
}
