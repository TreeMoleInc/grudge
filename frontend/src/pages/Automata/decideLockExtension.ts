import { EditorState } from "@codemirror/state";
import { indentUnit } from "@codemirror/language";
import type { Extension, Text } from "@codemirror/state";

// Every automaton's entry point is `def decide(history):` (CLAUDE.md S2) - the
// signature line itself is locked so a player can't rename/break it, while
// everything else (including top-level setup code, e.g. Grudger's `_betrayed`
// flag) stays freely editable, per the product's persistent-process model.
const SIGNATURE_LINE = "def decide(history):";

function findSignatureLine(doc: Text): { from: number; to: number } | null {
  for (let n = 1; n <= doc.lines; n++) {
    const line = doc.line(n);
    if (line.text.trim() === SIGNATURE_LINE) {
      return { from: line.from, to: line.to };
    }
  }
  return null;
}

function editTouchesLine(
  fromA: number,
  toA: number,
  insertedText: string,
  line: { from: number; to: number }
): boolean {
  if (fromA === toA) {
    if (fromA > line.from && fromA < line.to) {
      // Strictly inside the line's own text - always corrupts it.
      return true;
    }
    if (fromA === line.to) {
      // At the line's end, right before its terminating newline. Safe only
      // if the insertion starts with a newline (e.g. Enter, or CodeMirror's
      // indent-on-enter inserting "\n    ") - anything else appends onto the
      // signature line itself, e.g. typing right after the colon.
      return !insertedText.startsWith("\n");
    }
    if (fromA === line.from) {
      // At the line's start. Safe only if the insertion ends with a newline
      // (adds a line above without touching this line's own first character).
      return !insertedText.endsWith("\n");
    }
    return false;
  }
  return fromA < line.to && toA > line.from;
}

export function lockSignatureLine(): Extension {
  return EditorState.transactionFilter.of((tr) => {
    if (!tr.docChanged) return tr;
    const line = findSignatureLine(tr.startState.doc);
    if (!line) return tr;

    let blocked = false;
    tr.changes.iterChangedRanges((fromA, toA, fromB, toB) => {
      const insertedText = tr.newDoc.sliceString(fromB, toB);
      if (editTouchesLine(fromA, toA, insertedText, line)) blocked = true;
    });
    return blocked ? [] : tr;
  });
}

// A consistent 4-space indent unit - CodeMirror's default indentUnit facet
// otherwise leaves auto-indent (e.g. after a colon) inconsistent, which
// showed up as a "half tab" (two spaces) in some contexts.
export function consistentIndent(): Extension {
  return indentUnit.of("    ");
}
