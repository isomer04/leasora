'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { motion, AnimatePresence } from 'framer-motion';
import { LayoutDashboard, FileText, GitCompare, Upload, ChevronsLeft, ChevronsRight } from 'lucide-react';
import { useSafeReducedMotion } from '@/lib/motion';
import { cn } from '@/lib/utils';

interface NavItem {
  href: string;
  label: string;
  icon: React.ElementType;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const navGroups: NavGroup[] = [
  {
    label: 'Overview',
    items: [{ href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard }],
  },
  {
    label: 'Workspace',
    items: [
      { href: '/leases', label: 'Leases', icon: FileText },
      { href: '/compare', label: 'Compare', icon: GitCompare },
      { href: '/upload', label: 'Upload', icon: Upload },
    ],
  },
];

function isItemActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(href + '/');
}

interface SidebarProps {
  /** Whether the mobile drawer is open. Ignored on `lg:` and above. */
  isOpen?: boolean;
  /** Called when the mobile drawer should close (backdrop click, nav click). */
  onClose?: () => void;
}

/**
 * App shell sidebar. Grouped nav (Overview / Workspace) with lucide icons,
 * an animated shared-element active indicator, and a collapse-to-icons
 * toggle on large screens. On smaller screens it becomes a slide-in drawer
 * with a backdrop, coordinated by the parent `AppShellClient` via `isOpen`/`onClose`.
 * The Framer Motion active-indicator animation respects `prefers-reduced-motion`.
 */
export function Sidebar({ isOpen = false, onClose }: SidebarProps) {
  const pathname = usePathname();
  const shouldReduceMotion = useSafeReducedMotion();
  const [collapsed, setCollapsed] = useState(false);

  const navContent = (
    <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-4">
      {navGroups.map((group) => (
        <div key={group.label}>
          {!collapsed && (
            <p className="mb-2 px-3 text-xs font-medium uppercase tracking-wider text-ink-muted">
              {group.label}
            </p>
          )}
          <div className="space-y-1">
            {group.items.map((item) => {
              const active = isItemActive(pathname, item.href);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onClose}
                  aria-current={active ? 'page' : undefined}
                  title={collapsed ? item.label : undefined}
                  className={cn(
                    'relative flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors',
                    'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400',
                    active ? 'font-medium text-ink-primary' : 'text-ink-secondary hover:text-ink-primary',
                    collapsed && 'justify-center'
                  )}
                >
                  {active && (
                    <motion.span
                      layoutId={shouldReduceMotion ? undefined : 'sidebar-active-indicator'}
                      className="absolute inset-0 rounded-md bg-surface-overlay"
                      style={{ zIndex: -1 }}
                      transition={shouldReduceMotion ? { duration: 0 } : { type: 'spring', stiffness: 500, damping: 35 }}
                    />
                  )}
                  {active && (
                    <span
                      aria-hidden="true"
                      className="absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-brand-400"
                    />
                  )}
                  <Icon size={20} strokeWidth={1.75} className="shrink-0" aria-hidden="true" />
                  {!collapsed && <span>{item.label}</span>}
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );

  return (
    <>
      {/* Mobile drawer — built on @radix-ui/react-dialog so Escape-to-close,
          focus trap, and focus return on close are handled correctly instead
          of hand-rolled. `forceMount` + AnimatePresence keeps the existing
          framer-motion slide/fade transitions. */}
      <Dialog.Root open={isOpen} onOpenChange={(open) => !open && onClose?.()}>
        <AnimatePresence>
          {isOpen && (
            <Dialog.Portal forceMount>
              <Dialog.Overlay asChild forceMount>
                <motion.div
                  className="fixed inset-0 z-30 bg-black/60 lg:hidden"
                  initial={shouldReduceMotion ? undefined : { opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={shouldReduceMotion ? undefined : { opacity: 0 }}
                  transition={{ duration: 0.15 }}
                />
              </Dialog.Overlay>
              <Dialog.Content asChild forceMount aria-describedby={undefined}>
                <motion.aside
                  className="fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-border-subtle bg-surface-surface lg:hidden"
                  initial={shouldReduceMotion ? undefined : { x: '-100%' }}
                  animate={{ x: 0 }}
                  exit={shouldReduceMotion ? undefined : { x: '-100%' }}
                  transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
                >
                  <Dialog.Title className="sr-only">Navigation</Dialog.Title>
                  {navContent}
                </motion.aside>
              </Dialog.Content>
            </Dialog.Portal>
          )}
        </AnimatePresence>
      </Dialog.Root>

      {/* Desktop sidebar */}
      <aside
        className={cn(
          'hidden shrink-0 flex-col border-r border-border-subtle bg-surface-surface lg:flex',
          collapsed ? 'w-16' : 'w-64',
          'transition-[width] duration-200'
        )}
      >
        {navContent}
        <div className="border-t border-border-subtle p-3">
          <button
            type="button"
            onClick={() => setCollapsed((c) => !c)}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className={cn(
              'flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-ink-secondary transition-colors hover:text-ink-primary',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400',
              collapsed && 'justify-center'
            )}
          >
            {collapsed ? (
              <ChevronsRight size={20} strokeWidth={1.75} aria-hidden="true" />
            ) : (
              <>
                <ChevronsLeft size={20} strokeWidth={1.75} aria-hidden="true" />
                <span>Collapse</span>
              </>
            )}
          </button>
        </div>
      </aside>
    </>
  );
}
