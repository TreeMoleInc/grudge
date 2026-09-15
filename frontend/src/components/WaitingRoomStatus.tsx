import styles from "./WaitingRoomStatus.module.css";

type WaitingRoomStatusProps =
  | { kind: "count"; memberCount: number; capacity: number }
  | { kind: "entries"; entries: { id: string; automatonId: string }[] };

// Two variants of one "who's in the room" primitive: ranked/unranked queues
// only expose a count (individual identities aren't shared pre-match), sim
// rooms show the actual entrant list (CLAUDE.md's invite-code-based, already
// social design). Kept as one component so both read as the same visual
// pattern rather than diverging.
export function WaitingRoomStatus(props: WaitingRoomStatusProps) {
  if (props.kind === "count") {
    return (
      <div className={styles.status}>
        <span className={styles.count}>
          {props.memberCount}/{props.capacity}
        </span>{" "}
        waiting…
      </div>
    );
  }

  return (
    <ul className={styles.entryList}>
      {props.entries.map((entry) => (
        <li key={entry.id}>{entry.automatonId}</li>
      ))}
      {props.entries.length === 0 && <li className={styles.empty}>No one has joined yet</li>}
    </ul>
  );
}
