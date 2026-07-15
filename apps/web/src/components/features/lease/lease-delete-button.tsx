'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Trash2 } from 'lucide-react';
import { Button } from '@/components/ui';
import { deleteLease } from '@/lib/api';

interface LeaseDeleteButtonProps {
  leaseId: string;
  leaseName: string;
  compact?: boolean;
  onDeleted?: (leaseId: string) => void;
}

export function LeaseDeleteButton({ leaseId, leaseName, compact = false, onDeleted }: LeaseDeleteButtonProps) {
  const router = useRouter();
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState('');

  async function handleDelete() {
    const confirmed = window.confirm(
      `Delete “${leaseName}”? This permanently removes the PDF, extracted data, and cached answers.`
    );
    if (!confirmed) return;

    setIsDeleting(true);
    setError('');
    try {
      const { data, error: apiError } = await deleteLease(leaseId);
      if (apiError) throw new Error(apiError.detail);
      if (!data?.lease_record_removed || data.errors.length > 0) {
        throw new Error('The lease could not be fully deleted. Please try again.');
      }
      if (onDeleted) onDeleted(leaseId);
      else {
        router.replace('/leases');
        router.refresh();
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to delete lease.');
    } finally {
      setIsDeleting(false);
    }
  }

  return (
    <div className={compact ? 'inline-flex flex-col items-end gap-1' : 'flex flex-col items-start gap-1'}>
      <Button variant="danger" size="sm" isLoading={isDeleting} onClick={handleDelete}
        iconLeft={<Trash2 size={16} strokeWidth={1.75} />} aria-label={`Delete ${leaseName}`}
        className={compact ? 'h-8 w-8 rounded-full p-0' : undefined}>
        {compact ? <span className="sr-only">Delete {leaseName}</span> : isDeleting ? 'Deleting…' : 'Delete lease'}
      </Button>
      {error && <p role="alert" className="max-w-64 text-xs text-danger">{error}</p>}
    </div>
  );
}
