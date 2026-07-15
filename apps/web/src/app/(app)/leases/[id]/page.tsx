import Link from 'next/link';
import { notFound } from 'next/navigation';
import { ArrowLeft, Building2, Calendar, DollarSign, MessageCircle, User } from 'lucide-react';
import { Card, StatCard } from '@/components/ui';
import { MetadataRefreshButton } from '../../../../components/features/lease/metadata-refresh-button';
import { LeaseDeleteButton } from '@/components/features/lease/lease-delete-button';
import { ClauseList } from '@/components/features/lease/clause-list';
import { API_BASE_URL } from '@/lib/env';
import type { LeaseMetadata } from '@/lib/api';

async function fetchLease(id: string): Promise<LeaseMetadata | null> {
  const url = new URL(`/leases/${id}`, API_BASE_URL).toString();
  const response = await fetch(url, { cache: 'no-store' });

  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`Failed to load lease ${id}: ${response.status}`);
  }
  return response.json();
}

export default async function LeaseDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const lease = await fetchLease(id);

  if (!lease) {
    notFound();
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-4xl font-bold text-ink-primary">{lease.name}</h1>
          <p className="mt-2 text-ink-secondary">{lease.location}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <LeaseDeleteButton leaseId={lease.id} leaseName={lease.name} />
          {[
            lease.tenant,
            lease.landlord,
            lease.start_date,
            lease.end_date,
            lease.rent_amount,
          ].includes('Not yet extracted') && <MetadataRefreshButton leaseId={lease.id} />}
          <Link
            href={`/leases/${lease.id}/ask`}
            className="inline-flex items-center justify-center gap-2 rounded-md bg-brand-500 px-4 py-2 text-base font-medium text-black! transition-colors duration-150 hover:bg-brand-400 active:bg-brand-700 active:text-white! focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
          >
            <MessageCircle size={18} strokeWidth={1.75} aria-hidden="true" />
            Ask Question
          </Link>
        </div>
      </div>

      {/* Key Information */}
      <div className="grid gap-4 md:grid-cols-4">
        <StatCard
          icon={<User size={20} strokeWidth={1.75} />}
          label="Tenant"
          value={lease.tenant}
          valueClassName="text-2xl"
        />
        <StatCard
          icon={<Building2 size={20} strokeWidth={1.75} />}
          label="Landlord"
          value={lease.landlord}
          valueClassName="text-2xl"
        />
        <StatCard
          icon={<Calendar size={20} strokeWidth={1.75} />}
          label="Period"
          value={lease.start_date}
          valueClassName="text-2xl"
          trend={lease.start_date === 'Not yet extracted' ? undefined : `to ${lease.end_date}`}
        />
        <StatCard
          icon={<DollarSign size={20} strokeWidth={1.75} />}
          label="Rent"
          value={lease.rent_amount}
          valueClassName="text-2xl"
        />
      </div>

      {/* Clause browsing */}
      <div>
        <h2 className="mb-4 text-2xl font-bold text-ink-primary">Clauses</h2>
        <ClauseList leaseId={lease.id} />
      </div>

      {/* Back Button */}
      <Link
        href="/leases"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-secondary hover:text-ink-primary"
      >
        <ArrowLeft size={16} strokeWidth={1.75} aria-hidden="true" />
        Back to Leases
      </Link>
    </div>
  );
}
