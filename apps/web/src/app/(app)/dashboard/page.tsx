'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import {
  ArrowRight,
  CheckCircle2,
  Clock,
  FileText,
  FilePlus2,
  GitCompare,
  Loader2,
  Upload,
} from 'lucide-react';
import { Badge, Card, CardContent, EmptyState, StatCard } from '@/components/ui';
import { MotionList, MotionListItem } from '@/components/motion';
import { Greeting } from '@/components/features/dashboard/greeting';
import { getComparisonCount, listLeases, type LeaseMetadata } from '@/lib/api';

/** Derive a simple status from a lease's metadata fields. */
function getLeaseStatus(lease: LeaseMetadata): 'active' | 'pending' {
  // A lease is "pending" if key fields haven't been extracted yet.
  const notExtracted = 'Not yet extracted';
  if (
    lease.start_date === notExtracted ||
    lease.end_date === notExtracted ||
    lease.rent_amount === notExtracted
  ) {
    return 'pending';
  }
  return 'active';
}

/** Format an ISO timestamp into a human-friendly relative string. */
function formatRelativeTime(isoString: string | null | undefined): string {
  if (!isoString) return 'Unknown';
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return isoString;

  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return '1 day ago';
  if (diffDays < 7) return `${diffDays} days ago`;
  if (diffDays < 14) return '1 week ago';
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
  if (diffDays < 60) return '1 month ago';
  return `${Math.floor(diffDays / 30)} months ago`;
}

export default function DashboardPage() {
  const isMountedRef = useRef(true);
  const [leases, setLeases] = useState<LeaseMetadata[]>([]);
  const [comparisonCount, setComparisonCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    isMountedRef.current = true;

    async function fetchData() {
      setLoading(true);
      setError('');
      try {
        const [leasesResult, comparisonCountResult] = await Promise.allSettled([
          listLeases(),
          getComparisonCount(),
        ]);
        if (!isMountedRef.current) return;

        // The lease list is the primary fetch — only surface a banner when
        // it actually fails. A rejected leases request is treated as a
        // hard error (banner + no dashboard content).
        if (leasesResult.status === 'rejected') {
          const reason = leasesResult.reason;
          setError(reason instanceof Error ? reason.message : 'Failed to load leases');
        } else {
          const leasesResponse = leasesResult.value;
          if (leasesResponse.error) {
            setError(leasesResponse.error.detail);
          } else {
            setLeases(leasesResponse.data ?? []);
          }
        }

        // The comparison count is a secondary stat — handle its result
        // independently so an unexpected failure here can't prevent lease
        // data from rendering. On any failure (rejected promise or per-
        // call error envelope), keep the existing 0 default rather than
        // surfacing an error banner for a stat card.
        if (comparisonCountResult.status === 'fulfilled') {
          const comparisonCountResponse = comparisonCountResult.value;
          if (!comparisonCountResponse.error && comparisonCountResponse.data) {
            setComparisonCount(comparisonCountResponse.data.count);
          }
        }
      } catch (err) {
        if (!isMountedRef.current) return;
        const message = err instanceof Error ? err.message : 'Failed to load leases';
        setError(message);
      } finally {
        if (isMountedRef.current) {
          setLoading(false);
        }
      }
    }

    fetchData();

    return () => {
      isMountedRef.current = false;
    };
  }, []);

  // Compute stats from real data
  const totalLeases = leases.length;
  const analyzedLeases = leases.filter((l) => getLeaseStatus(l) === 'active').length;
  const pendingLeases = leases.filter((l) => getLeaseStatus(l) === 'pending').length;
  const analysisPct = totalLeases > 0 ? Math.round((analyzedLeases / totalLeases) * 100) : 0;

  const stats = [
    { label: 'Total Leases', value: totalLeases, icon: FileText, trend: undefined, trendTone: 'neutral' as const },
    {
      label: 'Analyzed',
      value: analyzedLeases,
      icon: CheckCircle2,
      trend: totalLeases > 0 ? `${analysisPct}% complete` : undefined,
      trendTone: 'neutral' as const,
    },
    {
      label: 'Pending',
      value: pendingLeases,
      icon: Clock,
      trend: pendingLeases > 0 ? 'Awaiting analysis' : undefined,
      trendTone: 'warning' as const,
    },
    {
      label: 'Comparisons',
      value: comparisonCount,
      icon: GitCompare,
      trend: undefined,
      trendTone: 'neutral' as const,
    },
  ];

  const quickActions = [
    {
      href: '/upload',
      icon: Upload,
      title: 'Upload Lease',
      description: 'Add a new lease document',
    },
    {
      href: '/leases',
      icon: FileText,
      title: 'View Leases',
      description: 'Browse your uploaded leases',
    },
    {
      href: '/compare',
      icon: GitCompare,
      title: 'Compare Leases',
      description: 'Side-by-side comparison',
    },
  ];

  // Show the 5 most recent leases
  const recentLeases = leases.slice(0, 5).map((lease) => ({
    id: lease.id,
    name: lease.name,
    address: lease.location,
    uploadedAt: formatRelativeTime(lease.created_at),
    status: getLeaseStatus(lease),
  }));

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-4xl font-bold text-ink-primary">Dashboard</h1>
        <p className="mt-2 text-ink-secondary">
          <Greeting />
        </p>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 size={32} className="animate-spin text-brand-400" aria-label="Loading dashboard data" />
        </div>
      )}

      {/* Error state */}
      {!loading && error && (
        <Card>
          <CardContent>
            <p className="text-sm text-danger">{error}</p>
          </CardContent>
        </Card>
      )}

      {/* Dashboard content */}
      {!loading && !error && (
        <>
          {/* Stats Grid */}
          <MotionList as="div" className="grid gap-4 md:grid-cols-4">
            {stats.map((stat) => (
              <MotionListItem key={stat.label}>
                <StatCard
                  icon={<stat.icon size={20} strokeWidth={1.75} />}
                  label={stat.label}
                  value={stat.value}
                  trend={stat.trend}
                  trendTone={stat.trendTone}
                />
              </MotionListItem>
            ))}
          </MotionList>

          {/* Quick Actions */}
          <div>
            <h2 className="mb-4 text-2xl font-bold text-ink-primary">Quick Actions</h2>
            <div className="grid gap-4 md:grid-cols-3">
              {quickActions.map((action) => (
                <Link key={action.href} href={action.href} className="group block">
                  <Card variant="interactive">
                    <CardContent className="flex items-start justify-between gap-4">
                      <div className="flex items-start gap-4">
                        <div
                          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-500/10 text-brand-400"
                          aria-hidden="true"
                        >
                          <action.icon size={20} strokeWidth={1.75} />
                        </div>
                        <div>
                          <h3 className="font-semibold text-ink-primary">{action.title}</h3>
                          <p className="text-sm text-ink-secondary">{action.description}</p>
                        </div>
                      </div>
                      <ArrowRight
                        size={18}
                        strokeWidth={1.75}
                        className="mt-2 shrink-0 text-ink-muted transition-transform group-hover:translate-x-1"
                        aria-hidden="true"
                      />
                    </CardContent>
                  </Card>
                </Link>
              ))}
            </div>
          </div>

          {/* Recent Leases */}
          <div>
            <h2 className="mb-4 text-2xl font-bold text-ink-primary">Recent Leases</h2>
            {recentLeases.length === 0 ? (
              <Card>
                <EmptyState
                  icon={<FilePlus2 size={24} strokeWidth={1.75} />}
                  heading="No leases yet"
                  description="Upload your first lease document to start extracting clauses and key terms."
                  action={
                    <Link
                      href="/upload"
                      className="inline-flex items-center gap-2 rounded-md bg-brand-500 px-4 py-2 text-sm font-medium !text-black hover:bg-brand-400 active:bg-brand-700 active:!text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
                    >
                      <Upload size={16} strokeWidth={1.75} aria-hidden="true" />
                      Upload your first lease
                    </Link>
                  }
                />
              </Card>
            ) : (
              <Card className="p-0">
                <MotionList as="ul" className="divide-y divide-border-subtle">
                  {recentLeases.map((lease) => (
                    <MotionListItem key={lease.id} as="li">
                      <Link
                        href={`/leases/${lease.id}`}
                        className="flex items-center justify-between gap-4 px-6 py-4 hover:bg-surface-overlay focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-inset"
                      >
                        <div className="min-w-0">
                          <p className="truncate font-medium text-ink-primary">{lease.name}</p>
                          <p className="truncate text-sm text-ink-secondary">
                            {lease.address} &middot; Uploaded {lease.uploadedAt}
                          </p>
                        </div>
                        <div className="flex shrink-0 items-center gap-3">
                          <Badge status={lease.status}>{lease.status === 'active' ? 'Active' : 'Pending'}</Badge>
                          <ArrowRight size={16} strokeWidth={1.75} className="text-ink-muted" aria-hidden="true" />
                        </div>
                      </Link>
                    </MotionListItem>
                  ))}
                </MotionList>
              </Card>
            )}
          </div>
        </>
      )}
    </div>
  );
}
