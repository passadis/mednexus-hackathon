import { useState } from 'react';
import { ChevronDown, ChevronUp, Calendar, FileText, Layers, Share2 } from 'lucide-react';
import type { Episode } from '../../types';
import { XrayCard } from './XrayCard';
import { TranscriptCard } from './TranscriptCard';
import { SynthesisCard } from './SynthesisCard';
import { StatusBadge } from '../StatusBadge';
import { ShareModal } from '../ShareModal';

interface EpisodeCardProps {
  episode: Episode;
  patientId: string;
  isActive: boolean;
  defaultOpen?: boolean;
  onActivate: () => void;
}

export function EpisodeCard({
  episode,
  patientId,
  isActive,
  defaultOpen = false,
  onActivate,
}: EpisodeCardProps) {
  const [open, setOpen] = useState(defaultOpen);
  const [showShare, setShowShare] = useState(false);

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
          ? 'border-brand-300 shadow-lg shadow-brand-100/50'
          : 'border-slate-200 shadow-sm hover:border-slate-300'
      }`}
    >
      {/* Header — always visible */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-3 rounded-t-2xl px-5 py-4 text-left transition hover:bg-slate-50/60"
      >
        <div
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${
            isActive ? 'bg-brand-100' : 'bg-slate-100'
          }`}
        >
          <Layers className={`h-5 w-5 ${isActive ? 'text-brand-600' : 'text-slate-400'}`} />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold text-slate-800 truncate">{episode.label}</span>
            {isActive && (
              <span className="shrink-0 rounded-full bg-brand-600 px-2 py-0.5 text-[10px] font-semibold text-white">
                Active
              </span>
            )}
          </div>
          <div className="mt-0.5 flex items-center gap-3 text-xs text-slate-400">
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
          <ChevronUp className="h-5 w-5 shrink-0 text-slate-400" />
        ) : (
          <ChevronDown className="h-5 w-5 shrink-0 text-slate-400" />
        )}
      </button>

      {/* Activate / Share buttons */}
      {(!isActive || episode.approved_by) && (
        <div className="flex items-center gap-3 border-t border-slate-100 px-5 py-2">
          {!isActive && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onActivate();
              }}
              className="text-xs font-medium text-brand-600 hover:text-brand-700 transition"
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
              className="ml-auto flex items-center gap-1 text-xs font-medium text-emerald-600 hover:text-emerald-700 transition"
            >
              <Share2 className="h-3 w-3" /> Share with Patient
            </button>
          )}
        </div>
      )}

      {/* Collapsible body */}
      {open && (
        <div className="border-t border-slate-100 bg-slate-50/30 px-5 py-5">
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
            <div className="mt-4 rounded-xl border border-slate-100 bg-white p-3">
              <p className="mb-2 text-xs font-semibold text-slate-500">
                Episode Activity ({episode.activity_log.length} events)
              </p>
              <div className="max-h-48 overflow-y-auto space-y-1">
                {episode.activity_log.slice(-5).map((a, i) => (
                  <p key={i} className="text-[11px] text-slate-400">
                    <span className="font-medium text-slate-500">{a.action}</span> — {a.detail}
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
