import { useState, useCallback, useEffect, useRef } from 'react';
import { getLeaseChunks, type ChunkResponse } from '@/lib/api';

export type { ChunkResponse };

/**
 * Fetches a lease's indexed chunks (clauses) client-side, following the
 * same mounted-guard pattern as `useLeases`/`useLease` so a response that
 * resolves after unmount can't call setState on an unmounted component.
 */
export function useLeaseChunks(leaseId: string) {
  const [chunks, setChunks] = useState<ChunkResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const isMountedRef = useRef(true);

  const fetchChunks = useCallback(async () => {
    if (!isMountedRef.current) return;

    setLoading(true);
    setError(null);

    try {
      const response = await getLeaseChunks(leaseId);

      if (!isMountedRef.current) return;

      if (response.error) {
        setError(response.error.detail);
        return;
      }

      if (response.data) {
        setChunks(response.data);
      }
    } catch (err) {
      if (!isMountedRef.current) return;
      setError(err instanceof Error ? err.message : 'Failed to fetch clauses');
    } finally {
      if (isMountedRef.current) setLoading(false);
    }
  }, [leaseId]);

  useEffect(() => {
    isMountedRef.current = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchChunks();

    return () => {
      isMountedRef.current = false;
    };
  }, [fetchChunks]);

  return { chunks, loading, error, refetch: fetchChunks };
}
