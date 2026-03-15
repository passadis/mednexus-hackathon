// ── MedNexus UI Type Definitions ────────────────────────────

export interface PatientDemographics {
  patient_id: string;
  name: string;
  date_of_birth: string;
  gender: string;
  mrn: string;
}

export interface ClinicalFinding {
  finding_id: string;
  modality: string;
  source_agent: string;
  summary: string;
  confidence: number;
  details: Record<string, unknown>;
  timestamp: string;
}

export interface Discrepancy {
  finding_a_id: string;
  finding_b_id: string;
  description: string;
  severity: string;
}

// Whisper transcript segment with timestamps
export interface TranscriptSegment {
  start: number;  // seconds
  end: number;
  text: string;
}

export interface SynthesisReport {
  report_id: string;
  summary: string;
  cross_modality_notes: string;
  discrepancies: Discrepancy[];
  recommendations: string[];
  generated_by: string;
  generated_at: string;
}

export interface AgentActivity {
  agent: string;
  action: string;
  detail: string;
  timestamp: string;
}

// ── Episode ─────────────────────────────────────────────────

export interface Episode {
  episode_id: string;
  label: string;
  status: string;
  findings: ClinicalFinding[];
  ingested_files: string[];
  synthesis: SynthesisReport | null;
  approved_by: string | null;
  approved_at: string | null;
  activity_log: AgentActivity[];
  created_at: string;
  updated_at: string;
}

// ── Patient Context ─────────────────────────────────────────

export interface PatientContext {
  id: string;
  partition_key: string;
  patient: PatientDemographics;
  status: string;
  // Episode-based architecture
  episodes: Episode[];
  active_episode_id: string | null;
  cross_episode_summary: string;
  // Flat legacy fields (backward-compat)
  findings: ClinicalFinding[];
  ingested_files: string[];
  synthesis: SynthesisReport | null;
  activity_log: AgentActivity[];
  // Phase 3 – Human-in-the-Loop approval
  approved_by: string | null;
  approved_at: string | null;
  approval_notes: string;
  created_at: string;
  updated_at: string;
}

export interface A2AMessage {
  message_id: string;
  type: string;
  sender: string;
  receiver: string;
  patient_id: string;
  payload: Record<string, unknown>;
  timestamp: string;
  correlation_id: string;
}

// Agent roles used for avatar coloring
export const AGENT_COLORS: Record<string, { bg: string; text: string; icon: string }> = {
  orchestrator: { bg: 'bg-brand-500/20', text: 'text-brand-400', icon: '🎯' },
  clinical_sorter: { bg: 'bg-amber-500/20', text: 'text-amber-400', icon: '📋' },
  vision_specialist: { bg: 'bg-purple-500/20', text: 'text-purple-400', icon: '👁️' },
  patient_historian: { bg: 'bg-emerald-500/20', text: 'text-emerald-400', icon: '📚' },
  diagnostic_synthesis: { bg: 'bg-rose-500/20', text: 'text-rose-400', icon: '🧬' },
};

// ── Portal Types ────────────────────────────────────────────

export interface PortalContext {
  patient_name: string;
  episode_label: string;
  episode_date: string;
  status: string;
  plain_summary: string;
  recommendations: string[];
  finding_count: number;
  approved_by: string | null;
  approved_at: string | null;
}

export interface PortalChatMessage {
  role: 'user' | 'assistant';
  content: string;
}
