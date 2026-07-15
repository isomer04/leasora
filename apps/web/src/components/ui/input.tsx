import React, { useId } from 'react';
import { cn } from '@/lib/utils';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  icon?: React.ReactNode;
}

export function Input({
  label,
  error,
  helperText,
  icon,
  className,
  id: providedId,
  ...props
}: InputProps) {
  const generatedId = useId();
  const inputId = providedId || generatedId;
  const errorId = error ? `${inputId}-error` : undefined;
  const helperId = helperText ? `${inputId}-helper` : undefined;

  return (
    <div className="w-full">
      {label && (
        <label htmlFor={inputId} className="mb-1 block text-sm font-medium text-ink-secondary">
          {label}
        </label>
      )}
      <div className="relative">
        {icon && (
          <span className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-ink-muted">
            {icon}
          </span>
        )}
        <input
          id={inputId}
          aria-invalid={error ? 'true' : 'false'}
          aria-describedby={error ? errorId : helperId}
          className={cn(
            'w-full rounded-md border bg-surface-surface px-3 py-2 text-ink-primary',
            'border-border-subtle placeholder:text-ink-muted',
            'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:border-brand-400',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            icon ? 'pl-9' : undefined,
            error && 'border-danger focus-visible:ring-danger',
            className
          )}
          {...props}
        />
      </div>
      {error && (
        <p id={errorId} className="mt-1 text-sm text-danger">
          {error}
        </p>
      )}
      {helperText && !error && (
        <p id={helperId} className="mt-1 text-sm text-ink-muted">
          {helperText}
        </p>
      )}
    </div>
  );
}
