'use client';

import { useEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';
import { THEME_STORAGE_KEY, type Theme } from '@/lib/theme';

/**
 * Flips the `.dark` class on `<html>` and persists the choice to
 * localStorage. Renders a non-interactive placeholder until mounted so the
 * client's actual theme (set by `themeInitScript` before hydration) doesn't
 * mismatch a server-rendered guess.
 */
export function ThemeToggle() {
  const [mounted, setMounted] = useState(false);
  const [theme, setTheme] = useState<Theme>('dark');

  // One-time read of the DOM class applied by the blocking inline script in
  // <head> (see lib/theme.ts) — genuinely external state the server can't
  // know, not a derived value. Safe to disable the cascading-render lint
  // rule here since it only ever fires once on mount.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTheme(document.documentElement.classList.contains('dark') ? 'dark' : 'light');
    setMounted(true);
  }, []);

  function toggleTheme() {
    const next: Theme = theme === 'dark' ? 'light' : 'dark';
    document.documentElement.classList.toggle('dark', next === 'dark');
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // Ignore write errors (e.g. private browsing with storage disabled).
    }
    setTheme(next);
  }

  if (!mounted) {
    return <div className="h-9 w-9" aria-hidden="true" />;
  }

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
      className="flex h-9 w-9 items-center justify-center rounded-md text-ink-secondary transition-colors hover:text-ink-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
    >
      {theme === 'dark' ? (
        <Sun size={18} strokeWidth={1.75} aria-hidden="true" />
      ) : (
        <Moon size={18} strokeWidth={1.75} aria-hidden="true" />
      )}
    </button>
  );
}
