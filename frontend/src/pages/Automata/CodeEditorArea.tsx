import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import { oneDark } from "@codemirror/theme-one-dark";
import { getVersion, updateVersion } from "../../api/versions";
import type { UUID } from "../../api/types";
import { useDebouncedCallback } from "./useDebouncedCallback";
import { lockSignatureLine, consistentIndent } from "./decideLockExtension";
import styles from "./Editor.module.css";

const AUTOSAVE_DELAY_MS = 800;

interface CodeEditorAreaProps {
  automatonId: UUID;
  versionId: UUID;
}

/** Fetches the version's code, then hands off to CodeEditorInner once loaded.
 * The parent (Editor.tsx) keys this whole component by versionId, so
 * switching versions mounts a fresh instance rather than needing an effect
 * to resync local state.
 */
export function CodeEditorArea({ automatonId, versionId }: CodeEditorAreaProps) {
  const versionQuery = useQuery({
    queryKey: ["version", automatonId, versionId],
    queryFn: () => getVersion(automatonId, versionId),
  });

  if (versionQuery.isLoading) {
    return <p className={styles.hint}>Loading…</p>;
  }
  // A settled query with no data means it errored (e.g. a version id that
  // doesn't belong to this automaton) - show that instead of silently
  // rendering "Loading…" forever, which gave no indication anything was
  // wrong or how to recover.
  if (versionQuery.isError || !versionQuery.data) {
    return <p className={styles.hint}>Couldn't load this version.</p>;
  }

  return (
    <CodeEditorInner
      automatonId={automatonId}
      versionId={versionId}
      initialCode={versionQuery.data.code}
    />
  );
}

function CodeEditorInner({
  automatonId,
  versionId,
  initialCode,
}: CodeEditorAreaProps & { initialCode: string }) {
  const queryClient = useQueryClient();
  // Safe here specifically because this component is freshly mounted (via
  // the parent's `key={versionId}`) whenever the version changes - this is
  // the initial value for THIS mount only, not synced on every render.
  const [code, setCode] = useState(initialCode);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");
  // Two autosave requests can be in flight together (a fast edit right after
  // a slow one) with no guarantee the earlier one's response arrives first -
  // without this, a stale response landing last could overwrite the cache
  // with older code than what the player actually has on screen/persisted.
  const latestRequestRef = useRef(0);

  const autosave = useDebouncedCallback(async (nextCode: string) => {
    const requestId = ++latestRequestRef.current;
    setSaveState("saving");
    const updated = await updateVersion(automatonId, versionId, { code: nextCode });
    if (latestRequestRef.current !== requestId) return; // superseded by a newer autosave
    setSaveState("saved");
    // Write the fresh code straight into the cache for THIS version (the one
    // CodeEditorArea's own query reads) rather than only invalidating the
    // version LIST query ("versions", plural - a different, unrelated cache
    // entry that doesn't hold code at all). Without this, switching to
    // another automaton and back showed stale pre-edit code until the
    // global 10s staleTime happened to have elapsed by the time you
    // returned - a real bug, not a timing coincidence to work around.
    queryClient.setQueryData(["version", automatonId, versionId], updated);
    // The version list's `updated_at` (shown in the version picker) still
    // needs a real invalidation, since setQueryData above doesn't touch it.
    await queryClient.invalidateQueries({ queryKey: ["versions", automatonId] });
  }, AUTOSAVE_DELAY_MS);

  function handleChange(nextCode: string) {
    setCode(nextCode);
    setSaveState("idle");
    autosave(nextCode);
  }

  return (
    <div className={styles.codeAreaInner}>
      <div className={styles.codeMirrorWrap}>
        <CodeMirror
          value={code}
          theme={oneDark}
          extensions={[python(), consistentIndent(), lockSignatureLine()]}
          onChange={handleChange}
          height="100%"
        />
      </div>
      <span className={styles.saveIndicator}>
        {saveState === "saving" ? "Saving…" : saveState === "saved" ? "Saved" : ""}
      </span>
    </div>
  );
}
