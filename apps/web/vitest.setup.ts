// Vitest setup — runs before each test file.
//
// Stubs out browser APIs that jsdom doesn't fully implement, and
// disables framer-motion in unit tests so we don't churn on animation
// timing.

import { afterEach, vi, beforeAll } from 'vitest';
import { cleanup } from '@testing-library/react';

beforeAll(() => {
  // jsdom doesn't implement matchMedia / ResizeObserver / IntersectionObserver;
  // the app uses matchMedia for prefers-reduced-motion and Radix Checkbox
  // uses ResizeObserver for measurement. Stub no-op implementations.
  if (typeof window !== 'undefined') {
    const noopMatchMedia = (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    });
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      configurable: true,
      value: noopMatchMedia,
    });

    // Radix UI Checkbox uses ResizeObserver for measurement. jsdom
    // doesn't implement it — stub a minimal observer that never fires.
    class NoopResizeObserver {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    Object.defineProperty(window, 'ResizeObserver', {
      writable: true,
      configurable: true,
      value: NoopResizeObserver,
    });

    class NoopIntersectionObserver {
      observe() {}
      unobserve() {}
      disconnect() {}
      takeRecords() { return []; }
      root = null;
      rootMargin = '';
      thresholds = [];
    }
    Object.defineProperty(window, 'IntersectionObserver', {
      writable: true,
      configurable: true,
      value: NoopIntersectionObserver,
    });

    // jsdom doesn't implement Element#scrollIntoView; pages call it after
    // async work (e.g. after a successful API call). Provide a no-op so
    // post-test timers don't throw an unhandled exception.
    if (!Element.prototype.scrollIntoView) {
      Element.prototype.scrollIntoView = function () {};
    }
  }
});

afterEach(() => {
  cleanup();
});

// next/navigation is a stub in unit tests; the pages we test don't
// actually navigate, but if they did, this prevents a hard crash.
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
  }),
  useParams: () => ({}),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/',
}));

// next/link — render as a plain anchor so we don't pull in the
// client-side router during unit tests.
vi.mock('next/link', () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => {
    const React = require('react');
    return React.createElement('a', { href, ...rest }, children);
  },
}));

// framer-motion — disable animations in unit tests so we don't fight
// timing.
vi.mock('framer-motion', () => ({
  motion: new Proxy(
    {},
    {
      get: (_target, prop) => {
        const React = require('react');
        const Component = React.forwardRef((props: Record<string, unknown>, ref: unknown) =>
          React.createElement(prop as string, { ...props, ref }, props.children)
        );
        Component.displayName = `motion.${String(prop)}`;
        return Component;
      },
    }
  ),
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
  useReducedMotion: () => false,
  useSafeReducedMotion: () => false,
  hoverLift: {},
  tapPress: {},
}));