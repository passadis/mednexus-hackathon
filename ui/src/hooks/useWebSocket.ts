import { useEffect, useRef, useState, useCallback } from 'react';
import type { A2AMessage } from '../types';

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
 */
export function useWebSocket() {
  const [messages, setMessages] = useState<A2AMessage[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

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
  }, []);

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
    };
  }, [connect]);

  return { messages, connected };
}
