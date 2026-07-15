import { useSyncExternalStore } from 'react';
import type { Variants } from 'framer-motion';

export const EASE_OUT = [0.16, 1, 0.3, 1] as const;

export const fadeSlideUp: Variants = {
  hidden: { opacity: 0, y: 8 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.2, ease: EASE_OUT },
  },
};

export const listStagger: Variants = {
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.03,
    },
  },
};

// Individual list-item entrance is identical to the page-level fade/slide-up,
// so `listItem` reuses `fadeSlideUp` as a single source of truth instead of
// duplicating the same hidden/visible transition config.
export const listItem: Variants = fadeSlideUp;

export const hoverLift = {
  y: -2,
  transition: { duration: 0.15, ease: EASE_OUT },
};

export const pressScale = {
  scale: 0.98,
};

const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';

function subscribeToReducedMotion(callback: () => void): () => void {
  const mediaQueryList = window.matchMedia(REDUCED_MOTION_QUERY);
  mediaQueryList.addEventListener('change', callback);
  return () => mediaQueryList.removeEventListener('change', callback);
}

function getReducedMotionSnapshot(): boolean {
  return window.matchMedia(REDUCED_MOTION_QUERY).matches;
}

// Server (and the client's first render, before hydration) always reports
// `false`, matching what SSR renders. The real client-side preference is
// then read via `getSnapshot` on the client after mount.
function getServerReducedMotionSnapshot(): boolean {
  return false;
}

/**
 * SSR-safe replacement for framer-motion's `useReducedMotion()`.
 *
 * The library hook reads `window.matchMedia` synchronously on first render
 * (see framer-motion's `use-reduced-motion.mjs`), which is fine on the
 * client but has no `window` on the server. Next.js SSR always renders as
 * if motion is allowed, so a client whose OS has reduced motion enabled
 * produces a *different* first render than the server — a hydration
 * mismatch (`className={undefined}` / animated `style` attrs vs the static
 * fallback branch), even though the DOM is otherwise correct.
 *
 * Fix: use `useSyncExternalStore` with a distinct server snapshot (always
 * `false`, matching SSR) so React handles the client/server split itself
 * during hydration, then re-renders with the real preference afterward as
 * a normal update — no manual `useEffect` + `setState` needed.
 */
export function useSafeReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeToReducedMotion,
    getReducedMotionSnapshot,
    getServerReducedMotionSnapshot
  );
}
