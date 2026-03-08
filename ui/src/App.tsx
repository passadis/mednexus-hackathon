import { useState, useCallback } from 'react';
import { Sidebar } from './components/Sidebar';
import { ClinicalWorkspace } from './components/ClinicalWorkspace';
import { AgentChatter } from './components/AgentChatter';
import { ChatPanel } from './components/ChatPanel';
import { PatientGrid } from './components/PatientGrid';
import { PatientPortal } from './components/PatientPortal';
import { useWebSocket } from './hooks/useWebSocket';
import { usePatientContext } from './hooks/usePatientContext';

export function App() {
  // ── Portal route: /portal?token=xxx ─────────────────────
  const params = new URLSearchParams(window.location.search);
  const portalToken = window.location.pathname === '/portal' ? params.get('token') : null;

  if (portalToken) {
    return <PatientPortal token={portalToken} />;
  }

  // ── Doctor app ──────────────────────────────────────────
  return <DoctorApp />;
}

function DoctorApp() {
  const [selectedPatientId, setSelectedPatientId] = useState<string>('');
  const { messages } = useWebSocket();
  const { context, loading, error, refresh } = usePatientContext(selectedPatientId);

  const handleSelectPatient = useCallback((id: string) => {
    setSelectedPatientId(id);
  }, []);

  const handleNewEpisode = useCallback(async () => {
    if (!context) return;
    try {
      const res = await fetch(`/api/patients/${context.patient.patient_id}/episodes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (res.ok) refresh();
    } catch {
      console.error('Failed to create episode');
    }
  }, [context, refresh]);

  const handleActivateEpisode = useCallback(async (episodeId: string) => {
    if (!context) return;
    try {
      await fetch(
        `/api/patients/${context.patient.patient_id}/episodes/${episodeId}/activate`,
        { method: 'PATCH' },
      );
      refresh();
    } catch {
      console.error('Failed to activate episode');
    }
  }, [context, refresh]);

  const handleBackToGrid = useCallback(() => {
    setSelectedPatientId('');
  }, []);

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar: Patient Search + Episodes */}
      <Sidebar
        selectedPatientId={selectedPatientId}
        onSelectPatient={handleSelectPatient}
        onBackToGrid={handleBackToGrid}
        episodes={context?.episodes ?? []}
        activeEpisodeId={context?.active_episode_id ?? null}
        onNewEpisode={handleNewEpisode}
        onActivateEpisode={handleActivateEpisode}
      />

      {/* Main content: Grid (home) or Workspace (patient detail) */}
      <main className="flex flex-1 overflow-hidden">
        {selectedPatientId ? (
          <ClinicalWorkspace
            context={context}
            loading={loading}
            error={error}
            onRefresh={refresh}
          />
        ) : (
          <PatientGrid onSelectPatient={handleSelectPatient} />
        )}

        {/* Right panel: Agent Chatter (only in workspace view) */}
        {selectedPatientId && <AgentChatter messages={messages} />}
      </main>

      {/* Floating Doctor Chat */}
      <ChatPanel onNavigatePatient={handleSelectPatient} />
    </div>
  );
}
