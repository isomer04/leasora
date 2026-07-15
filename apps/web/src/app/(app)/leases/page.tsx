'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { AlertCircle, Eye, FilePlus2, Plus, Search } from 'lucide-react';
import { Badge, Button, Card, EmptyState, Input, Pagination, Select } from '@/components/ui';
import { PAGINATION } from '@/lib/constants';
import { listLeases, type LeaseMetadata } from '@/lib/api';

function formatDate(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

const PAGE_SIZE = PAGINATION.DEFAULT_PAGE_SIZE;

export default function LeasesPage() {
  const router = useRouter();
  const isMountedRef = useRef(true);
  const [leases, setLeases] = useState<LeaseMetadata[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    // Reset on every (re)mount — React Strict Mode's dev-only double-mount
    // simulates an unmount before the real mount, which would otherwise
    // leave this stuck at false forever (see upload/page.tsx fix for the
    // same bug pattern).
    isMountedRef.current = true;

    async function fetchLeases() {
      setLoading(true);
      setError('');
      const response = await listLeases();
      if (!isMountedRef.current) return;

      if (response.error) {
        setError(response.error.detail);
      } else {
        setLeases(response.data ?? []);
      }
      setLoading(false);
    }

    fetchLeases();

    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const filteredLeases = leases.filter((lease) => {
    if (searchQuery.trim() === '') return true;
    const query = searchQuery.toLowerCase();
    return (
      lease.name.toLowerCase().includes(query) || lease.tenant.toLowerCase().includes(query)
    );
  });

  const totalPages = Math.max(1, Math.ceil(filteredLeases.length / PAGE_SIZE));
  const safeCurrentPage = Math.min(currentPage, totalPages);
  const paginatedLeases = filteredLeases.slice(
    (safeCurrentPage - 1) * PAGE_SIZE,
    safeCurrentPage * PAGE_SIZE
  );

  function renderPeriod(lease: LeaseMetadata): string {
    if (lease.start_date === 'Not yet extracted' || lease.end_date === 'Not yet extracted') {
      return 'Not yet extracted';
    }
    return `${formatDate(lease.start_date)} – ${formatDate(lease.end_date)}`;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-bold text-ink-primary">Leases</h1>
          <p className="mt-2 text-ink-secondary">Manage and analyze your lease documents</p>
        </div>
        <Button
          iconLeft={<Plus size={18} strokeWidth={1.75} />}
          onClick={() => router.push('/upload')}
        >
          Upload Lease
        </Button>
      </div>

      {/* Search */}
      <div className="flex gap-4">
        <div className="flex-1">
          <Input
            type="search"
            placeholder="Search leases..."
            icon={<Search size={16} strokeWidth={1.75} />}
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setCurrentPage(1);
            }}
          />
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-md border border-danger/30 bg-danger/10 p-4 text-danger">
          <AlertCircle size={18} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden="true" />
          <p className="text-sm">{error}</p>
        </div>
      )}

      {loading ? (
        <Card>
          <p className="text-sm text-ink-secondary">Loading leases…</p>
        </Card>
      ) : filteredLeases.length === 0 ? (
        <Card>
          {leases.length === 0 ? (
            <EmptyState
              icon={<FilePlus2 size={24} strokeWidth={1.75} />}
              heading="No leases yet"
              description="Upload your first lease document to start extracting clauses and key terms."
              action={
                <Button iconLeft={<Plus size={16} strokeWidth={1.75} />} onClick={() => router.push('/upload')}>
                  Upload your first lease
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={<Search size={24} strokeWidth={1.75} />}
              heading="No matching leases"
              description="Try a different search term."
            />
          )}
        </Card>
      ) : (
        <>
          {/* Leases Table (desktop) */}
          <Card className="hidden overflow-hidden p-0 md:block">
            <div className="max-h-[520px] overflow-auto">
              <table className="w-full">
                <thead className="sticky top-0 border-b border-border-subtle bg-surface-elevated">
                  <tr>
                    <th scope="col" className="px-6 py-3 text-left text-sm font-medium text-ink-primary">Name</th>
                    <th scope="col" className="px-6 py-3 text-left text-sm font-medium text-ink-primary">Tenant</th>
                    <th scope="col" className="px-6 py-3 text-left text-sm font-medium text-ink-primary">Period</th>
                    <th scope="col" className="px-6 py-3 text-left text-sm font-medium text-ink-primary">Chunks</th>
                    <th scope="col" className="px-6 py-3 text-right text-sm font-medium text-ink-primary">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle">
                  {paginatedLeases.map((lease) => (
                    <tr key={lease.id} className="hover:bg-surface-overlay">
                      <td className="px-6 py-4 font-medium text-ink-primary">{lease.name}</td>
                      <td className="px-6 py-4 text-ink-secondary">{lease.tenant}</td>
                      <td className="px-6 py-4 text-sm text-ink-secondary">{renderPeriod(lease)}</td>
                      <td className="px-6 py-4">
                        <Badge status="info">{lease.chunk_count ?? '—'}</Badge>
                      </td>
                      <td className="px-6 py-4 text-right">
                        <Link
                          href={`/leases/${lease.id}`}
                          aria-label={`View ${lease.name}`}
                          className="inline-flex h-8 w-8 items-center justify-center rounded-full text-ink-secondary hover:bg-surface-overlay hover:text-ink-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
                        >
                          <Eye size={16} strokeWidth={1.75} />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          {/* Leases Stacked Cards (mobile) */}
          <div className="space-y-4 md:hidden">
            {paginatedLeases.map((lease) => (
              <Card key={lease.id}>
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <p className="truncate font-medium text-ink-primary">{lease.name}</p>
                    <p className="mt-1 text-sm text-ink-secondary">{lease.tenant}</p>
                    <p className="font-tabular mt-1 text-sm text-ink-secondary">{renderPeriod(lease)}</p>
                  </div>
                  <Link
                    href={`/leases/${lease.id}`}
                    aria-label={`View ${lease.name}`}
                    className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-ink-secondary hover:bg-surface-overlay hover:text-ink-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
                  >
                    <Eye size={16} strokeWidth={1.75} />
                  </Link>
                </div>
                <div className="mt-4">
                  <Badge status="info">{lease.chunk_count ?? '—'} chunks</Badge>
                </div>
              </Card>
            ))}
          </div>

          {/* Pagination */}
          <div className="flex justify-center">
            <Pagination currentPage={safeCurrentPage} totalPages={totalPages} onPageChange={setCurrentPage} />
          </div>
        </>
      )}
    </div>
  );
}
