import { useState } from 'react';
import { Brain, AlertTriangle, ChevronRight, ShieldCheck, Pencil, Save, X } from 'lucide-react';
import type { SynthesisReport } from '../../types';

interface SynthesisCardProps {
  synthesis: SynthesisReport | null;
  patientId?: string;
  episodeId?: string | null;
  approvedBy?: string | null;
  approvedAt?: string | null;
  onSynthesisUpdated?: (updated: SynthesisReport) => void;
}

export function SynthesisCard({ synthesis, patientId, episodeId, approvedBy, approvedAt, onSynthesisUpdated }: SynthesisCardProps) {
  const [isApproving, setIsApproving] = useState(false);
  const [localApproval, setLocalApproval] = useState<{ by: string; at: string } | null>(null);
  const [editing, setEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [editSummary, setEditSummary] = useState('');
  const [editNotes, setEditNotes] = useState('');
  const [editRecs, setEditRecs] = useState('');

  const isApproved = !!(approvedBy || localApproval);

  const startEditing = () => {
    if (!synthesis) return;
    setEditSummary(synthesis.summary);
    setEditNotes(synthesis.cross_modality_notes || '');
    setEditRecs(synthesis.recommendations.join('\n'));
    setEditing(true);
  };

  const cancelEditing = () => setEditing(false);

  const handleSave = async () => {
    if (!patientId || !episodeId || !synthesis) return;
    setIsSaving(true);
    try {
      const res = await fetch(`/api/patients/${patientId}/episodes/${episodeId}/synthesis`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          summary: editSummary,
          cross_modality_notes: editNotes,
          recommendations: editRecs.split('\n').map(r => r.trim()).filter(Boolean),
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setEditing(false);
        if (onSynthesisUpdated && data.synthesis) {
          onSynthesisUpdated(data.synthesis as SynthesisReport);
        }
      } else {
        const err = await res.json().catch(() => ({ detail: 'Save failed' }));
        alert(err.detail || 'Save failed');
      }
    } catch {
      alert('Network error – could not reach server');
    } finally {
      setIsSaving(false);
    }
  };

  const handleApprove = async () => {
    if (!patientId || !synthesis) return;
    const name = prompt('Enter your name (MD) for sign-off:');
    if (!name?.trim()) return;

    setIsApproving(true);
    try {
      const res = await fetch(`/api/patients/${patientId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved_by: name.trim(), notes: '', episode_id: episodeId || null }),
      });
      if (res.ok) {
        const data = await res.json();
        setLocalApproval({ by: data.approved_by, at: data.approved_at });
      } else {
        const err = await res.json().catch(() => ({ detail: 'Approval failed' }));
        alert(err.detail || 'Approval failed');
      }
    } catch {
      alert('Network error – could not reach server');
    } finally {
      setIsApproving(false);
    }
  };

  const displayApprovedBy = localApproval?.by ?? approvedBy;
  const displayApprovedAt = localApproval?.at ?? approvedAt;
  return (
    <div className="card lg:col-span-2 xl:col-span-1">
      <div className="mb-3 flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-rose-500/15">
          <Brain className="h-4 w-4 text-rose-400" />
        </div>
        <h3 className="text-sm font-semibold text-slate-200">Synthesis Report</h3>
        {synthesis && !isApproved && !editing && (
          <button
            type="button"
            onClick={startEditing}
            className="ml-auto flex items-center gap-1 rounded-lg border border-white/10 px-2 py-1 text-xs text-slate-400 transition hover:bg-white/5 hover:text-slate-200"
            title="Edit before sign-off"
          >
            <Pencil className="h-3 w-3" /> Edit
          </button>
        )}
        {editing && (
          <div className="ml-auto flex items-center gap-1.5">
            <button
              type="button"
              onClick={handleSave}
              disabled={isSaving}
              className="flex items-center gap-1 rounded-lg bg-brand-600 px-2.5 py-1 text-xs font-medium text-white transition hover:bg-brand-700 disabled:opacity-60"
            >
              <Save className="h-3 w-3" /> {isSaving ? 'Saving…' : 'Save'}
            </button>
            <button
              type="button"
              onClick={cancelEditing}
              className="flex items-center gap-1 rounded-lg border border-white/10 px-2 py-1 text-xs text-slate-400 transition hover:bg-white/5"
            >
              <X className="h-3 w-3" /> Cancel
            </button>
          </div>
        )}
      </div>

      {!synthesis ? (
        <div className="flex h-40 flex-col items-center justify-center rounded-xl border-2 border-dashed border-white/10 bg-white/[0.02]">
          <Brain className="mb-2 h-8 w-8 text-slate-600" />
          <p className="text-xs text-slate-500">Awaiting cross-modality analysis</p>
          <p className="mt-1 text-[10px] text-slate-600">
            Upload imaging + clinical records to trigger synthesis
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Summary */}
          <div>
            {editing ? (
              <textarea
                value={editSummary}
                onChange={e => setEditSummary(e.target.value)}
                rows={4}
                placeholder="Synthesis summary"
                className="w-full rounded-lg border border-white/10 bg-white/5 p-2 text-sm text-slate-200 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/30"
              />
            ) : (
              <p className="text-sm leading-relaxed text-slate-300">{synthesis.summary}</p>
            )}
          </div>

          {/* Cross-modality notes */}
          {(synthesis.cross_modality_notes || editing) && (
            <div className="rounded-xl bg-amber-500/10 p-3 border border-amber-500/20">
              <p className="mb-1 text-xs font-semibold text-amber-400">Cross-Modality Notes</p>
              {editing ? (
                <textarea
                  value={editNotes}
                  onChange={e => setEditNotes(e.target.value)}
                  rows={3}
                  placeholder="Cross-modality notes"
                  className="w-full rounded-lg border border-amber-500/20 bg-white/5 p-2 text-xs text-amber-300 focus:border-amber-500/40 focus:outline-none focus:ring-1 focus:ring-amber-500/20"
                />
              ) : (
                <p className="text-xs text-amber-300 leading-relaxed">
                  {synthesis.cross_modality_notes}
                </p>
              )}
            </div>
          )}

          {/* Discrepancies */}
          {synthesis.discrepancies.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-red-400 flex items-center gap-1">
                <AlertTriangle className="h-3.5 w-3.5" />
                Discrepancies ({synthesis.discrepancies.length})
              </p>
              {synthesis.discrepancies.map((d, i) => (
                <div
                  key={i}
                  className="rounded-lg border border-red-500/20 bg-red-500/10 p-2.5"
                >
                  <p className="text-xs text-red-400">{d.description}</p>
                  <span className="mt-1 badge-red">{d.severity}</span>
                </div>
              ))}
            </div>
          )}

          {/* Recommendations */}
          {(synthesis.recommendations.length > 0 || editing) && (
            <div>
              <p className="mb-2 text-xs font-semibold text-slate-500">Recommendations</p>
              {editing ? (
                <textarea
                  value={editRecs}
                  onChange={e => setEditRecs(e.target.value)}
                  rows={4}
                  placeholder="One recommendation per line"
                  className="w-full rounded-lg border border-white/10 bg-white/5 p-2 text-xs text-slate-300 focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/30"
                />
              ) : (
                <ul className="space-y-1.5">
                  {synthesis.recommendations.map((rec, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-slate-300">
                      <ChevronRight className="mt-0.5 h-3 w-3 shrink-0 text-brand-500" />
                      {rec}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Metadata */}
          <div className="border-t border-white/[0.06] pt-2">
            <p className="text-[10px] text-slate-400">
              Generated by {synthesis.generated_by} at{' '}
              {new Date(synthesis.generated_at).toLocaleString()}
            </p>
          </div>

          {/* ── Phase 3: Human-in-the-Loop MD Sign-Off ────── */}
          {isApproved ? (
            <div className="mt-4 flex items-center gap-3 rounded-xl border-2 border-emerald-500/30 bg-emerald-500/10 p-4">
              <ShieldCheck className="h-6 w-6 text-emerald-400 shrink-0" />
              <div>
                <p className="text-sm font-bold text-emerald-300">Approved &amp; Signed Off</p>
                <p className="text-xs text-emerald-400">
                  By {displayApprovedBy} on{' '}
                  {displayApprovedAt ? new Date(displayApprovedAt).toLocaleString() : '—'}
                </p>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={handleApprove}
              disabled={isApproving}
              className="mt-4 w-full rounded-xl bg-gradient-to-r from-brand-500 to-brand-700 px-6 py-4 text-center text-base
                         font-bold text-white shadow-lg shadow-brand-500/20 transition
                         hover:shadow-brand-500/30 hover:shadow-xl
                         focus:outline-none focus:ring-4 focus:ring-brand-500/30
                         disabled:cursor-wait disabled:opacity-60"
            >
              {isApproving ? 'Submitting…' : '✅ Approve and Sign-off by MD'}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
