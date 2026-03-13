import { useCallback, useEffect, useRef, useState } from 'react';
import type { PatientContext } from '../types';

/** Status values that indicate agents are still processing. */
const PROCESSING_STATUSES = new Set([
  'intake',
  'waiting_for_radiology',
  'waiting_for_history',
  'waiting_for_transcript',
  'cross_modality_check',
]);

/**
 * Hook to fetch and cache a patient's Clinical Context from the API.
 *
 * Key design: context is NEVER set to null except when switching to a
 * genuinely different patient.  Background WS-triggered refreshes
 * silently swap data in without touching `loading`.
 *
 * A polling safety-net auto-refreshes every 3 s while agents are
 * actively processing, so the UI stays up-to-date even if a WS event
 * is lost or delayed.
 */
export function usePatientContext(patientId: string) {
  const [context, setContext] = useState<PatientContext | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Track previous patient so we only blank the screen on real switches.
  const prevId = useRef(patientId);

  const fetchContext = useCallback(async () => {
    if (!patientId) {
      setContext(null);
      setLoading(false);
      return;
    }

    try {
      const res = await fetch(`/api/patients/${encodeURIComponent(patientId)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: PatientContext = await res.json();
      setContext(data);
      setError(null);
    } catch (err) {
      // On error, preserve whatever is already on screen
      setContext((prev) => {
        if (prev === null) {
          setError(err instanceof Error ? err.message : 'Unknown error');
        }
        return prev;
      });
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  // ── Initial load / patient switch ────────────────────────
  useEffect(() => {
    if (patientId !== prevId.current) {
      prevId.current = patientId;
      if (patientId) {
        setLoading(true);
        setContext(null);
        setError(null);
      } else {
        setContext(null);
        setLoading(false);
      }
    }
    fetchContext();
  }, [fetchContext]);

  // ── Polling safety-net while agents are processing ───────
  // Derive the active episode status string so the effect only
  // re-fires when the status actually changes.
  const activeEpStatus = context?.episodes?.find(
    (e) => e.episode_id === context.active_episode_id,
  )?.status;
  const normalizedStatus = activeEpStatus?.toLowerCase();
  const isProcessing = normalizedStatus ? PROCESSING_STATUSES.has(normalizedStatus) : false;

  useEffect(() => {
    if (!isProcessing) return;
    const timer = setInterval(fetchContext, 3000);
    return () => clearInterval(timer);
  }, [isProcessing, fetchContext]);

  return { context, loading, error, refresh: fetchContext };
}
