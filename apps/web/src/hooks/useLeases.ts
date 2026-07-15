import { useState, useCallback, useEffect, useRef } from 'react';
import { listLeases } from '@/lib/api';

export interface LeaseSummary {
  id: string;
  name: string;
}

/**
 * Fetches the real lease list from the API. Used anywhere a lease picker
 * needs live IDs/names instead of a hardcoded mock list (see PR #6 review
 * finding: compare page previously used `[{id:'1', ...}]`, which drifts
 * from real backend IDs).
 */
export function useLeases() {
  const [leases, setLeases] = useState<LeaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const isMountedRef = useRef(true);

  // Single shared implementation for both the mount-time fetch and manual
  // `refetch()` calls, guarded so a response that resolves after unmount
  // can't call setState on an unmounted component.
  const fetchLeases = useCallback(async () => {
    if (!isMountedRef.current) return;

    setLoading(true);
    setError(null);

    try {
      const response = await listLeases();

      if (!isMountedRef.current) return;

      if (response.error) {
        setError(response.error.detail);
        return;
      }

      if (response.data) {
        setLeases(response.data);
      }
    } catch (err) {
      if (!isMountedRef.current) return;
      setError(err instanceof Error ? err.message : 'Failed to fetch leases');
    } finally {
      if (isMountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    // Fetching from the API is the "sync with an external system" case
    // useEffect exists for — the mounted guard inside fetchLeases prevents
    // the cascading-render risk this lint rule is otherwise guarding against.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchLeases();

    return () => {
      isMountedRef.current = false;
    };
  }, [fetchLeases]);

  return { leases, loading, error, refetch: fetchLeases };
}
