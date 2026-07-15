import React from 'react';
import { cn } from '@/lib/utils';

export type SkeletonVariant = 'text' | 'circle' | 'card';

export interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: SkeletonVariant;
  /** Only used by the `circle` variant, in px. Defaults to 40. */
  size?: number;
}

/**
 * Loading placeholder. Uses Tailwind's `animate-pulse` (a plain CSS
 * animation) which is already governed by the global reduced-motion
 * override in globals.css, so no extra JS gating is needed here.
 */
export function Skeleton({ variant = 'text', size = 40, className, style, ...props }: SkeletonProps) {
  if (variant === 'circle') {
    return (
      <div
        className={cn('animate-pulse rounded-full bg-surface-overlay', className)}
        style={{ width: size, height: size, ...style }}
        {...props}
      />
    );
  }

  if (variant === 'card') {
    return (
      <div
        className={cn('animate-pulse rounded-lg bg-surface-overlay', className)}
        style={{ height: size * 3, ...style }}
        {...props}
      />
    );
  }

  return <div className={cn('h-4 animate-pulse rounded bg-surface-overlay', className)} style={style} {...props} />;
}
