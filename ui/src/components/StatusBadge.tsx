interface StatusBadgeProps {
  status: string;
}

const STATUS_STYLES: Record<string, { class: string; label: string }> = {
  intake: { class: 'badge-blue', label: 'Intake' },
  waiting_for_radiology_report: { class: 'badge-amber', label: 'Awaiting Radiology' },
  waiting_for_patient_history: { class: 'badge-amber', label: 'Awaiting History' },
  waiting_for_audio_transcript: { class: 'badge-amber', label: 'Awaiting Transcript' },
  cross_modality_check: { class: 'badge-purple', label: 'Cross-Modality Check' },
  synthesis_complete: { class: 'badge-green', label: 'Synthesis Complete' },
  review_required: { class: 'badge-red', label: 'Review Required' },
  finalized: { class: 'badge-green', label: 'Finalized' },
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const style = STATUS_STYLES[status] || { class: 'badge-blue', label: status };
  return <span className={style.class}>{style.label}</span>;
}
