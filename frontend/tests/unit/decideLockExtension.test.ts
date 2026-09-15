import { describe, expect, it } from "vitest";
import { EditorState } from "@codemirror/state";
import type { TransactionSpec } from "@codemirror/state";
import { lockSignatureLine } from "../../src/pages/Automata/decideLockExtension";

const INITIAL = "_betrayed = False\n\ndef decide(history):\n    return COOPERATE\n";

function makeState(doc: string = INITIAL): EditorState {
  return EditorState.create({ doc, extensions: [lockSignatureLine()] });
}

function apply(state: EditorState, spec: TransactionSpec): EditorState {
  const tr = state.update(spec);
  return tr.state;
}

describe("lockSignatureLine", () => {
  it("blocks typing in the middle of the signature line", () => {
    let state = makeState();
    const defLineFrom = state.doc.toString().indexOf("def decide");
    // Position the cursor right after "def decide(history" (before the colon).
    const pos = defLineFrom + "def decide(history".length;
    state = apply(state, { changes: { from: pos, insert: "X" } });
    expect(state.doc.toString()).toBe(INITIAL);
  });

  it("blocks appending text right at the end of the signature line without a newline", () => {
    // Regression test: typing immediately after the colon (no Enter) used to
    // slip through because insertion exactly at the line's end was allowed
    // unconditionally.
    let state = makeState();
    const lineEnd =
      state.doc.toString().indexOf("def decide(history):") + "def decide(history):".length;
    state = apply(state, { changes: { from: lineEnd, insert: "XXXX" } });
    expect(state.doc.toString()).toBe(INITIAL);
  });

  it("allows pressing Enter at the end of the signature line to start a new line", () => {
    let state = makeState();
    const lineEnd =
      state.doc.toString().indexOf("def decide(history):") + "def decide(history):".length;
    state = apply(state, { changes: { from: lineEnd, insert: "\n    pass" } });
    expect(state.doc.toString()).toContain("def decide(history):\n    pass\n    return COOPERATE");
  });

  it("allows inserting a new line above the signature line", () => {
    let state = makeState();
    const lineStart = state.doc.toString().indexOf("def decide(history):");
    state = apply(state, { changes: { from: lineStart, insert: "# a comment\n" } });
    expect(state.doc.toString()).toContain("# a comment\ndef decide(history):");
  });

  it("blocks deleting part of the signature line", () => {
    let state = makeState();
    const lineStart = state.doc.toString().indexOf("def decide(history):");
    state = apply(state, { changes: { from: lineStart, to: lineStart + 3, insert: "" } });
    expect(state.doc.toString()).toBe(INITIAL);
  });

  it("leaves edits to other lines (including top-level setup code) untouched", () => {
    let state = makeState();
    const pos = state.doc.toString().indexOf("_betrayed = False") + "_betrayed = False".length;
    state = apply(state, { changes: { from: pos, insert: "  # a flag" } });
    expect(state.doc.toString()).toContain("_betrayed = False  # a flag");
  });
});
