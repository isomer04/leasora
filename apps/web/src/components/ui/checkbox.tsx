'use client';

import React, { useId } from 'react';
import * as CheckboxPrimitive from '@radix-ui/react-checkbox';
import type { CheckedState } from '@radix-ui/react-checkbox';
import { motion, AnimatePresence } from 'framer-motion';
import { Check } from 'lucide-react';
import { useSafeReducedMotion } from '@/lib/motion';
import { cn } from '@/lib/utils';

export interface CheckboxProps
  extends Omit<React.ComponentPropsWithoutRef<typeof CheckboxPrimitive.Root>, 'asChild'> {
  label?: React.ReactNode;
}

/**
 * Built on `@radix-ui/react-checkbox` for full keyboard operability.
 * The check mark scale-animates in, gated behind `prefers-reduced-motion`.
 */
export const Checkbox = React.forwardRef<React.ElementRef<typeof CheckboxPrimitive.Root>, CheckboxProps>(
  function Checkbox({ label, className, id: providedId, checked, defaultChecked, onCheckedChange, ...props }, ref) {
    const generatedId = useId();
    const checkboxId = providedId || generatedId;
    const shouldReduceMotion = useSafeReducedMotion();

    // Track the real checked state ourselves so the check mark renders
    // correctly for controlled, uncontrolled, and indeterminate states.
    const isControlled = checked !== undefined;
    const [internalChecked, setInternalChecked] = React.useState<CheckedState>(
      defaultChecked ?? false
    );
    const checkedState = isControlled ? checked : internalChecked;

    const checkbox = (
      <CheckboxPrimitive.Root
        ref={ref}
        id={checkboxId}
        checked={checked}
        defaultChecked={defaultChecked}
        onCheckedChange={(next) => {
          if (!isControlled) {
            setInternalChecked(next);
          }
          onCheckedChange?.(next);
        }}
        className={cn(
          'flex h-5 w-5 shrink-0 items-center justify-center rounded-sm border border-border-strong bg-surface-surface',
          'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400',
          'data-[state=checked]:border-brand-700 data-[state=checked]:bg-brand-700',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          className
        )}
        {...props}
      >
        <CheckboxPrimitive.Indicator forceMount asChild>
          <AnimatePresence>
            {checkedState === true && (
              <motion.span
                initial={shouldReduceMotion ? undefined : { scale: 0, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={shouldReduceMotion ? undefined : { scale: 0, opacity: 0 }}
                transition={{ duration: 0.12 }}
                className="flex items-center justify-center text-white"
              >
                <Check size={14} strokeWidth={2.5} />
              </motion.span>
            )}
          </AnimatePresence>
        </CheckboxPrimitive.Indicator>
      </CheckboxPrimitive.Root>
    );

    if (!label) return checkbox;

    return (
      <label htmlFor={checkboxId} className="inline-flex items-center gap-2 text-sm text-ink-primary">
        {checkbox}
        {label}
      </label>
    );
  }
);
