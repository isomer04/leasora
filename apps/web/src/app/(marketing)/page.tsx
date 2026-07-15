import Link from 'next/link';
import { FileText, GitCompare, ShieldCheck, Sparkles } from 'lucide-react';
import { Card, CardContent } from '@/components/ui';
import { MotionList, MotionListItem } from '@/components/motion';

const features = [
  {
    icon: FileText,
    title: 'Smart Analysis',
    description: 'Extract and classify key lease clauses automatically with AI-powered analysis.',
  },
  {
    icon: GitCompare,
    title: 'Compare Terms',
    description: 'Side-by-side comparison of multiple leases to identify differences and outliers.',
  },
  {
    icon: Sparkles,
    title: 'Risk Detection',
    description: 'Identify potential risks and unfavorable terms in your leases instantly.',
  },
  {
    icon: ShieldCheck,
    title: 'Secure & Private',
    description: 'Your documents are encrypted in transit and at rest, and never shared.',
  },
];

const stats = [
  { value: '10,000+', label: 'Leases analyzed' },
  { value: '3.5x', label: 'Faster than manual review' },
  { value: '99.9%', label: 'Uptime' },
];

export default function HomePage() {
  return (
    <div className="min-h-screen">
      {/* Hero Section */}
      <section className="px-4 sm:px-6 lg:px-8 py-20 bg-gradient-to-b from-brand-950/40 to-surface-base">
        <div className="max-w-7xl mx-auto grid gap-12 lg:grid-cols-2 lg:items-center">
          <div className="text-center lg:text-left">
            <h1 className="text-5xl sm:text-6xl font-bold text-ink-primary mb-6">
              Analyze Leases with AI
            </h1>
            <p className="text-xl text-ink-secondary mb-8 max-w-2xl mx-auto lg:mx-0">
              Extract key insights, compare terms, and identify risks across multiple lease agreements
              instantly.
            </p>
            <div className="flex flex-col sm:flex-row justify-center lg:justify-start items-center gap-4">
              <Link
                href="/dashboard"
                className="inline-flex items-center justify-center rounded-md bg-brand-500 px-8 py-3 text-lg font-semibold !text-black transition-colors duration-150 hover:bg-brand-400 active:bg-brand-700 active:!text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
              >
                Get Started
              </Link>
              <Link
                href="/about"
                className="inline-flex items-center justify-center rounded-md border border-border-strong px-8 py-3 text-lg font-semibold text-ink-primary transition-colors duration-150 hover:bg-surface-overlay focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
              >
                Learn More
              </Link>
            </div>
          </div>

          {/* Product mockup: stylized browser frame around an abstract dashboard preview */}
          <div className="hidden lg:block" aria-hidden="true">
            <Card variant="glass" className="p-0 overflow-hidden">
              {/* Browser chrome */}
              <div className="flex items-center gap-2 border-b border-border-subtle bg-surface-surface px-4 py-3">
                <span className="h-2.5 w-2.5 rounded-full bg-danger/70" />
                <span className="h-2.5 w-2.5 rounded-full bg-warning/70" />
                <span className="h-2.5 w-2.5 rounded-full bg-success/70" />
                <div className="ml-3 h-5 flex-1 max-w-xs rounded-full bg-surface-overlay" />
              </div>
              {/* Abstract dashboard preview */}
              <div className="space-y-4 p-6">
                <div className="grid grid-cols-3 gap-3">
                  <div className="h-16 rounded-md bg-surface-overlay" />
                  <div className="h-16 rounded-md bg-surface-overlay" />
                  <div className="h-16 rounded-md bg-brand-500/20" />
                </div>
                <div className="space-y-2 rounded-md bg-surface-surface p-4">
                  <div className="h-3 w-2/3 rounded bg-surface-overlay" />
                  <div className="h-3 w-1/2 rounded bg-surface-overlay" />
                  <div className="h-3 w-5/6 rounded bg-surface-overlay" />
                </div>
                <div className="space-y-2 rounded-md bg-surface-surface p-4">
                  <div className="h-3 w-1/3 rounded bg-surface-overlay" />
                  <div className="h-3 w-2/3 rounded bg-surface-overlay" />
                </div>
              </div>
            </Card>
          </div>
        </div>
      </section>

      {/* Social proof / stat strip */}
      <section className="px-4 sm:px-6 lg:px-8 py-12 border-y border-border-subtle bg-surface-surface">
        <div className="max-w-5xl mx-auto">
          <p className="text-center text-sm font-medium uppercase tracking-wide text-ink-muted mb-8">
            Trusted by teams managing thousands of leases
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-8 text-center">
            {stats.map((stat) => (
              <div key={stat.label}>
                <p className="font-tabular text-3xl sm:text-4xl font-bold text-ink-primary">{stat.value}</p>
                <p className="mt-1 text-sm text-ink-secondary">{stat.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="px-4 sm:px-6 lg:px-8 py-20">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-4xl font-bold text-center mb-12 text-ink-primary">Powerful Features</h2>
          <MotionList as="div" className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {features.map((feature) => (
              <MotionListItem key={feature.title}>
                <Card variant="interactive" className="h-full">
                  <CardContent>
                    <div
                      className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-brand-500/10 text-brand-400"
                      aria-hidden="true"
                    >
                      <feature.icon size={24} strokeWidth={1.75} />
                    </div>
                    <h3 className="text-xl font-bold mb-2 text-ink-primary">{feature.title}</h3>
                    <p className="text-ink-secondary">{feature.description}</p>
                  </CardContent>
                </Card>
              </MotionListItem>
            ))}
          </MotionList>
        </div>
      </section>

      {/* Bottom CTA band */}
      <section className="px-4 sm:px-6 lg:px-8 py-16 bg-brand-500/10">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl sm:text-4xl font-bold text-ink-primary mb-4">
            Ready to analyze your first lease?
          </h2>
          <p className="text-lg text-ink-secondary mb-8">
            Get started in minutes — no credit card required.
          </p>
          <Link
            href="/dashboard"
            className="inline-flex items-center justify-center rounded-md bg-brand-500 px-8 py-3 text-lg font-semibold !text-black transition-colors duration-150 hover:bg-brand-400 active:bg-brand-700 active:!text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
          >
            Get Started
          </Link>
        </div>
      </section>
    </div>
  );
}
