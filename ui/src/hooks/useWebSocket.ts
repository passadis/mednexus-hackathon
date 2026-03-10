import { useEffect, useRef, useState, useCallback } from 'react';
import type { A2AMessage } from '../types';

/** Tiny debounce helper — collapses rapid-fire calls into one. */
function useDebouncedCallback(fn: () => void, delay: number) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  return useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => fnRef.current(), delay);
  }, [delay]);
}

/** Merge new messages into existing list, deduplicating by message_id. */
function dedup(prev: A2AMessage[], incoming: A2AMessage[]): A2AMessage[] {
  const seen = new Set(prev.map((m) => m.message_id));
  const merged = [...prev];
  for (const msg of incoming) {
    if (!seen.has(msg.message_id)) {
      seen.add(msg.message_id);
      merged.push(msg);
    }
  }
  // Keep last 200
  return merged.slice(-200);
}

/**
 * WebSocket hook that connects to the Agent Chatter stream.
 * Automatically reconnects on disconnect.
 * Calls onContextChange when agent activity suggests the context has changed.
 */
export function useWebSocket(onContextChange?: () => void) {
  const [messages, setMessages] = useState<A2AMessage[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const trailTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Keep onContextChange in a ref so the trailing-fetch callback is stable
  // (same pattern as useDebouncedCallback above).
  const onChangeRef = useRef(onContextChange);
  onChangeRef.current = onContextChange;

  // Debounced refresh — collapses rapid-fire agent events into one API call
  const debouncedRefresh = useDebouncedCallback(() => {
    onContextChange?.();
  }, 300);

  // Schedule a trailing safety fetch that fires ~2.5 s after the last
  // context_updated event.  This catches updates that the debounce window
  // collapsed (e.g. specialist #2 finishes right after specialist #1).
  const scheduleTrailingFetch = useCallback(() => {
    if (trailTimer.current) clearTimeout(trailTimer.current);
    trailTimer.current = setTimeout(() => {
      onChangeRef.current?.();
    }, 2500);
  }, []);  // stable — uses ref, no deps

  const connect = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/chatter`);

    ws.onopen = () => {
      setConnected(true);
      console.log('[MedNexus] Agent Chatter connected');
    };

    ws.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);

        // ── Authoritative refresh: fired AFTER orchestrator saves to Cosmos
        if (parsed.event === 'context_updated') {
          debouncedRefresh();
          scheduleTrailingFetch();
          return;
        }

        if (parsed.event === 'a2a_message' && parsed.data) {
          const msg = parsed.data as A2AMessage;
          setMessages((prev) => dedup(prev, [msg]));
        }
      } catch {
        // ignore non-JSON messages
      }
    };

    ws.onclose = () => {
      setConnected(false);
      // Reconnect after 3 seconds
      reconnectTimer.current = setTimeout(connect, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };

    wsRef.current = ws;
  }, [debouncedRefresh, scheduleTrailingFetch]);

  useEffect(() => {
    connect();

    // Also fetch history on mount
    fetch('/api/chatter/history?limit=50')
      .then((r) => r.json())
      .then((data: A2AMessage[]) => {
        if (Array.isArray(data)) {
          setMessages((prev) => dedup(prev, data));
        }
      })
      .catch(() => {});

    return () => {
      wsRef.current?.close();
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (trailTimer.current) clearTimeout(trailTimer.current);
    };
  }, [connect]);

  return { messages, connected };
}
