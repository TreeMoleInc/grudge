import type { AutomatonRead, FolderRead, UUID } from "../../api/types";

export interface FolderNode {
  folder: FolderRead;
  children: FolderNode[];
  automata: AutomatonRead[];
}

/**
 * Builds a tree client-side from the backend's flat folder list (GET
 * /folders returns a flat list by design - see backend/src/grudge_backend/
 * routers/folders.py's own comment: avoids a recursive CTE server-side and
 * doesn't force a response shape on the UI). O(n), pure function so it's
 * unit-testable without a DOM or network.
 */
export function buildFolderTree(
  folders: FolderRead[],
  automata: AutomatonRead[]
): { roots: FolderNode[]; rootAutomata: AutomatonRead[] } {
  const nodeById = new Map<UUID, FolderNode>(
    folders.map((folder) => [folder.id, { folder, children: [], automata: [] }])
  );

  const roots: FolderNode[] = [];
  for (const node of nodeById.values()) {
    const parentId = node.folder.parent_id;
    if (parentId && nodeById.has(parentId)) {
      nodeById.get(parentId)!.children.push(node);
    } else {
      roots.push(node);
    }
  }

  const rootAutomata: AutomatonRead[] = [];
  for (const automaton of automata) {
    if (automaton.folder_id && nodeById.has(automaton.folder_id)) {
      nodeById.get(automaton.folder_id)!.automata.push(automaton);
    } else {
      rootAutomata.push(automaton);
    }
  }

  return { roots, rootAutomata };
}
