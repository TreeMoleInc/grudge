import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import { oneDark } from "@codemirror/theme-one-dark";

interface CodeSnapshotViewerProps {
  code: string;
}

// Read-only viewer for a tournament entrant's frozen code_snapshot (Results
// page) - deliberately NOT a link into the automaton's live Automata page.
// Reuses the same CodeMirror setup as the real editor so syntax highlighting
// looks identical, but `editable={false}` here since nothing should be
// mutable about a past tournament's record.
export function CodeSnapshotViewer({ code }: CodeSnapshotViewerProps) {
  return (
    <CodeMirror
      value={code}
      theme={oneDark}
      extensions={[python()]}
      editable={false}
      basicSetup={{ lineNumbers: true, foldGutter: false }}
    />
  );
}
