import { useQuery } from "@tanstack/react-query";
import { getLiveStats } from "../api/stats";
import styles from "./LiveActivity.module.css";

// Approximate, not a realtime feed (see backend/services/stats.py) - polling
// every 20s is plenty for a number that's already only accurate to within
// ONLINE_WINDOW_SECONDS server-side.
const POLL_INTERVAL_MS = 20_000;

export function LiveActivity() {
  const { data } = useQuery({
    queryKey: ["live-stats"],
    queryFn: getLiveStats,
    refetchInterval: POLL_INTERVAL_MS,
    refetchIntervalInBackground: true,
  });

  if (!data) return null;

  return (
    <div className={styles.activity}>
      <span className={styles.stat}>
        <strong>{data.online_count}</strong> online
      </span>
      <span className={styles.divider}>·</span>
      <span className={styles.stat}>
        <strong>{data.in_activity_count}</strong> in a match or queue
      </span>
    </div>
  );
}
