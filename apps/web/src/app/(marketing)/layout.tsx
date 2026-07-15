import Link from 'next/link';
import { FileSearch } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Footer } from '@/components/layout/footer';

// Link-styled-as-button classes, mirroring the `Button` component's primary variant.
const primaryButtonClasses = cn(
  'inline-flex items-center justify-center rounded-md bg-brand-500 px-3 py-1.5 text-sm font-medium !text-black',
  'transition-colors duration-150 hover:bg-brand-400 active:bg-brand-700 active:!text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400'
);

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen flex flex-col bg-surface-base">
      <header className="border-b border-border-subtle bg-surface-surface">
        <nav className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <Link
            href="/"
            className="flex items-center gap-2 text-ink-primary rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
          >
            <FileSearch size={22} strokeWidth={1.75} className="text-brand-400" aria-hidden="true" />
            <span className="text-lg font-semibold tracking-tight">Leasora</span>
          </Link>
          <div className="flex items-center gap-6">
            <Link
              href="/about"
              className="text-sm text-ink-secondary hover:text-ink-primary rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
            >
              About
            </Link>
            <Link
              href="/pricing"
              className="text-sm text-ink-secondary hover:text-ink-primary rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
            >
              Pricing
            </Link>
            <Link href="/dashboard" className={primaryButtonClasses}>
              Open App
            </Link>
          </div>
        </nav>
      </header>
      <main className="flex-1">{children}</main>
      <Footer />
    </div>
  );
}
