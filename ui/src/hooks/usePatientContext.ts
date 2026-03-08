import { useCallback, useEffect, useState } from 'react';
import type { PatientContext } from '../types';

/**
 * Hook to fetch and cache a patient's Clinical Context from the API.
 */
export function usePatientContext(patientId: string) {
  const [context, setContext] = useState<PatientContext | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchContext = useCallback(async () => {
    if (!patientId) {
      setContext(null);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`/api/patients/${encodeURIComponent(patientId)}`);
      if (res.status === 404) {
        setContext(null);
        setError(null);
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: PatientContext = await res.json();
      setContext(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      setContext(null);
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  useEffect(() => {
    fetchContext();
  }, [fetchContext]);

  return { context, loading, error, refresh: fetchContext };
}
