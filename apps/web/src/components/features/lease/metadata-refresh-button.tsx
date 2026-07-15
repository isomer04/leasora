'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { RefreshCw } from 'lucide-react';
import { refreshLeaseMetadata } from '@/lib/api';

export function MetadataRefreshButton({ leaseId }: { leaseId: string }) {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);
  const [isExhausted, setIsExhausted] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function refreshMetadata() {
    setIsLoading(true);
    setMessage(null);
    try {
      const { data, error } = await refreshLeaseMetadata(leaseId);
      if (error) throw new Error(error.detail);
      if (!data) throw new Error('Metadata extraction returned no response.');

      if (data.status === 'updated') {
        const count = data.updated_fields.length;
        setMessage(`${count} metadata ${count === 1 ? 'field' : 'fields'} updated.`);
        router.refresh();
      } else {
        setIsExhausted(true);
        setMessage('No additional metadata was found in this document.');
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Metadata extraction failed.');
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={refreshMetadata}
        disabled={isLoading || isExhausted}
        className="inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm font-medium text-ink-primary hover:bg-surface-2 disabled:cursor-wait disabled:opacity-60"
      >
        <RefreshCw size={16} className={isLoading ? 'animate-spin' : ''} aria-hidden="true" />
        {isLoading ? 'Extracting…' : isExhausted ? 'No more metadata' : 'Retry extraction'}
      </button>
      {message && (
        <p
          role="status"
          aria-live="polite"
          className="max-w-64 text-right text-xs text-ink-secondary"
        >
          {message}
        </p>
      )}
    </div>
  );
}
