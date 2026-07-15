'use client';

import { useState, type ReactNode } from 'react';
import { Topbar } from './topbar';
import { Sidebar } from './sidebar';

interface AppShellClientProps {
  children: ReactNode;
}

/**
 * Smallest possible client component needed to coordinate the mobile
 * sidebar drawer's open/closed state between `Topbar`'s hamburger and
 * `Sidebar`'s drawer/backdrop, and to own the overall shell layout (topbar
 * on top, sidebar + main content row below). Accepts server-rendered
 * `children` so `(app)/layout.tsx` itself can stay a Server Component.
 */
export function AppShellClient({ children }: AppShellClientProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex min-h-screen flex-col bg-surface-base">
      <Topbar sidebarOpen={sidebarOpen} onToggleSidebar={() => setSidebarOpen((open) => !open)} />
      <div className="flex flex-1">
        <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
        <main className="flex-1 overflow-auto">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">{children}</div>
        </main>
      </div>
    </div>
  );
}
