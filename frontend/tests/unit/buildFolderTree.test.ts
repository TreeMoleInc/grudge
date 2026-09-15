import { describe, expect, it } from "vitest";
import { buildFolderTree } from "../../src/pages/Automata/buildFolderTree";
import type { AutomatonRead, FolderRead } from "../../src/api/types";

function folder(id: string, name: string, parentId: string | null = null): FolderRead {
  return {
    id,
    user_id: "u1",
    parent_id: parentId,
    name,
    sort_order: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function automaton(id: string, name: string, folderId: string | null = null): AutomatonRead {
  return {
    id,
    user_id: "u1",
    folder_id: folderId,
    name,
    sort_order: 0,
    active_version_id: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

describe("buildFolderTree", () => {
  it("puts folders with no parent (or an unknown parent) at the root", () => {
    const { roots } = buildFolderTree([folder("a", "A"), folder("b", "B")], []);
    expect(roots.map((n) => n.folder.id).sort()).toEqual(["a", "b"]);
  });

  it("nests a folder under its parent", () => {
    const { roots } = buildFolderTree([folder("a", "A"), folder("b", "B", "a")], []);
    expect(roots).toHaveLength(1);
    expect(roots[0].folder.id).toBe("a");
    expect(roots[0].children).toHaveLength(1);
    expect(roots[0].children[0].folder.id).toBe("b");
  });

  it("treats a folder whose parent_id doesn't match any known folder as a root", () => {
    // e.g. a stale/dangling parent_id - shouldn't crash or silently drop the folder
    const { roots } = buildFolderTree([folder("a", "A", "does-not-exist")], []);
    expect(roots.map((n) => n.folder.id)).toEqual(["a"]);
  });

  it("places an automaton under its folder", () => {
    const { roots, rootAutomata } = buildFolderTree(
      [folder("a", "A")],
      [automaton("bot1", "Bot1", "a")]
    );
    expect(rootAutomata).toHaveLength(0);
    expect(roots[0].automata.map((a) => a.id)).toEqual(["bot1"]);
  });

  it("places an automaton with no folder (or an unknown folder) at the root list", () => {
    const { rootAutomata } = buildFolderTree(
      [],
      [automaton("bot1", "Bot1", null), automaton("bot2", "Bot2", "missing-folder")]
    );
    expect(rootAutomata.map((a) => a.id).sort()).toEqual(["bot1", "bot2"]);
  });

  it("handles a multi-level tree with automata at each level", () => {
    const { roots } = buildFolderTree(
      [folder("a", "A"), folder("b", "B", "a"), folder("c", "C", "b")],
      [automaton("x", "X", "a"), automaton("y", "Y", "c")]
    );
    expect(roots[0].automata.map((a) => a.id)).toEqual(["x"]);
    const b = roots[0].children[0];
    const c = b.children[0];
    expect(c.automata.map((a) => a.id)).toEqual(["y"]);
  });
});
