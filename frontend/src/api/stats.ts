import { apiFetch } from "./client";
import type { LiveStatsRead } from "./types";

export async function getLiveStats(): Promise<LiveStatsRead> {
  return apiFetch<LiveStatsRead>("/stats/live");
}
