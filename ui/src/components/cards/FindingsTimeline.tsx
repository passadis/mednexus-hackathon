import { Clock } from 'lucide-react';
import type { AgentActivity } from '../../types';
import { AGENT_COLORS } from '../../types';

interface FindingsTimelineProps {
  activities: AgentActivity[];
}

export function FindingsTimeline({ activities }: FindingsTimelineProps) {
  if (activities.length === 0) return null;

  return (
    <div className="card">
      <div className="mb-4 flex items-center gap-2">
        <Clock className="h-4 w-4 text-slate-400" />
        <h3 className="text-sm font-semibold text-slate-700">Activity Timeline</h3>
        <span className="ml-auto badge-blue">{activities.length} events</span>
      </div>

      <div className="relative space-y-4">
        {/* Vertical line */}
        <div className="absolute left-[15px] top-1 bottom-1 w-0.5 bg-slate-100" />

        {activities.map((act, i) => {
          const agentKey = act.agent.split('-')[0];
          const style = AGENT_COLORS[agentKey] || AGENT_COLORS.orchestrator;

          return (
            <div key={i} className="relative flex gap-3 pl-1">
              {/* Dot */}
              <div
                className={`relative z-10 mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs ${style.bg}`}
              >
                {style.icon}
              </div>

              {/* Content */}
              <div className="min-w-0 flex-1 pb-1">
                <div className="flex items-baseline gap-2">
                  <span className={`text-xs font-medium ${style.text}`}>
                    {formatAgentName(act.agent)}
                  </span>
                  <span className="text-[10px] text-slate-300">
                    {new Date(act.timestamp).toLocaleTimeString()}
                  </span>
                </div>
                <p className="text-xs text-slate-500">{act.action}</p>
                {act.detail && (
                  <p className="mt-0.5 text-xs text-slate-400">{act.detail}</p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function formatAgentName(agent: string): string {
  // agent_id format: "role-abc123" → display the role nicely
  const role = agent.split('-')[0];
  return role
    .split('_')
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(' ');
}
