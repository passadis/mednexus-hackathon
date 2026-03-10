import type { Episode } from '../types';

/**
 * Horizontal visual pipeline stepper – shows which agents have run / are
 * running / are pending for a given episode.  Driven entirely by the
 * episode.status enum and episode.activity_log already flowing over WS.
 */

// ── Step definitions ────────────────────────────────────────

type StepState = 'completed' | 'active' | 'pending';

interface Step {
  key: string;
  label: string;
  icon: string;         // emoji for the dot
  detail?: string;      // extra context shown below the label
}

const PIPELINE: Step[] = [
  { key: 'intake',     label: 'Intake',     icon: '📥' },
  { key: 'specialist', label: 'Specialist',  icon: '🔬' },
  { key: 'crosscheck', label: 'Cross-Check', icon: '🔗' },
  { key: 'synthesis',  label: 'Synthesis',   icon: '🧬' },
];

// Map episode.status → which pipeline step is *active*
const STATUS_TO_ACTIVE_STEP: Record<string, number> = {
  intake:                   0,
  waiting_for_radiology:    1,
  waiting_for_history:      1,
  waiting_for_transcript:   1,
  cross_modality_check:     2,
  synthesis_complete:       4,   // beyond last index → all done
  review_required:          4,
  approved:                 4,
  finalized:                4,
};

// Friendly sub-labels for "Specialist" step based on what dispatched
function specialistDetail(activity: Episode['activity_log']): string | undefined {
  const dispatches = activity.filter((a) => a.action === 'dispatch');
  if (dispatches.length === 0) return undefined;
  const agents = new Set(dispatches.map((d) => {
    if (d.detail.toLowerCase().includes('vision')) return 'Vision';
    if (d.detail.toLowerCase().includes('historian')) return 'Historian';
    if (d.detail.toLowerCase().includes('transcript')) return 'Transcript';
    return d.agent.split('-')[0];
  }));
  return [...agents].join(' + ');
}

function resolveStates(episode: Episode): { step: Step; state: StepState }[] {
  const activeIdx = STATUS_TO_ACTIVE_STEP[episode.status] ?? 0;
  const detail = specialistDetail(episode.activity_log);

  return PIPELINE.map((step, i) => {
    let state: StepState = 'pending';
    if (i < activeIdx) state = 'completed';
    else if (i === activeIdx) state = 'active';

    const enriched = { ...step };
    if (step.key === 'specialist' && detail) enriched.detail = detail;
    return { step: enriched, state };
  });
}

// ── Component ───────────────────────────────────────────────

export function AgentStepper({ episode }: { episode: Episode }) {
  const steps = resolveStates(episode);

  return (
    <div className="flex items-start justify-between gap-1 px-2 py-3">
      {steps.map(({ step, state }, i) => (
        <div key={step.key} className="flex flex-1 items-start">
          {/* Dot + label column */}
          <div className="flex flex-col items-center gap-1 min-w-[60px]">
            {/* Circle */}
            <div
              className={`relative flex h-9 w-9 items-center justify-center rounded-full text-sm
                ${state === 'completed'
                  ? 'bg-emerald-500 text-white shadow-md shadow-emerald-200'
                  : state === 'active'
                    ? 'bg-brand-500 text-white shadow-md shadow-brand-200'
                    : 'bg-slate-100 text-slate-400 border border-slate-200'
                }`}
            >
              {state === 'completed' ? '✓' : step.icon}
              {state === 'active' && (
                <span className="absolute inset-0 rounded-full animate-ping bg-brand-400 opacity-30" />
              )}
            </div>
            {/* Label */}
            <span
              className={`text-[10px] font-semibold leading-tight text-center
                ${state === 'completed'
                  ? 'text-emerald-600'
                  : state === 'active'
                    ? 'text-brand-600'
                    : 'text-slate-400'
                }`}
            >
              {step.label}
            </span>
            {/* Sub-detail */}
            {step.detail && (
              <span className="text-[9px] text-slate-400 leading-tight text-center">
                {step.detail}
              </span>
            )}
          </div>

          {/* Connector line (between dots – not after the last one) */}
          {i < steps.length - 1 && (
            <div className="flex-1 mt-[18px] mx-1">
              <div
                className={`h-[2px] w-full rounded-full transition-colors duration-500
                  ${i < (STATUS_TO_ACTIVE_STEP[episode.status] ?? 0)
                    ? 'bg-emerald-400'
                    : 'bg-slate-200'
                  }`}
              />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
