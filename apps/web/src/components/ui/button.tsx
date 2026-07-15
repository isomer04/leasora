'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { Loader2 } from 'lucide-react';
import { pressScale, useSafeReducedMotion } from '@/lib/motion';
import { cn } from '@/lib/utils';

export type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';

type MotionConflictingProps =
  | 'onDrag'
  | 'onDragStart'
  | 'onDragEnd'
  | 'onAnimationStart'
  | 'onAnimationEnd'
  | 'onTransitionEnd';

export interface ButtonProps
  extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, MotionConflictingProps> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  isLoading?: boolean;
  iconLeft?: React.ReactNode;
  iconRight?: React.ReactNode;
}

function variantClasses(variant: ButtonVariant): string {
  switch (variant) {
    case 'primary':
      return 'bg-brand-500 text-gray-900 hover:bg-brand-400 active:bg-brand-700 active:text-white';
    case 'secondary':
      return 'bg-surface-overlay text-ink-primary hover:bg-surface-elevated border border-border-subtle';
    case 'outline':
      return 'bg-transparent text-ink-primary border border-border-strong hover:bg-surface-overlay';
    case 'ghost':
      return 'bg-transparent text-ink-primary hover:bg-surface-overlay';
    case 'danger':
      return 'bg-danger-600 text-white hover:bg-danger-700 active:bg-danger-800';
  }
}

function sizeClasses(size: ButtonSize): string {
  switch (size) {
    case 'sm':
      return 'px-3 py-1.5 text-sm gap-1.5';
    case 'md':
      return 'px-4 py-2 text-base gap-2';
    case 'lg':
      return 'px-6 py-3 text-lg gap-2.5';
  }
}

function iconSize(size: ButtonSize): number {
  switch (size) {
    case 'sm':
      return 16;
    case 'md':
      return 18;
    case 'lg':
      return 20;
  }
}

export function Button({
  variant = 'primary',
  size = 'md',
  isLoading = false,
  disabled,
  iconLeft,
  iconRight,
  children,
  className,
  ...props
}: ButtonProps) {
  const shouldReduceMotion = useSafeReducedMotion();
  const isDisabled = disabled || isLoading;

  return (
    <motion.button
      type={props.type ?? 'button'}
      disabled={isDisabled}
      whileTap={!isDisabled && !shouldReduceMotion ? pressScale : undefined}
      className={cn(
        'inline-flex items-center justify-center rounded-md font-medium',
        'transition-colors duration-150',
        isLoading
          ? 'cursor-wait'
          : 'cursor-pointer disabled:cursor-not-allowed disabled:opacity-50',
        variantClasses(variant),
        sizeClasses(size),
        className
      )}
      {...props}
    >
      {isLoading ? (
        <Loader2 className="animate-spin" size={iconSize(size)} strokeWidth={1.75} aria-hidden="true" />
      ) : (
        iconLeft && (
          <span className="inline-flex shrink-0" aria-hidden="true">
            {iconLeft}
          </span>
        )
      )}
      {children}
      {!isLoading && iconRight && (
        <span className="inline-flex shrink-0" aria-hidden="true">
          {iconRight}
        </span>
      )}
    </motion.button>
  );
}
