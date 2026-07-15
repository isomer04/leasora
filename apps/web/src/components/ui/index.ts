/**
 * UI primitives for the web app. None of these are unmodified
 * Tailwind UI primitives — every component in this folder is
 * project-specific (Leasora-styled, motion-gated, and accessibility
 * tuned for the lease-analysis domain).
 *
 * Components:
 *
 * - Project-specific (custom behavior / domain styling):
 *     avatar, badge, button, card, checkbox, empty-state, input,
 *     pagination, select, skeleton, stat-card, textarea
 *
 * Each module is independently testable via the existing
 * `apps/web/src/tests/accessibility.test.tsx` smoke suite; per-component
 * tests live alongside the page that exercises them.
 *
 * Vendored primitives: none. If we ever bring in shadcn/Tailwind UI
 * primitives, add a top-of-file `/* VENDORED FROM <source> *\/` comment
 * to each module so the audit re-run stays honest.
 */

export { Button } from './button';
export type { ButtonProps, ButtonVariant, ButtonSize } from './button';

export { Card, CardHeader, CardContent, CardFooter } from './card';
export type { CardProps, CardVariant } from './card';

export { Input } from './input';
export type { InputProps } from './input';

export { Textarea } from './textarea';
export type { TextareaProps } from './textarea';

export { Select } from './select';
export type { SelectProps, SelectOption } from './select';

export { Badge } from './badge';
export type { BadgeProps, BadgeStatus, BadgeSize } from './badge';

export { Skeleton } from './skeleton';
export type { SkeletonProps, SkeletonVariant } from './skeleton';

export { EmptyState } from './empty-state';
export type { EmptyStateProps } from './empty-state';

export { Avatar } from './avatar';
export type { AvatarProps, AvatarSize } from './avatar';

export { Checkbox } from './checkbox';
export type { CheckboxProps } from './checkbox';

export { Pagination } from './pagination';
export type { PaginationProps } from './pagination';

export { StatCard } from './stat-card';
export type { StatCardProps, StatCardTrend } from './stat-card';
