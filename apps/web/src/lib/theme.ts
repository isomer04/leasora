// Lightweight dark/light theme support (no next-themes dependency).
//
// `variables.css` already defines a full light-mode token set under `:root`
// and dark overrides under `.dark`, and `tailwind.config.ts` sets
// `darkMode: 'class'`. This module wires those tokens up to a real toggle:
// - `themeInitScript` runs as a blocking inline script in <head> so the
//   right class is applied before first paint (no flash-of-wrong-theme).
// - `ThemeToggle` (components/layout/theme-toggle.tsx) flips the class and
//   persists the choice.

export const THEME_STORAGE_KEY = 'leasora-theme';

export type Theme = 'light' | 'dark';

/**
 * Returns an IIFE string meant to be injected via `dangerouslySetInnerHTML`
 * in the root layout's `<head>`. Reads the persisted preference first, falls
 * back to the OS `prefers-color-scheme`, and defaults to dark (matching the
 * previous dark-only design) if neither is available.
 */
export function themeInitScript(): string {
  return `(function(){try{var t=localStorage.getItem('${THEME_STORAGE_KEY}');if(t!=='light'&&t!=='dark'){t=window.matchMedia('(prefers-color-scheme: light)').matches?'light':'dark';}document.documentElement.classList.toggle('dark',t==='dark');}catch(e){document.documentElement.classList.add('dark');}})();`;
}
