'use client';

import React from 'react';
import { cn } from '@/lib/utils';

export type AvatarSize = 'sm' | 'md' | 'lg';

export interface AvatarProps extends React.HTMLAttributes<HTMLSpanElement> {
  src?: string;
  name?: string;
  size?: AvatarSize;
}

const sizeClasses: Record<AvatarSize, string> = {
  sm: 'h-6 w-6 text-[9px]',
  md: 'h-9 w-9 text-sm',
  lg: 'h-12 w-12 text-base',
};

function getInitials(name?: string): string {
  if (!name) return '';
  const parts = name.trim().split(/\s+/);
  const first = parts[0]?.[0] ?? '';
  const last = parts.length > 1 ? parts[parts.length - 1]?.[0] ?? '' : '';
  return (first + last).toUpperCase();
}

/**
 * Circular avatar. Falls back to initials derived from `name` when `src`
 * is absent or fails to load.
 */
export function Avatar({ src, name, size = 'md', className, ...props }: AvatarProps) {
  const [imgFailed, setImgFailed] = React.useState(false);
  const [prevSrc, setPrevSrc] = React.useState(src);

  // Reset the failure flag whenever `src` changes so a new URL gets a fresh attempt.
  if (src !== prevSrc) {
    setPrevSrc(src);
    setImgFailed(false);
  }

  const showImage = src && !imgFailed;

  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-brand-700 font-medium text-white',
        sizeClasses[size],
        className
      )}
      role="img"
      aria-label={name ?? 'User avatar'}
      {...props}
    >
      {showImage ? (
        // eslint-disable-next-line @next/next/no-img-element -- avatars are small, dynamic, user-provided URLs
        <img src={src} alt="" onError={() => setImgFailed(true)} className="h-full w-full object-cover" />
      ) : (
        <span aria-hidden="true">{getInitials(name)}</span>
      )}
    </span>
  );
}
