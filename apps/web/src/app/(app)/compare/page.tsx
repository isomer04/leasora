'use client';

import { FormEvent, useState } from 'react';
import { AlertCircle, Lightbulb, Scale } from 'lucide-react';
import { Badge, Button, Card, CardContent, CardHeader, Checkbox, EmptyState } from '@/components/ui';
import { useCompare } from '@/hooks/useCompare';
import { useLeases } from '@/hooks/useLeases';

export default function ComparePage() {
  const [selectedLeases, setSelectedLeases] = useState<string[]>([]);
  const { compare, loading, error, result } = useCompare();
  const { leases, loading: leasesLoading, error: leasesError } = useLeases();

  async function handleCompare(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();

    if (selectedLeases.length < 2) {
      return;
    }

    await compare(selectedLeases);
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-4xl font-bold text-ink-primary">Compare Leases</h1>
        <p className="mt-2 text-ink-secondary">
          Select multiple leases to compare terms and identify differences
        </p>
      </div>

      {/* Selection Form */}
      <Card>
        {leasesLoading ? (
          <p className="text-sm text-ink-secondary">Loading leases…</p>
        ) : leases.length === 0 ? (
          <EmptyState
            icon={<Scale size={24} strokeWidth={1.75} />}
            heading="No leases to compare"
            description="Upload at least two leases before comparing them."
          />
        ) : (
          <form onSubmit={handleCompare} className="space-y-6">
            <fieldset>
              <legend className="mb-4 text-sm font-medium text-ink-secondary">
                Select Leases to Compare (minimum 2)
              </legend>
              <div className="space-y-1">
                {leases.map((lease) => (
                  <div
                    key={lease.id}
                    className="rounded-md px-2 py-1.5 hover:bg-surface-overlay"
                  >
                    <Checkbox
                      label={lease.name}
                      checked={selectedLeases.includes(lease.id)}
                      onCheckedChange={(checked) => {
                        if (checked) {
                          setSelectedLeases([...selectedLeases, lease.id]);
                        } else {
                          setSelectedLeases(selectedLeases.filter((id) => id !== lease.id));
                        }
                      }}
                    />
                  </div>
                ))}
              </div>
            </fieldset>

            <div className="flex items-center gap-4">
              <Button type="submit" disabled={loading || selectedLeases.length < 2} isLoading={loading}>
                {loading ? 'Comparing...' : 'Compare Selected Leases'}
              </Button>
              <p className="text-sm text-ink-muted">
                {selectedLeases.length} of {leases.length} selected &middot; min 2
              </p>
            </div>
          </form>
        )}
      </Card>

      {/* Error State */}
      {(error || leasesError) && (
        <div className="flex items-start gap-2 rounded-md border border-danger/30 bg-danger/10 p-4 text-danger">
          <AlertCircle size={18} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden="true" />
          <p className="text-sm">{error || leasesError}</p>
        </div>
      )}

      {/* Comparison Results */}
      {result && (
        <div className="space-y-6">
          <h2 className="text-2xl font-bold text-ink-primary">Comparison Results</h2>

          {result.differences.length === 0 ? (
            <Card>
              <EmptyState
                icon={<Scale size={24} strokeWidth={1.75} />}
                heading="No differences detected yet"
                description="The comparison engine is still being built — check back soon for detailed clause-by-clause differences."
              />
            </Card>
          ) : (
            <Card className="overflow-hidden p-0">
              <table className="w-full">
                <thead className="border-b border-border-subtle bg-surface-overlay">
                  <tr>
                    <th scope="col" className="px-6 py-3 text-left text-sm font-medium text-ink-primary">Clause</th>
                    <th scope="col" className="px-6 py-3 text-left text-sm font-medium text-ink-primary">
                      {leases.find((l) => l.id === result.lease_ids[0])?.name ?? 'Lease A'}
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-sm font-medium text-ink-primary">
                      {leases.find((l) => l.id === result.lease_ids[1])?.name ?? 'Lease B'}
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-sm font-medium text-ink-primary">Difference</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle">
                  {result.differences.map((row, idx) => (
                    <tr key={idx} className="hover:bg-surface-overlay">
                      <td className="px-6 py-4 font-medium text-ink-primary">{row.clause_type}</td>
                      <td className="px-6 py-4 text-ink-secondary">{row.lease1_value}</td>
                      <td className="px-6 py-4 text-ink-secondary">{row.lease2_value}</td>
                      <td className="px-6 py-4">
                        <Badge status="warning">{row.difference}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}

          {/* Key Insights */}
          <Card className="border-info/20 bg-info/5">
            <CardHeader>
              <div className="flex items-center gap-2">
                <Lightbulb size={18} strokeWidth={1.75} className="text-info" aria-hidden="true" />
                <h3 className="font-bold text-ink-primary">Key Insights</h3>
              </div>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2 text-sm text-ink-secondary">
                {(result.key_insights ?? []).map((insight, idx) => (
                  <li key={idx}>{insight}</li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
