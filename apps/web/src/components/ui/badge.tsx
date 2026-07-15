import React from 'react';
import { cn } from '@/lib/utils';

export type BadgeStatus = 'active' | 'expired' | 'pending' | 'success' | 'warning' | 'danger' | 'info' | 'neutral';
export type BadgeSize = 'sm' | 'md';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  status?: BadgeStatus;
  size?: BadgeSize;
  children: React.ReactNode;
}

const statusClasses: Record<BadgeStatus, { pill: string; dot: string }> = {
  active: { pill: 'bg-success/10 text-success', dot: 'bg-success' },
  success: { pill: 'bg-success/10 text-success', dot: 'bg-success' },
  expired: { pill: 'bg-ink-muted/10 text-ink-muted', dot: 'bg-ink-muted' },
  neutral: { pill: 'bg-ink-muted/10 text-ink-muted', dot: 'bg-ink-muted' },
  pending: { pill: 'bg-warning/10 text-warning', dot: 'bg-warning' },
  warning: { pill: 'bg-warning/10 text-warning', dot: 'bg-warning' },
  danger: { pill: 'bg-danger/10 text-danger', dot: 'bg-danger' },
  info: { pill: 'bg-info/10 text-info', dot: 'bg-info' },
};

const sizeClasses: Record<BadgeSize, string> = {
  sm: 'text-xs px-2 py-0.5 gap-1',
  md: 'text-sm px-2.5 py-1 gap-1.5',
};

/**
 * Status pill with a semantic color dot, used for Active/Expired/Pending
 * lease states and similar inline status labels.
 */
export function Badge({ status = 'neutral', size = 'md', children, className, ...props }: BadgeProps) {
  const { pill, dot } = statusClasses[status];

  return (
    <span
      className={cn('inline-flex items-center rounded-full font-medium', pill, sizeClasses[size], className)}
      {...props}
    >
      <span className={cn('h-1.5 w-1.5 rounded-full', dot)} aria-hidden="true" />
      {children}
    </span>
  );
}
