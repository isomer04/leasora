'use client';

import { AnimatePresence, motion } from 'framer-motion';
import type { ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { fadeSlideUp, useSafeReducedMotion } from '@/lib/motion';

interface PageTransitionProps {
  children: ReactNode;
  className?: string;
}

/**
 * Wraps page content in a fade/slide-up entrance animation that re-fires on
 * every route change. App Router doesn't remount `(app)/layout.tsx` (and
 * therefore this wrapper) between sibling routes, so the animated node is
 * keyed on `pathname` and swapped inside `AnimatePresence` to force a fresh
 * enter transition per navigation instead of only on first mount. Respects
 * `prefers-reduced-motion` by rendering instantly with no transform/delay
 * when the user has opted out.
 */
export function PageTransition({ children, className }: PageTransitionProps) {
  const shouldReduceMotion = useSafeReducedMotion();
  const pathname = usePathname();

  if (shouldReduceMotion) {
    return <div className={className}>{children}</div>;
  }

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={pathname}
        className={className}
        initial="hidden"
        animate="visible"
        exit="hidden"
        variants={fadeSlideUp}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}
