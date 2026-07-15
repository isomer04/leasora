import React from 'react';
import { cn } from '@/lib/utils';

export interface EmptyStateProps extends React.HTMLAttributes<HTMLDivElement> {
  icon: React.ReactNode;
  heading: string;
  description?: string;
  action?: React.ReactNode;
}

/**
 * Icon + heading + copy + CTA slot, used across Leases/Compare/Dashboard
 * whenever a list/table has no data.
 */
export function EmptyState({ icon, heading, description, action, className, ...props }: EmptyStateProps) {
  return (
    <div
      className={cn('flex flex-col items-center justify-center rounded-lg px-6 py-12 text-center', className)}
      {...props}
    >
      <div
        className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-brand-500/10 text-brand-400"
        aria-hidden="true"
      >
        {icon}
      </div>
      <h3 className="text-lg font-semibold text-ink-primary">{heading}</h3>
      {description && <p className="mt-1 max-w-sm text-sm text-ink-secondary">{description}</p>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
