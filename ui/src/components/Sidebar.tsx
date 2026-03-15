import { useState } from 'react';
import { Search, Stethoscope, Activity, Layers, Plus, Circle, Home, Paperclip, Shield, Compass } from 'lucide-react';
import type { Episode } from '../types';

interface SidebarProps {
  selectedPatientId: string;
  onSelectPatient: (id: string) => void;
  onBackToGrid?: () => void;
  episodes?: Episode[];
  activeEpisodeId?: string | null;
  onNewEpisode?: () => void;
  onActivateEpisode?: (episodeId: string) => void;
  currentView?: string;
  onNavigateObservability?: () => void;
  onNavigateNavigator?: () => void;
}

export function Sidebar({
  selectedPatientId,
  onSelectPatient,
  onBackToGrid,
  episodes = [],
  activeEpisodeId,
  onNewEpisode,
  onActivateEpisode,
  currentView,
  onNavigateObservability,
  onNavigateNavigator,
}: SidebarProps) {
  const [searchInput, setSearchInput] = useState('');

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchInput.trim()) {
      onSelectPatient(searchInput.trim().toUpperCase());
    }
  };

  return (
    <aside className="flex w-72 flex-col border-r border-white/[0.06] bg-surface-1">
      {/* Logo / Brand */}
      <div className="flex items-center gap-3 border-b border-white/[0.06] px-5 py-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 shadow-lg shadow-brand-500/20">
          <Stethoscope className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="text-lg font-bold text-white">MedNexus</h1>
          <p className="text-xs text-slate-500">Command Center</p>
        </div>
      </div>

      {/* Patient Search */}
      <div className="p-4">
        {selectedPatientId && onBackToGrid && (
          <button
            type="button"
            onClick={onBackToGrid}
            className="mb-3 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-brand-400 transition hover:bg-brand-500/10"
          >
            <Home className="h-3.5 w-3.5" /> Back to Patient Grid
          </button>
        )}
        <form onSubmit={handleSearch} className="relative">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search Patient ID..."
              className="input-glass pl-10"
            />
          </div>
        </form>

        {selectedPatientId && (
          <div className="mt-4 card-hover cursor-pointer">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-500/15">
                <Activity className="h-4 w-4 text-brand-400" />
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-200">{selectedPatientId}</p>
                <p className="text-xs text-slate-500">Active patient</p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Episode list */}
      {selectedPatientId && episodes.length > 0 && (
        <div className="flex-1 overflow-y-auto border-t border-white/[0.06] px-4 py-3">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Layers className="h-3.5 w-3.5 text-slate-500" />
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Episodes
              </span>
            </div>
            {onNewEpisode && (
              <button
                type="button"
                onClick={onNewEpisode}
                className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-brand-400 transition hover:bg-brand-500/10"
                title="Create new episode"
              >
                <Plus className="h-3 w-3" /> New
              </button>
            )}
          </div>

          <div className="space-y-1">
            {[...episodes].reverse().map((ep) => {
              const isActive = ep.episode_id === activeEpisodeId;
              const date = new Date(ep.created_at).toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
              });
              return (
                <button
                  key={ep.episode_id}
                  type="button"
                  onClick={() => onActivateEpisode?.(ep.episode_id)}
                  className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left transition ${
                    isActive
                      ? 'bg-brand-500/10 ring-1 ring-brand-500/25'
                      : 'hover:bg-white/5'
                  }`}
                >
                  <Circle
                    className={`h-2 w-2 shrink-0 ${
                      isActive ? 'fill-brand-400 text-brand-400' : 'text-slate-600'
                    }`}
                  />
                  <div className="min-w-0 flex-1">
                    <p className={`text-xs font-medium truncate ${isActive ? 'text-brand-300' : 'text-slate-400'}`}>
                      {ep.label}
                    </p>
                    <p className="text-[10px] text-slate-600">
                      {date} · {ep.findings.length} findings
                    </p>
                    {ep.ingested_files && ep.ingested_files.length > 0 && (
                      <div className="mt-1 space-y-0.5">
                        {ep.ingested_files.map((uri) => {
                          const name = uri.split('/').pop() ?? uri;
                          return (
                            <div key={uri} className="flex items-center gap-1 text-[10px] text-slate-600 truncate">
                              <Paperclip className="h-2.5 w-2.5 shrink-0" />
                              <span className="truncate">{name}</span>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Observability + Status */}
      <div className="mt-auto border-t border-white/[0.06] p-4 space-y-3">
        {onNavigateNavigator && (
          <button
            type="button"
            onClick={onNavigateNavigator}
            className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-semibold transition ${
              currentView === 'navigator'
                ? 'bg-white/10 text-white shadow-sm'
                : 'bg-white/5 text-slate-400 hover:bg-white/10 hover:text-slate-200'
            }`}
          >
            <Compass className="h-4 w-4" /> Clinical Navigator
          </button>
        )}
        {onNavigateObservability && (
          <button
            type="button"
            onClick={onNavigateObservability}
            className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-semibold transition ${
              currentView === 'observability'
                ? 'bg-gradient-to-r from-brand-600 to-brand-500 text-white shadow-lg shadow-brand-500/20'
                : 'bg-brand-500/10 text-brand-400 hover:bg-brand-500/20'
            }`}
          >
            <Shield className="h-4 w-4" /> Observability
          </button>
        )}
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <div className="h-2 w-2 rounded-full bg-medical-green animate-pulse shadow-lg shadow-emerald-500/30" />
          <span>System Online</span>
        </div>
      </div>
    </aside>
  );
}
