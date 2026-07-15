'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { hoverLift, useSafeReducedMotion } from '@/lib/motion';
import { cn } from '@/lib/utils';

export type CardVariant = 'default' | 'interactive' | 'glass';

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  variant?: CardVariant;
}

function variantClasses(variant: CardVariant): string {
  switch (variant) {
    case 'default':
      return 'bg-surface-elevated border border-border-subtle shadow-elevation-1';
    case 'interactive':
      return 'bg-surface-elevated border border-border-subtle shadow-elevation-1 cursor-pointer';
    case 'glass':
      return 'bg-surface-elevated/60 backdrop-blur-md border border-border-subtle/60 shadow-elevation-2';
  }
}

/**
 * `interactive` gets a hover-lift (translateY + shadow grow) via framer-motion,
 * gated behind `prefers-reduced-motion`. `default`/`glass` render as plain divs
 * (no motion needed) even though this file is a client component — Card is
 * consumed widely enough that splitting into server/client variants isn't
 * worth the added indirection.
 */
export function Card({ children, variant = 'default', className, ...props }: CardProps) {
  const shouldReduceMotion = useSafeReducedMotion();

  const base = cn('rounded-lg p-6', variantClasses(variant), className);

  if (variant === 'interactive' && !shouldReduceMotion) {
    return (
      <motion.div
        className={cn(base, 'hover:shadow-elevation-2')}
        whileHover={hoverLift}
        {...(props as React.ComponentProps<typeof motion.div>)}
      >
        {children}
      </motion.div>
    );
  }

  return (
    <div className={cn(base, variant === 'interactive' && 'hover:shadow-elevation-2')} {...props}>
      {children}
    </div>
  );
}

export function CardHeader({ children, className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('mb-4', className)} {...props}>
      {children}
    </div>
  );
}

export function CardContent({ children, className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={className} {...props}>
      {children}
    </div>
  );
}

export function CardFooter({ children, className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('mt-4 pt-4 border-t border-border-subtle', className)} {...props}>
      {children}
    </div>
  );
}
