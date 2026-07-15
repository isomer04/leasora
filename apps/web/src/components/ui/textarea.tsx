import React, { useId } from 'react';
import { cn } from '@/lib/utils';

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export function Textarea({
  label,
  error,
  helperText,
  className,
  id: providedId,
  rows = 4,
  ...props
}: TextareaProps) {
  const generatedId = useId();
  const textareaId = providedId || generatedId;
  const errorId = error ? `${textareaId}-error` : undefined;
  const helperId = helperText ? `${textareaId}-helper` : undefined;

  return (
    <div className="w-full">
      {label && (
        <label htmlFor={textareaId} className="mb-1 block text-sm font-medium text-ink-secondary">
          {label}
        </label>
      )}
      <textarea
        id={textareaId}
        rows={rows}
        aria-invalid={error ? 'true' : 'false'}
        aria-describedby={error ? errorId : helperId}
        className={cn(
          'w-full rounded-md border bg-surface-surface px-3 py-2 text-ink-primary',
          'border-border-subtle placeholder:text-ink-muted',
          'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:border-brand-400',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          error && 'border-danger focus-visible:ring-danger',
          className
        )}
        {...props}
      />
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
