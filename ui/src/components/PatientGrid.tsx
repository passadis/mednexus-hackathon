import { useState, useEffect } from 'react';
import { Users, Activity, FileText, CheckCircle, Clock, AlertCircle, Search, Stethoscope, Trash2 } from 'lucide-react';
import type { PatientContext } from '../types';

interface PatientGridProps {
  onSelectPatient: (id: string) => void;
  onDeletePatient?: (id: string) => void;
}

type SummaryStatus = 'approved' | 'synthesised' | 'processing' | 'new';

function getPatientStatus(ctx: PatientContext): SummaryStatus {
  // Check episode-level approvals first
  const hasApproval = ctx.episodes.some((ep) => ep.approved_by);
  if (hasApproval || ctx.approved_by) return 'approved';

  const hasSynthesis = ctx.episodes.some((ep) => ep.synthesis) || ctx.synthesis;
  if (hasSynthesis) return 'synthesised';

  const hasFindings = ctx.episodes.some((ep) => ep.findings.length > 0) || ctx.findings.length > 0;
  if (hasFindings) return 'processing';

  return 'new';
}

const STATUS_CONFIG: Record<SummaryStatus, { label: string; color: string; icon: typeof CheckCircle }> = {
  approved: { label: 'Approved', color: 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/25', icon: CheckCircle },
  synthesised: { label: 'Synthesised', color: 'bg-blue-500/15 text-blue-400 ring-blue-500/25', icon: FileText },
  processing: { label: 'Processing', color: 'bg-amber-500/15 text-amber-400 ring-amber-500/25', icon: Clock },
  new: { label: 'New', color: 'bg-slate-500/15 text-slate-400 ring-slate-500/25', icon: AlertCircle },
};

export function PatientGrid({ onSelectPatient, onDeletePatient }: PatientGridProps) {
  const [patients, setPatients] = useState<PatientContext[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch('/api/patients?limit=100');
        if (res.ok) {
          const data: PatientContext[] = await res.json();
          setPatients(data);
        }
      } catch {
        // silent — user can still search
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const filtered = search.trim()
    ? patients.filter(
        (p) =>
          p.patient.patient_id.toLowerCase().includes(search.toLowerCase()) ||
          (p.patient.name && p.patient.name.toLowerCase().includes(search.toLowerCase())),
      )
    : patients;

  // Stats
  const total = patients.length;
  const approved = patients.filter((p) => getPatientStatus(p) === 'approved').length;
  const synthesised = patients.filter((p) => getPatientStatus(p) === 'synthesised').length;
  const totalFindings = patients.reduce(
    (acc, p) => acc + p.episodes.reduce((ea, ep) => ea + ep.findings.length, 0) + p.findings.length,
    0,
  );

  return (
    <div className="flex flex-1 flex-col overflow-y-auto bg-surface-0 p-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-1">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 shadow-lg shadow-brand-500/20">
            <Stethoscope className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">MedNexus Command Center</h1>
            <p className="text-sm text-slate-500">Multi-Agent Clinical Analysis Platform</p>
          </div>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-2 gap-3 mb-6 sm:grid-cols-4">
        <div className="card flex items-center gap-3 p-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-500/15">
            <Users className="h-5 w-5 text-brand-400" />
          </div>
          <div>
            <p className="text-2xl font-bold text-white">{total}</p>
            <p className="text-xs text-slate-500">Patients</p>
          </div>
        </div>
        <div className="card flex items-center gap-3 p-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/15">
            <CheckCircle className="h-5 w-5 text-emerald-400" />
          </div>
          <div>
            <p className="text-2xl font-bold text-white">{approved}</p>
            <p className="text-xs text-slate-500">Approved</p>
          </div>
        </div>
        <div className="card flex items-center gap-3 p-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500/15">
            <FileText className="h-5 w-5 text-blue-400" />
          </div>
          <div>
            <p className="text-2xl font-bold text-white">{synthesised}</p>
            <p className="text-xs text-slate-500">Synthesised</p>
          </div>
        </div>
        <div className="card flex items-center gap-3 p-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-500/15">
            <Activity className="h-5 w-5 text-purple-400" />
          </div>
          <div>
            <p className="text-2xl font-bold text-white">{totalFindings}</p>
            <p className="text-xs text-slate-500">Findings</p>
          </div>
        </div>
      </div>

      {/* Search */}
      <div className="relative mb-5">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search patients by ID or name..."
          className="input-glass pl-10"
        />
      </div>

      {/* Grid */}
      {loading ? (
        <div className="flex flex-1 items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand-500/30 border-t-brand-400" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 text-slate-500">
          <Users className="h-12 w-12" />
          <p className="text-sm">
            {search ? 'No patients match your search' : 'No patients yet — search for a Patient ID in the sidebar'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filtered.map((p) => {
            const status = getPatientStatus(p);
            const cfg = STATUS_CONFIG[status];
            const StatusIcon = cfg.icon;
            const episodeCount = p.episodes.length;
            const findingCount =
              p.episodes.reduce((a, ep) => a + ep.findings.length, 0) + p.findings.length;
            const latestDate = p.episodes.length
              ? new Date(
                  [...p.episodes].sort(
                    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
                  )[0].updated_at,
                ).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
              : new Date(p.updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

            return (
              <button
                key={p.id}
                type="button"
                onClick={() => onSelectPatient(p.patient.patient_id)}
                className="card-hover text-left transition-all duration-300 hover:scale-[1.02] relative group"
              >
                {/* Delete button */}
                {onDeletePatient && (
                  <div
                    className="absolute top-2 right-2 z-10 opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {confirmDelete === p.patient.patient_id ? (
                      <div className="flex items-center gap-1 bg-surface-2 rounded-lg shadow-lg border border-red-500/30 px-2 py-1">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onDeletePatient(p.patient.patient_id);
                            setPatients((prev) => prev.filter((x) => x.patient.patient_id !== p.patient.patient_id));
                            setConfirmDelete(null);
                          }}
                          className="text-[10px] font-bold text-red-400 hover:text-red-300 px-1"
                        >
                          Confirm
                        </button>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setConfirmDelete(null);
                          }}
                          className="text-[10px] font-medium text-slate-500 hover:text-slate-300 px-1"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setConfirmDelete(p.patient.patient_id);
                        }}
                        className="flex h-7 w-7 items-center justify-center rounded-lg bg-surface-2/90 shadow-sm border border-white/10 hover:border-red-500/40 hover:bg-red-500/10 transition"
                        title="Delete patient"
                      >
                        <Trash2 className="h-3.5 w-3.5 text-slate-500 hover:text-red-400" />
                      </button>
                    )}
                  </div>
                )}
                {/* Status bar */}
                <div
                  className={`flex items-center gap-1.5 rounded-t-xl px-4 py-1.5 text-xs font-medium ring-1 ring-inset ${cfg.color}`}
                >
                  <StatusIcon className="h-3 w-3" />
                  {cfg.label}
                </div>

                <div className="p-4">
                  <p className="text-sm font-bold text-slate-100 truncate">
                    {p.patient.name || p.patient.patient_id}
                  </p>
                  <p className="text-xs text-slate-500 mt-0.5">ID: {p.patient.patient_id}</p>

                  <div className="mt-3 flex items-center gap-3 text-xs text-slate-500">
                    <span>{episodeCount} episode{episodeCount !== 1 ? 's' : ''}</span>
                    <span className="text-slate-700">|</span>
                    <span>{findingCount} finding{findingCount !== 1 ? 's' : ''}</span>
                    <span className="text-slate-700">|</span>
                    <span>{latestDate}</span>
                  </div>

                  {/* Episode status dots */}
                  {episodeCount > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1">
                      {[...p.episodes].reverse().slice(0, 6).map((ep) => {
                        const epApproved = !!ep.approved_by;
                        const epSynthesis = !!ep.synthesis;
                        const dotColor = epApproved
                          ? 'bg-emerald-400 shadow-emerald-400/30'
                          : epSynthesis
                            ? 'bg-blue-400 shadow-blue-400/30'
                            : ep.findings.length > 0
                              ? 'bg-amber-400 shadow-amber-400/30'
                              : 'bg-slate-600';
                        return (
                          <div
                            key={ep.episode_id}
                            className={`h-2 w-2 rounded-full shadow-sm ${dotColor}`}
                            title={`${ep.label}: ${ep.status}`}
                          />
                        );
                      })}
                      {episodeCount > 6 && (
                        <span className="text-[10px] text-slate-500">+{episodeCount - 6}</span>
                      )}
                    </div>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
