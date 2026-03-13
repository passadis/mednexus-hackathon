import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity,
  BarChart3,
  CalendarDays,
  ClipboardList,
  FileText,
  Home,
  RefreshCw,
  ShieldCheck,
  Users,
} from 'lucide-react';
import type { PatientContext } from '../types';

interface DailyCount {
  dayLabel: string;
  value: number;
}

interface NamedCount {
  label: string;
  value: number;
}

interface ActivityItem {
  timestamp: string;
  patientId: string;
  episodeLabel: string;
  action: string;
  detail: string;
}

interface DashboardData {
  totalPatients: number;
  inProgressCases: number;
  completedSyntheses: number;
  approvedEpisodes: number;
  patientsPerDay: DailyCount[];
  episodesPerDay: DailyCount[];
  synthesisStatus: NamedCount[];
  approvalsPerDoctor: NamedCount[];
  modalityMix: NamedCount[];
  recentActivity: ActivityItem[];
}

function startOfMonthUtc(date: Date) {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1));
}

function parseDate(value?: string | null) {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatDayLabel(date: Date) {
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  });
}

function normalizeDoctorName(value?: string | null) {
  return value && value.trim() ? value.trim() : 'Unassigned';
}

function isInProgress(status: string) {
  return !['synthesis_complete', 'approved', 'finalized'].includes(status);
}

function humanizeLabel(value: string) {
  return value.replace(/_/g, ' ');
}

function buildMonthBuckets(now: Date): { labels: string[]; keys: string[] } {
  const start = startOfMonthUtc(now);
  const labels: string[] = [];
  const keys: string[] = [];
  const cursor = new Date(start);

  while (cursor <= now) {
    keys.push(cursor.toISOString().slice(0, 10));
    labels.push(formatDayLabel(cursor));
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }

  return { labels, keys };
}

function deriveDashboardData(patients: PatientContext[]): DashboardData {
  const now = new Date();
  const monthStart = startOfMonthUtc(now);
  const { labels, keys } = buildMonthBuckets(now);

  const patientCounts = new Map(keys.map((key) => [key, 0]));
  const episodeCounts = new Map(keys.map((key) => [key, 0]));
  const approvalsPerDoctor = new Map<string, number>();
  const modalityCounts = new Map<string, number>();
  const activity: ActivityItem[] = [];

  let inProgressCases = 0;
  let completedSyntheses = 0;
  let approvedEpisodes = 0;

  for (const patient of patients) {
    const patientCreated = parseDate(patient.created_at);
    if (patientCreated && patientCreated >= monthStart) {
      const key = patientCreated.toISOString().slice(0, 10);
      patientCounts.set(key, (patientCounts.get(key) ?? 0) + 1);
    }

    for (const episode of patient.episodes ?? []) {
      const episodeCreated = parseDate(episode.created_at);
      if (episodeCreated && episodeCreated >= monthStart) {
        const key = episodeCreated.toISOString().slice(0, 10);
        episodeCounts.set(key, (episodeCounts.get(key) ?? 0) + 1);
      }

      if (isInProgress(episode.status)) {
        inProgressCases += 1;
      }
      if (episode.status === 'synthesis_complete') {
        completedSyntheses += 1;
      }
      if (episode.status === 'approved') {
        approvedEpisodes += 1;
      }

      if (episode.approved_by) {
        const doctor = normalizeDoctorName(episode.approved_by);
        approvalsPerDoctor.set(doctor, (approvalsPerDoctor.get(doctor) ?? 0) + 1);
      }

      for (const finding of episode.findings ?? []) {
        const label =
          finding.modality === 'radiology_image'
            ? 'X-ray / Imaging'
            : finding.modality === 'clinical_text'
              ? 'Clinical Notes'
              : finding.modality === 'audio_transcript'
                ? 'Audio Transcript'
                : humanizeLabel(finding.modality);
        modalityCounts.set(label, (modalityCounts.get(label) ?? 0) + 1);
      }

      for (const item of episode.activity_log ?? []) {
        activity.push({
          timestamp: item.timestamp,
          patientId: patient.patient.patient_id,
          episodeLabel: episode.label,
          action: item.action,
          detail: item.detail,
        });
      }
    }
  }

  const patientsPerDay = labels.map((dayLabel, index) => ({
    dayLabel,
    value: patientCounts.get(keys[index]) ?? 0,
  }));

  const episodesPerDay = labels.map((dayLabel, index) => ({
    dayLabel,
    value: episodeCounts.get(keys[index]) ?? 0,
  }));

  const synthesisStatus = [
    { label: 'In Progress', value: inProgressCases },
    { label: 'Synthesis Complete', value: completedSyntheses },
    { label: 'Approved', value: approvedEpisodes },
  ];

  const approvalsChart = [...approvalsPerDoctor.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([label, value]) => ({ label, value }));

  const modalityMix = [...modalityCounts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([label, value]) => ({ label, value }));

  const recentActivity = activity
    .sort((a, b) => String(b.timestamp).localeCompare(String(a.timestamp)))
    .slice(0, 10);

  return {
    totalPatients: patients.length,
    inProgressCases,
    completedSyntheses,
    approvedEpisodes,
    patientsPerDay,
    episodesPerDay,
    synthesisStatus,
    approvalsPerDoctor: approvalsChart,
    modalityMix,
    recentActivity,
  };
}

function StatCard({
  label,
  value,
  icon: Icon,
  accent,
}: {
  label: string;
  value: number | string;
  icon: typeof Users;
  accent: string;
}) {
  return (
    <div className="card flex items-center gap-4">
      <div className={`flex h-12 w-12 items-center justify-center rounded-2xl ${accent}`}>
        <Icon className="h-5 w-5" />
      </div>
      <div>
        <p className="text-2xl font-bold text-slate-800">{value}</p>
        <p className="text-xs uppercase tracking-[0.18em] text-slate-400">{label}</p>
      </div>
    </div>
  );
}

function VerticalBars({
  title,
  subtitle,
  data,
  tone,
}: {
  title: string;
  subtitle: string;
  data: DailyCount[];
  tone: string;
}) {
  const max = Math.max(...data.map((item) => item.value), 1);
  return (
    <div className="card">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
        <p className="text-xs text-slate-400">{subtitle}</p>
      </div>
      <div className="flex h-48 items-end gap-2 overflow-hidden">
        {data.map((item, index) => (
          <div key={`${item.dayLabel}-${index}`} className="flex min-w-0 flex-1 flex-col items-center gap-2">
            <div className="text-[10px] font-semibold text-slate-500">{item.value}</div>
            <div className="flex h-32 w-full items-end rounded-t-xl bg-slate-100/80 px-[2px]">
              <div
                className={`w-full rounded-t-lg transition-all duration-500 ${tone}`}
                style={{ height: `${Math.max((item.value / max) * 100, item.value > 0 ? 8 : 0)}%` }}
              />
            </div>
            <div className="w-full truncate text-center text-[10px] text-slate-400">{item.dayLabel}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function HorizontalBars({
  title,
  subtitle,
  data,
  tone,
}: {
  title: string;
  subtitle: string;
  data: NamedCount[];
  tone: string;
}) {
  const max = Math.max(...data.map((item) => item.value), 1);
  return (
    <div className="card">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
        <p className="text-xs text-slate-400">{subtitle}</p>
      </div>
      <div className="space-y-3">
        {data.map((item) => (
          <div key={item.label}>
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="font-medium text-slate-600">{item.label}</span>
              <span className="text-slate-400">{item.value}</span>
            </div>
            <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
              <div
                className={`h-full rounded-full transition-all duration-500 ${tone}`}
                style={{ width: `${Math.max((item.value / max) * 100, item.value > 0 ? 8 : 0)}%` }}
              />
            </div>
          </div>
        ))}
        {data.length === 0 && <p className="text-xs italic text-slate-400">No data yet</p>}
      </div>
    </div>
  );
}

export function ObservabilityPage({ onBackToGrid }: { onBackToGrid?: () => void }) {
  const [patients, setPatients] = useState<PatientContext[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/patients?limit=200');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as PatientContext[];
      setPatients(Array.isArray(data) ? data : []);
    } catch {
      setPatients([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const dashboard = useMemo(() => deriveDashboardData(patients), [patients]);

  return (
    <div className="flex-1 overflow-y-auto bg-slate-50/50 p-6">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          {onBackToGrid && (
            <button
              type="button"
              onClick={onBackToGrid}
              className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium text-brand-600 transition hover:bg-brand-50"
            >
              <Home className="h-3.5 w-3.5" /> Back to Patient Grid
            </button>
          )}
          <div>
            <h2 className="text-xl font-bold text-slate-800">Clinical Operations Dashboard</h2>
            <p className="text-sm text-slate-400">A simple month-to-date view of patient flow, syntheses, and approvals.</p>
          </div>
        </div>

        <button onClick={refresh} disabled={loading} className="btn-secondary">
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard label="Total Patients" value={dashboard.totalPatients} icon={Users} accent="bg-brand-50 text-brand-600" />
        <StatCard label="In Progress" value={dashboard.inProgressCases} icon={Activity} accent="bg-amber-50 text-amber-600" />
        <StatCard label="Syntheses Complete" value={dashboard.completedSyntheses} icon={FileText} accent="bg-emerald-50 text-emerald-600" />
        <StatCard label="Approved Episodes" value={dashboard.approvedEpisodes} icon={ShieldCheck} accent="bg-blue-50 text-blue-600" />
      </div>

      <div className="mb-6 grid gap-4 xl:grid-cols-2">
        <VerticalBars
          title="Patients Per Day"
          subtitle="New patients created this month"
          data={dashboard.patientsPerDay}
          tone="bg-brand-500"
        />
        <VerticalBars
          title="Episodes Per Day"
          subtitle="New episodes created this month"
          data={dashboard.episodesPerDay}
          tone="bg-emerald-500"
        />
      </div>

      <div className="mb-6 grid gap-4 xl:grid-cols-3">
        <HorizontalBars
          title="Case Status Mix"
          subtitle="Current episode outcomes"
          data={dashboard.synthesisStatus}
          tone="bg-blue-500"
        />
        <HorizontalBars
          title="Approvals Per Doctor"
          subtitle="Signed-off episodes by clinician"
          data={dashboard.approvalsPerDoctor}
          tone="bg-rose-500"
        />
        <HorizontalBars
          title="Top Modalities"
          subtitle="Most common findings across cases"
          data={dashboard.modalityMix}
          tone="bg-violet-500"
        />
      </div>

      <div className="card">
        <div className="mb-4 flex items-center gap-2">
          <ClipboardList className="h-4 w-4 text-brand-500" />
          <div>
            <h3 className="text-sm font-semibold text-slate-800">Recent Clinical Activity</h3>
            <p className="text-xs text-slate-400">Latest workflow and sign-off events across the clinic</p>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs uppercase tracking-[0.18em] text-slate-400">
                <th className="pb-3 pr-3 font-semibold">Time</th>
                <th className="pb-3 pr-3 font-semibold">Patient</th>
                <th className="pb-3 pr-3 font-semibold">Episode</th>
                <th className="pb-3 pr-3 font-semibold">Action</th>
                <th className="pb-3 font-semibold">Detail</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.recentActivity.map((item, index) => (
                <tr key={`${item.timestamp}-${item.patientId}-${index}`} className="border-b border-slate-50">
                  <td className="py-3 pr-3 whitespace-nowrap text-xs text-slate-500">
                    {new Date(item.timestamp).toLocaleString('en-US', {
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </td>
                  <td className="py-3 pr-3 text-sm font-medium text-slate-700">{item.patientId}</td>
                  <td className="py-3 pr-3 text-sm text-slate-600">{item.episodeLabel}</td>
                  <td className="py-3 pr-3">
                    <span className="inline-flex rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-slate-600">
                      {humanizeLabel(item.action)}
                    </span>
                  </td>
                  <td className="py-3 text-sm text-slate-600">{item.detail || 'No detail available'}</td>
                </tr>
              ))}
              {dashboard.recentActivity.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-12 text-center">
                    <CalendarDays className="mx-auto mb-3 h-8 w-8 text-slate-300" />
                    <p className="text-sm font-medium text-slate-500">No clinic activity yet</p>
                    <p className="text-xs text-slate-400">Run a patient workflow and refresh this page.</p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-2 text-xs text-slate-400">
        <BarChart3 className="h-3.5 w-3.5" />
        This dashboard is derived directly from patient and episode records already stored in MedNexus.
      </div>
    </div>
  );
}
