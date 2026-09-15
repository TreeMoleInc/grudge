import { useState } from "react";
import { useParams } from "react-router-dom";
import { AppHeader } from "../../components/AppHeader";
import { Tabs } from "../../components/Tabs";
import { Sidebar } from "./Sidebar";
import { Editor } from "./Editor";
import { Stats } from "./Stats";
import styles from "./AutomataPage.module.css";

type PanelId = "sidebar" | "editor" | "stats";

// Three-pane layout (sidebar/editor/stats). Mobile pattern per CLAUDE.md §5,
// built now even though general mobile polish is Phase 7: one shared
// activePanel state, all three panels stay mounted at every viewport size,
// and a CSS media query (see AutomataPage.module.css) hides the two
// non-active panels and reveals the tab-switcher bar only below the
// breakpoint - not a separate mobile component tree.
export function AutomataPage() {
  const { automatonId } = useParams<{ automatonId?: string }>();
  const [activePanel, setActivePanel] = useState<PanelId>("editor");

  return (
    <div className={styles.page}>
      <AppHeader />
      <Tabs
        className={styles.mobileTabs}
        tabs={[
          { id: "sidebar", label: "Automata" },
          { id: "editor", label: "Editor" },
          { id: "stats", label: "Stats" },
        ]}
        active={activePanel}
        onChange={setActivePanel}
      />
      <div className={styles.panes} data-active-panel={activePanel}>
        <div className={styles.sidebarPane} data-panel="sidebar">
          <Sidebar selectedAutomatonId={automatonId ?? null} />
        </div>
        <div className={styles.editorPane} data-panel="editor">
          {automatonId ? (
            // Keyed by automatonId: switching automata must remount Editor,
            // not just update its prop - otherwise its manuallySelectedVersionId
            // state (set by the version dropdown) survives the switch and can
            // point at a version belonging to the PREVIOUS automaton, which
            // 404s against the new one (see CodeEditorArea's isError handling).
            <Editor key={automatonId} automatonId={automatonId} />
          ) : (
            <p className={styles.emptyState}>Select or create an automaton to start editing.</p>
          )}
        </div>
        <div className={styles.statsPane} data-panel="stats">
          {automatonId && <Stats automatonId={automatonId} />}
        </div>
      </div>
    </div>
  );
}
