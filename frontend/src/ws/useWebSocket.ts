import { useCallback, useEffect, useRef } from "react";
import { API_BASE_URL } from "../api/client";

const RECONNECT_DELAY_MS = 2000;
const MAX_RECONNECT_ATTEMPTS = 5;

export function wsUrl(path: string): string {
  const httpUrl = new URL(path, API_BASE_URL);
  httpUrl.protocol = httpUrl.protocol === "https:" ? "wss:" : "ws:";
  return httpUrl.toString();
}

/**
 * Connects to `path` (or does nothing if `path` is null - e.g. waiting on an
 * id from a prior HTTP call). Cookies are attached automatically by the
 * browser on same-site WS handshakes (see the Phase 4 plan's CORS/cookie
 * note) - no auth wiring needed here. Reconnects with a short fixed delay up
 * to a small cap; a page that needs the connection is expected to be
 * short-lived (a queue wait, a processing screen), not something that should
 * retry forever in the background.
 */
export function useWebSocket<TMessage>(
  path: string | null,
  onMessage: (message: TMessage) => void
): { send: (message: unknown) => void } {
  const onMessageRef = useRef(onMessage);
  // Ref mutations belong in an effect, not during render - see the identical
  // note in useDebouncedCallback.ts.
  useEffect(() => {
    onMessageRef.current = onMessage;
  });
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!path) return;
    let attempts = 0;
    let cancelled = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;

    function connect() {
      const socket = new WebSocket(wsUrl(path as string));
      socketRef.current = socket;

      socket.onmessage = (event) => {
        try {
          onMessageRef.current(JSON.parse(event.data) as TMessage);
        } catch {
          // malformed frame - ignore rather than crash the page
        }
      };

      socket.onclose = () => {
        if (cancelled || attempts >= MAX_RECONNECT_ATTEMPTS) return;
        attempts += 1;
        reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
      };
    }

    connect();

    return () => {
      cancelled = true;
      clearTimeout(reconnectTimer);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [path]);

  // Stable across renders (empty deps - socketRef is a ref, not a reactive
  // value) on purpose: a fresh function identity here previously propagated
  // through every caller's own useCallback (e.g. useMatchmakingSocket's
  // sendHeartbeat), which in RandomTab.tsx retriggers the heartbeat
  // useEffect on every WS broadcast - tearing down and recreating the
  // setInterval before it ever fires if broadcasts arrive faster than the
  // heartbeat period, silently dropping the player from the queue after the
  // backend's 30s stale-heartbeat sweep. See CLAUDE.md's matchmaking
  // heartbeat design (S2) for why that sweep exists.
  const send = useCallback((message: unknown) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(message));
    }
  }, []);

  return { send };
}
