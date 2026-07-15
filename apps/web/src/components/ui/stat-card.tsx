import React from 'react';
import { cn } from '@/lib/utils';
import { Card } from './card';

export type StatCardTrend = 'success' | 'warning' | 'danger' | 'neutral';

export interface StatCardProps extends React.HTMLAttributes<HTMLDivElement> {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  valueClassName?: string;
  trend?: string;
  trendTone?: StatCardTrend;
}

function trendToneClasses(tone: StatCardTrend): string {
  switch (tone) {
    case 'success':
      return 'text-success';
    case 'warning':
      return 'text-warning';
    case 'danger':
      return 'text-danger';
    case 'neutral':
      return 'text-ink-muted';
  }
}

/**
 * Icon chip + label + big tabular number + optional trend/status line,
 * used for dashboard-style stat grids.
 */
export function StatCard({
  icon,
  label,
  value,
  valueClassName,
  trend,
  trendTone = 'neutral',
  className,
  ...props
}: StatCardProps) {
  return (
    <Card className={className} {...props}>
      <div className="flex items-center gap-3">
        <div
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-500/10 text-brand-400"
          aria-hidden="true"
        >
          {icon}
        </div>
        <p className="text-sm text-ink-secondary">{label}</p>
      </div>
      <p className={cn('font-tabular mt-4 text-3xl font-bold text-ink-primary', valueClassName)}>
        {value}
      </p>
      {trend && <p className={cn('mt-1 text-sm', trendToneClasses(trendTone))}>{trend}</p>}
    </Card>
  );
}
