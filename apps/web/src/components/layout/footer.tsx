import Link from 'next/link';
import { FileSearch } from 'lucide-react';

/**
 * Marketing-only footer (used by `(marketing)/layout.tsx`). "Privacy"/"Terms"
 * and "Twitter"/"LinkedIn" have no real destination yet, so they render as
 * plain (non-interactive) text instead of `href="#"` placeholder links —
 * that pattern trips `jsx-a11y/anchor-is-valid` and isn't a real affordance
 * for users anyway.
 */
export function Footer() {
  const currentYear = new Date().getFullYear();

  return (
    <footer className="border-t border-border-subtle bg-surface-surface mt-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid md:grid-cols-4 gap-8 mb-8">
          <div>
            <div className="mb-4 flex items-center gap-2 text-ink-primary">
              <FileSearch size={20} strokeWidth={1.75} className="text-brand-400" aria-hidden="true" />
              <span className="font-semibold tracking-tight">Leasora</span>
            </div>
            <p className="text-sm text-ink-secondary">AI-powered lease analysis platform</p>
          </div>
          <div>
            <h4 className="font-semibold text-ink-primary mb-4">Product</h4>
            <ul className="space-y-2 text-sm text-ink-secondary">
              <li>
                <Link href="/about" className="hover:text-ink-primary rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400">
                  About
                </Link>
              </li>
              <li>
                <Link href="/pricing" className="hover:text-ink-primary rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400">
                  Pricing
                </Link>
              </li>
            </ul>
          </div>
          <div>
            <h4 className="font-semibold text-ink-primary mb-4">Legal</h4>
            <ul className="space-y-2 text-sm text-ink-secondary">
              <li><span className="cursor-not-allowed opacity-50" title="Coming soon">Privacy</span></li>
              <li><span className="cursor-not-allowed opacity-50" title="Coming soon">Terms</span></li>
            </ul>
          </div>
          <div>
            <h4 className="font-semibold text-ink-primary mb-4">Support</h4>
            <ul className="space-y-2 text-sm text-ink-secondary">
              <li><span className="cursor-not-allowed opacity-50" title="Coming soon">Help Center</span></li>
              <li><span className="cursor-not-allowed opacity-50" title="Coming soon">Contact</span></li>
            </ul>
          </div>
        </div>

        <div className="border-t border-border-subtle pt-8 flex flex-col gap-4 sm:flex-row sm:justify-between sm:items-center text-sm text-ink-secondary">
          <p>&copy; {currentYear} Leasora. All rights reserved.</p>
          <div className="flex gap-4">
            <span className="cursor-not-allowed opacity-50" title="Coming soon">Twitter</span>
            <span className="cursor-not-allowed opacity-50" title="Coming soon">LinkedIn</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
