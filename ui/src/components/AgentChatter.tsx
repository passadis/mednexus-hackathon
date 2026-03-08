import { useRef, useEffect } from 'react';
import { Radio } from 'lucide-react';
import type { A2AMessage } from '../types';
import { AGENT_COLORS } from '../types';

interface AgentChatterProps {
  messages: A2AMessage[];
}

export function AgentChatter({ messages }: AgentChatterProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <aside className="flex w-80 flex-col border-l border-slate-200 bg-white">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-3">
        <Radio className="h-4 w-4 text-brand-500" />
        <h3 className="text-sm font-semibold text-slate-700">Agent Chatter</h3>
        <span className="ml-auto badge-blue">{messages.length}</span>
      </div>

      {/* Messages */}
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && (
          <p className="text-center text-xs text-slate-400 mt-8">
            Agent communication will appear here as the pipeline processes files.
          </p>
        )}

        {messages.map((msg) => {
          const senderStyle = AGENT_COLORS[msg.sender] || AGENT_COLORS.orchestrator;
          const isThinking = msg.type === 'status_update';

          return (
            <div
              key={msg.message_id}
              className={`rounded-xl border p-3 transition-all duration-300 ${
                isThinking ? 'border-brand-200 bg-brand-50/50 animate-thinking' : 'border-slate-100 bg-white'
              }`}
            >
              {/* Agent avatar row */}
              <div className="mb-1.5 flex items-center gap-2">
                <span
                  className={`flex h-6 w-6 items-center justify-center rounded-full text-xs ${senderStyle.bg}`}
                >
                  {senderStyle.icon}
                </span>
                <span className={`text-xs font-medium ${senderStyle.text}`}>
                  {formatAgentName(msg.sender)}
                </span>
                <span className="ml-auto text-[10px] text-slate-300">
                  {formatTime(msg.timestamp)}
                </span>
              </div>

              {/* Message content */}
              <p className="text-xs text-slate-600 leading-relaxed">
                <span className="font-medium text-slate-400">→ {formatAgentName(msg.receiver)}: </span>
                {formatPayload(msg)}
              </p>

              {/* Type badge */}
              <div className="mt-2">
                <span className={`badge ${typeBadgeClass(msg.type)}`}>{msg.type.replace('_', ' ')}</span>
              </div>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </aside>
  );
}

// ── Helpers ──────────────────────────────────────────────────

function formatAgentName(role: string): string {
  return role
    .split('_')
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(' ');
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return '';
  }
}

function formatPayload(msg: A2AMessage): string {
  const p = msg.payload;
  if (p.summary) return String(p.summary).slice(0, 150);
  if (p.instructions) return String(p.instructions).slice(0, 150);
  if (p.detail) return String(p.detail).slice(0, 150);
  return msg.type;
}

function typeBadgeClass(type: string): string {
  switch (type) {
    case 'task_assign':
      return 'badge-blue';
    case 'task_result':
      return 'badge-green';
    case 'error':
      return 'badge-red';
    case 'status_update':
      return 'badge-amber';
    default:
      return 'badge-purple';
  }
}
