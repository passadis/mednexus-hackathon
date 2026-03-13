import { useEffect, useRef, useState, useCallback } from 'react';
import type { A2AMessage } from '../types';

type WorkflowEventName =
  | 'specialist_started'
  | 'specialist_completed'
  | 'synthesis_started'
  | 'synthesis_completed';

interface WorkflowEventPayload {
  patient_id?: string;
  episode_id?: string;
  agent?: string;
  task_id?: string;
  summary?: string;
}

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

function toWorkflowMessage(eventName: WorkflowEventName, data: WorkflowEventPayload): A2AMessage {
  const timestamp = new Date().toISOString();
  const patientId = data.patient_id ?? '';
  const episodeId = data.episode_id ?? '';
  const agent = data.agent ?? 'diagnostic_synthesis';
  const taskId = data.task_id ?? '';

  const base = {
    message_id: `workflow:${eventName}:${patientId}:${episodeId}:${taskId || timestamp}`,
    patient_id: patientId,
    timestamp,
    correlation_id: taskId || `${eventName}:${episodeId}:${timestamp}`,
  };

  if (eventName === 'specialist_started') {
    return {
      ...base,
      type: 'task_assign',
      sender: 'orchestrator',
      receiver: agent,
      payload: {
        detail: `Started ${agent.replace(/_/g, ' ')} for ${episodeId || patientId}`,
        episode_id: episodeId,
        task_id: taskId,
      },
    };
  }

  if (eventName === 'specialist_completed') {
    return {
      ...base,
      type: 'task_result',
      sender: agent,
      receiver: 'orchestrator',
      payload: {
        summary: data.summary || `${agent.replace(/_/g, ' ')} completed`,
        episode_id: episodeId,
        task_id: taskId,
      },
    };
  }

  if (eventName === 'synthesis_started') {
    return {
      ...base,
      type: 'task_assign',
      sender: 'orchestrator',
      receiver: 'diagnostic_synthesis',
      payload: {
        detail: `Started synthesis for ${episodeId || patientId}`,
        episode_id: episodeId,
      },
    };
  }

  return {
    ...base,
    type: 'task_result',
    sender: 'diagnostic_synthesis',
    receiver: 'orchestrator',
    payload: {
      summary: data.summary || `Synthesis completed for ${episodeId || patientId}`,
      episode_id: episodeId,
    },
  };
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
          return;
        }

        if (
          (parsed.event === 'specialist_started' ||
            parsed.event === 'specialist_completed' ||
            parsed.event === 'synthesis_started' ||
            parsed.event === 'synthesis_completed') &&
          parsed.data
        ) {
          const synthetic = toWorkflowMessage(parsed.event as WorkflowEventName, parsed.data as WorkflowEventPayload);
          setMessages((prev) => dedup(prev, [synthetic]));
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
