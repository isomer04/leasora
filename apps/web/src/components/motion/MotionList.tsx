'use client';

import { motion } from 'framer-motion';
import type { ReactNode } from 'react';
import { listStagger, listItem, useSafeReducedMotion } from '@/lib/motion';

// Explicit lookup map: framer-motion v11's types don't accept arbitrary
// string indexers into `motion`, so we resolve the dynamic tag at the
// call site against a typed table.
const MOTION_LIST_TAGS = {
  ul: motion.ul,
  ol: motion.ol,
  div: motion.div,
} as const;

const MOTION_LIST_ITEM_TAGS = {
  li: motion.li,
  div: motion.div,
} as const;

interface MotionListProps {
  children: ReactNode;
  className?: string;
  as?: keyof typeof MOTION_LIST_TAGS;
}

/**
 * Client wrapper that staggers the entrance of its direct children.
 * Use `MotionListItem` for each child. Falls back to an instant,
 * non-animated render when `prefers-reduced-motion` is set.
 */
export function MotionList({ children, className, as = 'div' }: MotionListProps) {
  const shouldReduceMotion = useSafeReducedMotion();
  const Component = MOTION_LIST_TAGS[as];

  if (shouldReduceMotion) {
    const Static = as;
    return <Static className={className}>{children}</Static>;
  }

  return (
    <Component className={className} initial="hidden" animate="visible" variants={listStagger}>
      {children}
    </Component>
  );
}

interface MotionListItemProps {
  children: ReactNode;
  className?: string;
  as?: keyof typeof MOTION_LIST_ITEM_TAGS;
}

export function MotionListItem({ children, className, as = 'div' }: MotionListItemProps) {
  const shouldReduceMotion = useSafeReducedMotion();
  const Component = MOTION_LIST_ITEM_TAGS[as];

  if (shouldReduceMotion) {
    const Static = as;
    return <Static className={className}>{children}</Static>;
  }

  return (
    <Component className={className} variants={listItem}>
      {children}
    </Component>
  );
}