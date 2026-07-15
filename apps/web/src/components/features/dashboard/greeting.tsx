'use client';

import { useEffect, useState } from 'react';

/**
 * Renders the time-of-day greeting/weekday client-side so it reflects the
 * visitor's local clock instead of the server's (see PR #6 review: the
 * dashboard Server Component previously computed these with server-local
 * time, which reads wrong for users in other timezones).
 *
 * Starts with a stable, non-time-dependent placeholder and swaps in the
 * real value after mount to avoid a hydration mismatch.
 */
function computeGreeting(): string {
  const now = new Date();
  const hour = now.getHours();
  const greeting = hour < 12 ? 'good morning' : hour < 18 ? 'good afternoon' : 'good evening';
  const weekday = now.toLocaleDateString('en-US', { weekday: 'long' });
  return `${weekday}, ${greeting}`;
}

export function Greeting() {
  const [text, setText] = useState<string | null>(null);

  // One-time read of the visitor's local clock on mount — this is the
  // "subscribe to an external system" case `useEffect` exists for (the
  // browser's Date/timezone, which the server can't see), not a derived
  // value that belongs in render. Safe to disable the cascading-render
  // lint rule here since it only ever fires once.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setText(computeGreeting());
  }, []);

  return <>{text ?? 'Welcome back'}. Here&apos;s your overview.</>;
}
