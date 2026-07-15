import { useState, useCallback } from 'react';
import { compareLeases } from '@/lib/api';
import type { CompareResponse } from '@leasora/shared-types';

export type { CompareResponse };
export type ComparisonResult = CompareResponse;

/**
 * Submits a comparison request. The shared `CompareResponse` type from
 * `@leasora/shared-types` is reused so this hook can't drift from the
 * backend's response shape.
 */
export function useCompare() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CompareResponse | null>(null);

  const compare = useCallback(async (leaseIds: string[]) => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await compareLeases(leaseIds);

      if (response.error) {
        setError(response.error.detail);
        return;
      }

      if (response.data) {
        setResult(response.data);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to compare leases');
    } finally {
      setLoading(false);
    }
  }, []);

  return { compare, loading, error, result };
}