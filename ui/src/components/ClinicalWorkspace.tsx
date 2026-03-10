import { FileUp, RefreshCw, AlertCircle, Loader2, Plus } from 'lucide-react';
import type { PatientContext } from '../types';
import { XrayCard } from './cards/XrayCard';
import { TranscriptCard } from './cards/TranscriptCard';
import { SynthesisCard } from './cards/SynthesisCard';
import { FindingsTimeline } from './cards/FindingsTimeline';
import { EpisodeCard } from './cards/EpisodeCard';
import { CrossEpisodeCard } from './cards/CrossEpisodeCard';
import { FileUploader } from './FileUploader';
import { StatusBadge } from './StatusBadge';

interface ClinicalWorkspaceProps {
  context: PatientContext | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  onDeleteEpisode?: (episodeId: string) => void;
}

export function ClinicalWorkspace({ context, loading, error, onRefresh, onDeleteEpisode }: ClinicalWorkspaceProps) {
  if (!context && !loading && !error) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 bg-slate-50 p-8">
        <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-brand-50">
          <FileUp className="h-10 w-10 text-brand-400" />
        </div>
        <h2 className="text-xl font-semibold text-slate-600">Welcome to MedNexus</h2>
        <p className="max-w-md text-center text-sm text-slate-400">
          Search for a Patient ID in the sidebar, or upload a medical file to begin
          the multi-agent clinical analysis pipeline.
        </p>
      </div>
    );
  }

  if (loading && !context) {
    return (
      <div className="flex flex-1 items-center justify-center bg-slate-50">
        <Loader2 className="h-8 w-8 animate-spin text-brand-500" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 bg-slate-50">
        <AlertCircle className="h-8 w-8 text-medical-red" />
        <p className="text-sm text-slate-500">{error}</p>
        <button onClick={onRefresh} className="btn-secondary">
          <RefreshCw className="h-4 w-4" /> Retry
        </button>
      </div>
    );
  }

  if (!context) return null;

  const hasEpisodes = context.episodes && context.episodes.length > 0;
  const activeEpisodeId = context.active_episode_id;

  // Create a new episode via API
  const handleNewEpisode = async () => {
    try {
      const res = await fetch(`/api/patients/${context.patient.patient_id}/episodes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (res.ok) {
        onRefresh();
      }
    } catch {
      console.error('Failed to create episode');
    }
  };

  // Activate an episode
  const handleActivateEpisode = async (episodeId: string) => {
    try {
      await fetch(
        `/api/patients/${context.patient.patient_id}/episodes/${episodeId}/activate`,
        { method: 'PATCH' },
      );
      onRefresh();
    } catch {
      console.error('Failed to activate episode');
    }
  };

  return (
    <div className="flex flex-1 flex-col overflow-y-auto bg-slate-50 p-6">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">
            Patient: {context.patient.name || context.patient.patient_id}
          </h2>
          <div className="mt-1 flex items-center gap-3">
            <span className="text-sm text-slate-400">ID: {context.patient.patient_id}</span>
            <StatusBadge status={context.status} />
            {hasEpisodes && (
              <span className="text-xs text-slate-400">
                {context.episodes.length} episode{context.episodes.length !== 1 ? 's' : ''}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {hasEpisodes && (
            <button onClick={handleNewEpisode} className="btn-secondary">
              <Plus className="h-4 w-4" /> New Episode
            </button>
          )}
          <button onClick={onRefresh} className="btn-secondary">
            <RefreshCw className="h-4 w-4" /> Refresh
          </button>
          <FileUploader
            patientId={context.patient.patient_id}
            episodeId={activeEpisodeId}
            onUploaded={onRefresh}
          />
        </div>
      </div>

      {/* ── Episode-Based Layout ─────────────────────────── */}
      {hasEpisodes ? (
        <div className="space-y-5">
          {/* Cross-Episode Intelligence (shown when 2+ episodes with synthesis) */}
          {context.cross_episode_summary && context.episodes.length >= 2 && (
            <CrossEpisodeCard
              summary={context.cross_episode_summary}
              episodeCount={context.episodes.length}
            />
          )}

          {/* Episodes — most-recent first */}
          {[...context.episodes].reverse().map((ep, idx) => (
            <EpisodeCard
              key={ep.episode_id}
              episode={ep}
              patientId={context.patient.patient_id}
              isActive={ep.episode_id === activeEpisodeId}
              defaultOpen={idx === 0}
              onActivate={() => handleActivateEpisode(ep.episode_id)}
              onDelete={onDeleteEpisode ? () => onDeleteEpisode(ep.episode_id) : undefined}
            />
          ))}
        </div>
      ) : (
        /* ── Legacy flat layout (no episodes yet) ──────── */
        <>
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2 xl:grid-cols-3">
            <XrayCard
              findings={context.findings.filter((f) => f.modality === 'radiology_image')}
              ingestedFiles={context.ingested_files}
            />
            <TranscriptCard
              findings={context.findings.filter(
                (f) => f.modality === 'clinical_text' || f.modality === 'audio_transcript',
              )}
            />
            <SynthesisCard
              synthesis={context.synthesis}
              patientId={context.patient.patient_id}
              approvedBy={context.approved_by}
              approvedAt={context.approved_at}
            />
          </div>
        </>
      )}

      {/* Activity Timeline */}
      <div className="mt-6">
        <FindingsTimeline activities={context.activity_log} />
      </div>
    </div>
  );
}
