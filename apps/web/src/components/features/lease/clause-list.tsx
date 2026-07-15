'use client';

import { useState } from 'react';
import { ChevronDown, FileSearch, Loader2 } from 'lucide-react';
import { Badge, Card, EmptyState } from '@/components/ui';
import { useLeaseChunks } from '@/hooks/useLeaseChunks';
import { cn } from '@/lib/utils';

/** Human-readable label for a heuristically-assigned clause type. */
function formatClauseType(clauseType: string): string {
  return clauseType
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

const EXCERPT_LENGTH = 180;

interface ClauseListProps {
  leaseId: string;
}

/**
 * Client-side clause browser for the lease detail page. Fetches indexed
 * chunks via `useLeaseChunks` and renders them as an expandable list with a
 * clause-type badge, page number, and truncated excerpt (full text on
 * expand). Replaces the previous "planned for future release" note.
 */
export function ClauseList({ leaseId }: ClauseListProps) {
  const { chunks, loading, error } = useLeaseChunks(leaseId);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (loading) {
    return (
      <Card>
        <div className="flex items-center justify-center py-8">
          <Loader2 size={24} className="animate-spin text-brand-400" aria-label="Loading clauses" />
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <p className="text-sm text-danger">{error}</p>
      </Card>
    );
  }

  if (chunks.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={<FileSearch size={24} strokeWidth={1.75} />}
          heading="No clauses indexed yet"
          description="This lease doesn't have any indexed clauses to browse."
        />
      </Card>
    );
  }

  return (
    <Card className="p-0">
      <ul className="divide-y divide-border-subtle">
        {chunks.map((chunk) => {
          const isExpanded = expandedId === chunk.id;
          const needsTruncation = chunk.text.length > EXCERPT_LENGTH;
          const displayText =
            isExpanded || !needsTruncation ? chunk.text : `${chunk.text.slice(0, EXCERPT_LENGTH)}…`;

          return (
            <li key={chunk.id}>
              <button
                type="button"
                onClick={() => setExpandedId(isExpanded ? null : chunk.id)}
                aria-expanded={isExpanded}
                disabled={!needsTruncation}
                className={cn(
                  'flex w-full items-start justify-between gap-4 px-6 py-4 text-left',
                  needsTruncation && 'hover:bg-surface-overlay focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-inset'
                )}
              >
                <div className="min-w-0 flex-1">
                  <div className="mb-1.5 flex items-center gap-2">
                    <Badge status="info" size="sm">
                      {formatClauseType(chunk.clause_type)}
                    </Badge>
                    {chunk.page != null && (
                      <span className="text-xs text-ink-muted">Page {chunk.page}</span>
                    )}
                  </div>
                  <p className="text-sm text-ink-secondary">{displayText}</p>
                </div>
                {needsTruncation && (
                  <ChevronDown
                    size={18}
                    strokeWidth={1.75}
                    className={cn(
                      'mt-1 shrink-0 text-ink-muted transition-transform',
                      isExpanded && 'rotate-180'
                    )}
                    aria-hidden="true"
                  />
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
