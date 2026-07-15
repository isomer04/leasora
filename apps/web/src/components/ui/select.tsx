'use client';

import React, { useId } from 'react';
import * as SelectPrimitive from '@radix-ui/react-select';
import { Check, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps {
  label?: string;
  error?: string;
  helperText?: string;
  icon?: React.ReactNode;
  placeholder?: string;
  options: SelectOption[];
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  disabled?: boolean;
  name?: string;
  id?: string;
  className?: string;
}

/**
 * Built on `@radix-ui/react-select` for correct keyboard/ARIA behavior,
 * styled with Tailwind tokens to match `Input`'s focus ring and
 * error-state conventions.
 */
export function Select({
  label,
  error,
  helperText,
  icon,
  placeholder = 'Select...',
  options,
  value,
  defaultValue,
  onValueChange,
  disabled,
  name,
  id: providedId,
  className,
}: SelectProps) {
  const generatedId = useId();
  const triggerId = providedId || generatedId;
  const errorId = error ? `${triggerId}-error` : undefined;
  const helperId = helperText ? `${triggerId}-helper` : undefined;

  return (
    <div className="w-full">
      {label && (
        <label htmlFor={triggerId} className="mb-1 block text-sm font-medium text-ink-secondary">
          {label}
        </label>
      )}
      <SelectPrimitive.Root
        value={value}
        defaultValue={defaultValue}
        onValueChange={onValueChange}
        disabled={disabled}
        name={name}
      >
        <SelectPrimitive.Trigger
          id={triggerId}
          aria-invalid={error ? 'true' : 'false'}
          aria-describedby={error ? errorId : helperId}
          className={cn(
            'relative flex w-full items-center justify-between rounded-md border bg-surface-surface px-3 py-2 text-ink-primary',
            'border-border-subtle',
            'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:border-brand-400',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            'data-[placeholder]:text-ink-muted',
            icon ? 'pl-9' : undefined,
            error && 'border-danger focus-visible:ring-danger',
            className
          )}
        >
          {icon && (
            <span className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-ink-muted">
              {icon}
            </span>
          )}
          <span className="truncate">
            <SelectPrimitive.Value placeholder={placeholder} />
          </span>
          <SelectPrimitive.Icon>
            <ChevronDown size={16} strokeWidth={1.75} className="text-ink-muted" />
          </SelectPrimitive.Icon>
        </SelectPrimitive.Trigger>
        <SelectPrimitive.Portal>
          <SelectPrimitive.Content
            position="popper"
            sideOffset={4}
            className="z-50 overflow-hidden rounded-md border border-border-subtle bg-surface-overlay shadow-elevation-2"
          >
            <SelectPrimitive.Viewport className="p-1">
              {options.map((option) => (
                <SelectPrimitive.Item
                  key={option.value}
                  value={option.value}
                  className={cn(
                    'relative flex cursor-pointer select-none items-center rounded-sm px-8 py-1.5 text-sm text-ink-primary',
                    'data-[highlighted]:bg-brand-500 data-[highlighted]:!text-black data-[highlighted]:outline-none',
                    'data-[disabled]:opacity-50 data-[disabled]:cursor-not-allowed'
                  )}
                >
                  <SelectPrimitive.ItemIndicator className="absolute left-2 inline-flex items-center">
                    <Check size={14} strokeWidth={2} />
                  </SelectPrimitive.ItemIndicator>
                  <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
                </SelectPrimitive.Item>
              ))}
            </SelectPrimitive.Viewport>
          </SelectPrimitive.Content>
        </SelectPrimitive.Portal>
      </SelectPrimitive.Root>
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
