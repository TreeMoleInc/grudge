import styles from "./VoidedFlaggedBanner.module.css";

interface VoidedFlaggedBannerProps {
  scope: "tournament" | "automaton";
  message?: string;
}

// One component for both the tournament-wide infrastructure-fault banner
// (Processing screen's `error` event) and the per-automaton "flagged
// privately" banner (Processing's `automaton_flagged` event, and a faulted
// entry's marker on the Results page) - kept as one place so the wording
// never drifts between the two call sites. Copy is deliberately explicit
// that this is NOT "your bot crashed" for the tournament scope (CLAUDE.md §3).
export function VoidedFlaggedBanner({ scope, message }: VoidedFlaggedBannerProps) {
  const heading =
    scope === "tournament"
      ? "Tournament voided"
      : "Your automaton was removed from this tournament";
  const defaultMessage =
    scope === "tournament"
      ? "This tournament failed due to an infrastructure fault and was fully voided - no rating changes were made to anyone."
      : "This was voided for you specifically due to a timeout or error in your code. No rating change occurred, and this won't appear in your normal match history.";

  return (
    <div className={styles.banner} role="alert">
      <strong className={styles.heading}>{heading}</strong>
      <p className={styles.message}>{message ?? defaultMessage}</p>
    </div>
  );
}
