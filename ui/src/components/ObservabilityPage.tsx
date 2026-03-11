import { useState, useEffect, useCallback } from 'react';
import {
  Shield,
  BarChart3,
  RefreshCw,
  Home,
  CheckCircle,
  XCircle,
  Clock,
  Users,
  FileText,
  Radio,
  ChevronDown,
  ChevronUp,
  Filter,
} from 'lucide-react';

// ── Types ───────────────────────────────────────────────────

interface AuditEntry {
  timestamp: string;
  operation: string;
  agent_id: string;
  patient_id: string;
  params: Record<string, unknown>;
  result_summary: string;
  success: boolean;
}

interface PlatformStats {
  patients_total: number;
  audit_events_total: number;
  a2a_messages_total: number;
  agent_message_counts: Record<string, number>;
  agent_audit_counts: Record<string, number>;
  operation_counts: Record<string, number>;
  audit_success: number;
  audit_failure: number;
}

// ── Helpers ─────────────────────────────────────────────────

const AGENT_COLORS: Record<string, string> = {
  orchestrator: 'bg-purple-100 text-purple-700',
  patient_historian: 'bg-blue-100 text-blue-700',
  vision_specialist: 'bg-amber-100 text-amber-700',
  clinical_sorter: 'bg-emerald-100 text-emerald-700',
  diagnostic_synthesis: 'bg-rose-100 text-rose-700',
};

function agentBadge(agent: string) {
  const color = AGENT_COLORS[agent] ?? 'bg-slate-100 text-slate-600';
  const label = agent.replace(/_/g, ' ');
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${color}`}>
      {label}
    </span>
  );
}

function formatTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function formatDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// ── Stat Card ───────────────────────────────────────────────

function StatCard({
  label,
  value,
  icon: Icon,
  accent = 'text-brand-600 bg-brand-50',
}: {
  label: string;
  value: number | string;
  icon: typeof Users;
  accent?: string;
}) {
  return (
    <div className="card flex items-center gap-4">
      <div className={`flex h-11 w-11 items-center justify-center rounded-xl ${accent}`}>
        <Icon className="h-5 w-5" />
      </div>
      <div>
        <p className="text-2xl font-bold text-slate-800">{value}</p>
        <p className="text-xs text-slate-400">{label}</p>
      </div>
    </div>
  );
}

// ── Bar Chart (pure CSS) ────────────────────────────────────

function HorizontalBar({ data, colorFn }: { data: Record<string, number>; colorFn?: (key: string) => string }) {
  const max = Math.max(...Object.values(data), 1);
  const sorted = Object.entries(data).sort((a, b) => b[1] - a[1]);

  return (
    <div className="space-y-2">
      {sorted.map(([key, count]) => {
        const pct = Math.round((count / max) * 100);
        const color = colorFn?.(key) ?? 'bg-brand-500';
        const label = key.replace(/_/g, ' ');
        return (
          <div key={key}>
            <div className="flex items-center justify-between text-xs mb-0.5">
              <span className="font-medium text-slate-600 capitalize">{label}</span>
              <span className="text-slate-400">{count}</span>
            </div>
            <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${color}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })}
      {sorted.length === 0 && (
        <p className="text-xs text-slate-400 italic">No data yet</p>
      )}
    </div>
  );
}

// ── Main Component ──────────────────────────────────────────

export function ObservabilityPage({ onBackToGrid }: { onBackToGrid?: () => void }) {
  const [stats, setStats] = useState<PlatformStats | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [agentFilter, setAgentFilter] = useState<string>('');
  const [opFilter, setOpFilter] = useState<string>('');
  const [expandedRow, setExpandedRow] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [statsRes, auditRes] = await Promise.all([
        fetch('/api/stats'),
        fetch('/api/audit?limit=200'),
      ]);
      if (statsRes.ok) setStats(await statsRes.json());
      if (auditRes.ok) setAudit(await auditRes.json());
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  // Filtered audit entries
  const filteredAudit = audit.filter((e) => {
    if (agentFilter && e.agent_id !== agentFilter) return false;
    if (opFilter && e.operation !== opFilter) return false;
    return true;
  });

  // Unique agents & operations for filter dropdowns
  const uniqueAgents = [...new Set(audit.map((e) => e.agent_id))].sort();
  const uniqueOps = [...new Set(audit.map((e) => e.operation))].sort();

  const successRate =
    stats && stats.audit_events_total > 0
      ? Math.round((stats.audit_success / stats.audit_events_total) * 100)
      : 100;

  const agentBarColor = (key: string) => {
    const map: Record<string, string> = {
      orchestrator: 'bg-purple-500',
      patient_historian: 'bg-blue-500',
      vision_specialist: 'bg-amber-500',
      clinical_sorter: 'bg-emerald-500',
      diagnostic_synthesis: 'bg-rose-500',
    };
    return map[key] ?? 'bg-slate-400';
  };

  return (
    <div className="flex-1 overflow-y-auto bg-slate-50/50 p-6">
      {/* Header */}
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
            <h2 className="text-xl font-bold text-slate-800">Platform Observability</h2>
            <p className="text-sm text-slate-400">Audit trail, agent analytics & HIPAA access log</p>
          </div>
        </div>
        <button
          onClick={refresh}
          disabled={loading}
          className="btn-secondary"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Summary Cards */}
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Total Patients" value={stats?.patients_total ?? '—'} icon={Users} />
        <StatCard
          label="Audit Events"
          value={stats?.audit_events_total ?? '—'}
          icon={Shield}
          accent="text-emerald-600 bg-emerald-50"
        />
        <StatCard
          label="A2A Messages"
          value={stats?.a2a_messages_total ?? '—'}
          icon={Radio}
          accent="text-purple-600 bg-purple-50"
        />
        <StatCard
          label="Success Rate"
          value={`${successRate}%`}
          icon={CheckCircle}
          accent={successRate >= 90 ? 'text-emerald-600 bg-emerald-50' : 'text-amber-600 bg-amber-50'}
        />
      </div>

      {/* Charts row */}
      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        {/* Agent Activity */}
        <div className="card">
          <div className="mb-4 flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-brand-500" />
            <h3 className="text-sm font-semibold text-slate-700">Agent Activity (A2A Messages)</h3>
          </div>
          <HorizontalBar data={stats?.agent_message_counts ?? {}} colorFn={agentBarColor} />
        </div>

        {/* Operation Breakdown */}
        <div className="card">
          <div className="mb-4 flex items-center gap-2">
            <FileText className="h-4 w-4 text-brand-500" />
            <h3 className="text-sm font-semibold text-slate-700">MCP Operations</h3>
          </div>
          <HorizontalBar data={stats?.operation_counts ?? {}} />
        </div>
      </div>

      {/* Audit Trail Table */}
      <div className="card">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-emerald-500" />
            <h3 className="text-sm font-semibold text-slate-700">HIPAA Audit Trail</h3>
            <span className="badge bg-slate-100 text-slate-500">{filteredAudit.length} entries</span>
          </div>

          {/* Filters */}
          <div className="flex items-center gap-2">
            <Filter className="h-3.5 w-3.5 text-slate-400" />
            <select
              value={agentFilter}
              onChange={(e) => setAgentFilter(e.target.value)}
              title="Filter by agent"
              className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-600 focus:outline-none focus:ring-2 focus:ring-brand-200"
            >
              <option value="">All Agents</option>
              {uniqueAgents.map((a) => (
                <option key={a} value={a}>{a.replace(/_/g, ' ')}</option>
              ))}
            </select>
            <select
              value={opFilter}
              onChange={(e) => setOpFilter(e.target.value)}
              title="Filter by operation"
              className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-600 focus:outline-none focus:ring-2 focus:ring-brand-200"
            >
              <option value="">All Operations</option>
              {uniqueOps.map((o) => (
                <option key={o} value={o}>{o.replace(/_/g, ' ')}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-100 text-left">
                <th className="pb-2 pr-3 font-semibold text-slate-400 uppercase tracking-wider">Time</th>
                <th className="pb-2 pr-3 font-semibold text-slate-400 uppercase tracking-wider">Agent</th>
                <th className="pb-2 pr-3 font-semibold text-slate-400 uppercase tracking-wider">Operation</th>
                <th className="pb-2 pr-3 font-semibold text-slate-400 uppercase tracking-wider">Patient</th>
                <th className="pb-2 pr-3 font-semibold text-slate-400 uppercase tracking-wider">Status</th>
                <th className="pb-2 font-semibold text-slate-400 uppercase tracking-wider"></th>
              </tr>
            </thead>
            <tbody>
              {filteredAudit.map((entry, i) => (
                <>
                  <tr
                    key={i}
                    className={`border-b border-slate-50 transition hover:bg-slate-50 cursor-pointer ${
                      !entry.success ? 'bg-red-50/40' : ''
                    }`}
                    onClick={() => setExpandedRow(expandedRow === i ? null : i)}
                  >
                    <td className="py-2 pr-3 whitespace-nowrap text-slate-500">
                      <div>{formatTime(entry.timestamp)}</div>
                      <div className="text-[10px] text-slate-300">{formatDate(entry.timestamp)}</div>
                    </td>
                    <td className="py-2 pr-3">{agentBadge(entry.agent_id)}</td>
                    <td className="py-2 pr-3 font-mono text-slate-600">{entry.operation}</td>
                    <td className="py-2 pr-3 text-slate-600">{entry.patient_id || '—'}</td>
                    <td className="py-2 pr-3">
                      {entry.success ? (
                        <CheckCircle className="h-3.5 w-3.5 text-emerald-500" />
                      ) : (
                        <XCircle className="h-3.5 w-3.5 text-red-500" />
                      )}
                    </td>
                    <td className="py-2">
                      {expandedRow === i ? (
                        <ChevronUp className="h-3.5 w-3.5 text-slate-400" />
                      ) : (
                        <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
                      )}
                    </td>
                  </tr>
                  {expandedRow === i && (
                    <tr key={`${i}-detail`} className="bg-slate-50/70">
                      <td colSpan={6} className="px-4 py-3">
                        <div className="space-y-1 text-[11px]">
                          <div>
                            <span className="font-semibold text-slate-500">Result: </span>
                            <span className="text-slate-600">{entry.result_summary}</span>
                          </div>
                          {Object.keys(entry.params).length > 0 && (
                            <div>
                              <span className="font-semibold text-slate-500">Params: </span>
                              <code className="rounded bg-white px-1.5 py-0.5 text-[10px] text-slate-500">
                                {JSON.stringify(entry.params)}
                              </code>
                            </div>
                          )}
                          <div>
                            <span className="font-semibold text-slate-500">Timestamp: </span>
                            <span className="text-slate-600">{entry.timestamp}</span>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
              {filteredAudit.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-400">
                    <Clock className="mx-auto mb-2 h-6 w-6 text-slate-300" />
                    {audit.length === 0 ? 'No audit events yet — run a patient pipeline to generate data' : 'No entries match current filters'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
