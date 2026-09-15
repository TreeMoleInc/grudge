import { describe, expect, it } from "vitest";
import {
  initialProcessingState,
  reduceProcessingMessage,
} from "../../src/pages/Processing/processingReducer";

describe("reduceProcessingMessage", () => {
  it("stores progress from a progress message", () => {
    const next = reduceProcessingMessage(initialProcessingState, {
      type: "progress",
      data: { completed_matches: 3, total_matches: 6, pct: 50.0 },
    });
    expect(next.progress).toEqual({ completed: 3, total: 6, pct: 50.0 });
  });

  it("sets redirectTo from a completed message, without touching other fields", () => {
    const withProgress = reduceProcessingMessage(initialProcessingState, {
      type: "progress",
      data: { completed_matches: 6, total_matches: 6, pct: 100 },
    });
    const next = reduceProcessingMessage(withProgress, {
      type: "completed",
      data: { redirect_url: "/results/abc" },
    });
    expect(next.redirectTo).toBe("/results/abc");
    expect(next.progress).toEqual(withProgress.progress); // untouched
  });

  it("stores the raw message text from an error message - infrastructure-fault copy lives in the component, not here", () => {
    const next = reduceProcessingMessage(initialProcessingState, {
      type: "error",
      data: { reason: "watchdog_stall", message: "Tournament failed and was fully voided." },
    });
    expect(next.tournamentError).toBe("Tournament failed and was fully voided.");
  });

  it("formats a flagged message including the reason", () => {
    const next = reduceProcessingMessage(initialProcessingState, {
      type: "automaton_flagged",
      data: { automaton_id: "auto-1", reason: "timeout on round 12" },
    });
    expect(next.flaggedMessage).toBe("Automaton removed: timeout on round 12");
  });

  it("progress and flagged/error states are independent - a flag doesn't clear progress", () => {
    const withProgress = reduceProcessingMessage(initialProcessingState, {
      type: "progress",
      data: { completed_matches: 2, total_matches: 6, pct: 33.3 },
    });
    const next = reduceProcessingMessage(withProgress, {
      type: "automaton_flagged",
      data: { automaton_id: "auto-1", reason: "crashed" },
    });
    expect(next.progress).toEqual(withProgress.progress);
    expect(next.flaggedMessage).toBe("Automaton removed: crashed");
  });
});
