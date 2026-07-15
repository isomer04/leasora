'use client';

import Link from 'next/link';
import { motion, AnimatePresence } from 'framer-motion';
import { FileSearch, Menu, X } from 'lucide-react';
import { useSafeReducedMotion } from '@/lib/motion';
import { ThemeToggle } from './theme-toggle';

interface TopbarProps {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
}

/**
 * Sticky app-shell header: logo lockup, mobile hamburger toggle (animates
 * Menu/X, respecting `prefers-reduced-motion`), and the theme toggle.
 */
export function Topbar({ sidebarOpen, onToggleSidebar }: TopbarProps) {
  const shouldReduceMotion = useSafeReducedMotion();

  return (
    <header className="sticky top-0 z-20 flex h-16 shrink-0 items-center border-b border-border-subtle bg-surface-surface px-4 sm:px-6">
      <button
        type="button"
        onClick={onToggleSidebar}
        aria-label={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
        aria-expanded={sidebarOpen}
        className="mr-3 flex h-9 w-9 items-center justify-center rounded-md text-ink-secondary transition-colors hover:text-ink-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 lg:hidden"
      >
        <AnimatePresence initial={false} mode="wait">
          {sidebarOpen ? (
            <motion.span
              key="close"
              initial={shouldReduceMotion ? undefined : { rotate: -90, opacity: 0 }}
              animate={{ rotate: 0, opacity: 1 }}
              exit={shouldReduceMotion ? undefined : { rotate: 90, opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="flex"
            >
              <X size={22} strokeWidth={1.75} aria-hidden="true" />
            </motion.span>
          ) : (
            <motion.span
              key="menu"
              initial={shouldReduceMotion ? undefined : { rotate: 90, opacity: 0 }}
              animate={{ rotate: 0, opacity: 1 }}
              exit={shouldReduceMotion ? undefined : { rotate: -90, opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="flex"
            >
              <Menu size={22} strokeWidth={1.75} aria-hidden="true" />
            </motion.span>
          )}
        </AnimatePresence>
      </button>

      <Link
        href="/dashboard"
        className="flex items-center gap-2 text-ink-primary hover:text-ink-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 rounded-md"
      >
        <FileSearch size={22} strokeWidth={1.75} className="text-brand-400" aria-hidden="true" />
        <span className="text-lg font-semibold tracking-tight">Leasora</span>
      </Link>

      <div className="ml-auto flex items-center gap-4">
        <ThemeToggle />
      </div>
    </header>
  );
}
