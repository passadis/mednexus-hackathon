import { useState } from 'react';
import { ChevronDown, ChevronUp, Calendar, FileText, Layers, Share2, Trash2, Download } from 'lucide-react';
import type { Episode } from '../../types';
import { XrayCard } from './XrayCard';
import { TranscriptCard } from './TranscriptCard';
import { SynthesisCard } from './SynthesisCard';
import { StatusBadge } from '../StatusBadge';
import { ShareModal } from '../ShareModal';
import { AgentStepper } from '../AgentStepper';

interface EpisodeCardProps {
  episode: Episode;
  patientId: string;
  isActive: boolean;
  defaultOpen?: boolean;
  onActivate: () => void;
  onDelete?: () => void;
}

export function EpisodeCard({
  episode,
  patientId,
  isActive,
  defaultOpen = false,
  onActivate,
  onDelete,
}: EpisodeCardProps) {
  const [open, setOpen] = useState(defaultOpen);
  const [showShare, setShowShare] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const xrayFindings = episode.findings.filter((f) => f.modality === 'radiology_image');
  const textFindings = episode.findings.filter(
    (f) => f.modality === 'clinical_text' || f.modality === 'audio_transcript',
  );
  const date = new Date(episode.created_at).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

  return (
    <div
      className={`rounded-2xl border-2 transition-all duration-200 ${
        isActive
          ? 'border-brand-500/40 shadow-lg shadow-brand-500/10'
          : 'border-white/[0.06] shadow-sm hover:border-white/10'
      }`}
    >
      {/* Header — always visible */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-3 rounded-t-2xl px-5 py-4 text-left transition hover:bg-white/[0.03]"
      >
        <div
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${
            isActive ? 'bg-brand-500/20' : 'bg-white/5'
          }`}
        >
          <Layers className={`h-5 w-5 ${isActive ? 'text-brand-400' : 'text-slate-500'}`} />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold text-white truncate">{episode.label}</span>
            {isActive && (
              <span className="shrink-0 rounded-full bg-brand-600 px-2 py-0.5 text-[10px] font-semibold text-white">
                Active
              </span>
            )}
          </div>
          <div className="mt-0.5 flex items-center gap-3 text-xs text-slate-500">
            <span className="flex items-center gap-1">
              <Calendar className="h-3 w-3" /> {date}
            </span>
            <span className="flex items-center gap-1">
              <FileText className="h-3 w-3" /> {episode.findings.length} findings
            </span>
            <StatusBadge status={episode.status} />
          </div>
        </div>

        {open ? (
          <ChevronUp className="h-5 w-5 shrink-0 text-slate-500" />
        ) : (
          <ChevronDown className="h-5 w-5 shrink-0 text-slate-500" />
        )}
      </button>

      {/* Activate / Share / Delete buttons */}
      {(!isActive || episode.approved_by || onDelete) && (
        <div className="flex items-center gap-3 border-t border-white/[0.06] px-5 py-2">
          {!isActive && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onActivate();
              }}
              className="text-xs font-medium text-brand-400 hover:text-brand-300 transition"
            >
              Set as active episode
            </button>
          )}
          {episode.approved_by && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setShowShare(true);
              }}
              className="flex items-center gap-1 text-xs font-medium text-emerald-400 hover:text-emerald-300 transition"
            >
              <Share2 className="h-3 w-3" /> Share with Patient
            </button>
          )}
          {episode.approved_by && (
            <button
              type="button"
              onClick={async (e) => {
                e.stopPropagation();
                const res = await fetch(`/api/patients/${patientId}/episodes/${episode.episode_id}/fhir`);
                if (!res.ok) return;
                const blob = new Blob([JSON.stringify(await res.json(), null, 2)], { type: 'application/fhir+json' });
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = `${patientId}_${episode.episode_id}_fhir_r4.json`;
                a.click();
                URL.revokeObjectURL(a.href);
              }}
              className="flex items-center gap-1 text-xs font-medium text-blue-400 hover:text-blue-300 transition"
            >
              <Download className="h-3 w-3" /> FHIR R4 Export
            </button>
          )}
          {onDelete && (
            <div className="ml-auto">
              {confirmDelete ? (
                <div className="flex items-center gap-2">
                  <span className="text-[11px] text-red-400">Delete this episode?</span>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete();
                      setConfirmDelete(false);
                    }}
                    className="text-[11px] font-bold text-red-400 hover:text-red-300"
                  >
                    Yes
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setConfirmDelete(false);
                    }}
                    className="text-[11px] font-medium text-slate-500 hover:text-slate-300"
                  >
                    No
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setConfirmDelete(true);
                  }}
                  className="flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-red-400 transition"
                  title="Delete episode"
                >
                  <Trash2 className="h-3 w-3" /> Delete
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* Collapsible body */}
      {open && (
        <div className="border-t border-white/[0.06] bg-surface-1/50 px-5 py-5">
          {/* Agent Pipeline Stepper */}
          <div className="mb-4 rounded-xl border border-white/[0.06] bg-surface-2 px-3 py-1">
            <AgentStepper episode={episode} />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
            <XrayCard findings={xrayFindings} ingestedFiles={episode.ingested_files} />
            <TranscriptCard findings={textFindings} />
            <SynthesisCard
              synthesis={episode.synthesis}
              patientId={patientId}
              episodeId={episode.episode_id}
              approvedBy={episode.approved_by}
              approvedAt={episode.approved_at}
            />
          </div>

          {/* Episode activity snippet */}
          {episode.activity_log.length > 0 && (
            <div className="mt-4 rounded-xl border border-white/[0.06] bg-surface-2 p-3">
              <p className="mb-2 text-xs font-semibold text-slate-400">
                Episode Activity ({episode.activity_log.length} events)
              </p>
              <div className="max-h-48 overflow-y-auto space-y-1">
                {episode.activity_log.slice(-5).map((a, i) => (
                  <p key={i} className="text-[11px] text-slate-500">
                    <span className="font-medium text-slate-400">{a.action}</span> — {a.detail}
                  </p>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Share Modal */}
      {showShare && (
        <ShareModal
          patientId={patientId}
          episodeId={episode.episode_id}
          episodeLabel={episode.label}
          onClose={() => setShowShare(false)}
        />
      )}
    </div>
  );
}
