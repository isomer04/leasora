'use client';

import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  className?: string;
}

/**
 * Builds a compact page list with ellipses: always shows first, last,
 * current, and one neighbor on each side of current.
 */
function getPageList(currentPage: number, totalPages: number): Array<number | 'ellipsis'> {
  const pages = new Set<number>([1, totalPages, currentPage, currentPage - 1, currentPage + 1]);
  const sorted = Array.from(pages)
    .filter((p) => p >= 1 && p <= totalPages)
    .sort((a, b) => a - b);

  const result: Array<number | 'ellipsis'> = [];
  let prev = 0;
  for (const page of sorted) {
    if (prev && page - prev > 1) {
      result.push('ellipsis');
    }
    result.push(page);
    prev = page;
  }
  return result;
}

export function Pagination({ currentPage, totalPages, onPageChange, className }: PaginationProps) {
  if (totalPages <= 1) return null;

  const pages = getPageList(currentPage, totalPages);
  const isFirst = currentPage <= 1;
  const isLast = currentPage >= totalPages;

  return (
    <nav aria-label="Pagination" className={cn('flex items-center gap-1', className)}>
      <button
        type="button"
        aria-label="Previous page"
        disabled={isFirst}
        onClick={() => onPageChange(currentPage - 1)}
        className={cn(
          'flex h-8 w-8 items-center justify-center rounded-full text-ink-secondary',
          'hover:bg-surface-overlay focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400',
          'disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent'
        )}
      >
        <ChevronLeft size={16} strokeWidth={1.75} />
      </button>

      {pages.map((page, idx) =>
        page === 'ellipsis' ? (
          <span key={`ellipsis-${idx}`} className="px-1.5 text-sm text-ink-muted" aria-hidden="true">
            …
          </span>
        ) : (
          <button
            key={page}
            type="button"
            aria-label={`Go to page ${page}`}
            aria-current={page === currentPage ? 'page' : undefined}
            onClick={() => onPageChange(page)}
            className={cn(
              'flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400',
              page === currentPage
                ? 'bg-brand-500 !text-black'
                : 'text-ink-secondary hover:bg-surface-overlay'
            )}
          >
            {page}
          </button>
        )
      )}

      <button
        type="button"
        aria-label="Next page"
        disabled={isLast}
        onClick={() => onPageChange(currentPage + 1)}
        className={cn(
          'flex h-8 w-8 items-center justify-center rounded-full text-ink-secondary',
          'hover:bg-surface-overlay focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400',
          'disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent'
        )}
      >
        <ChevronRight size={16} strokeWidth={1.75} />
      </button>
    </nav>
  );
}
