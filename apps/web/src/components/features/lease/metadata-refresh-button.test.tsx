import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MetadataRefreshButton } from './metadata-refresh-button';

const mocks = vi.hoisted(() => ({
  refreshLeaseMetadata: vi.fn(),
  routerRefresh: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: mocks.routerRefresh }),
}));
vi.mock('@/lib/api', () => ({
  refreshLeaseMetadata: mocks.refreshLeaseMetadata,
}));

const lease = {
  id: 'lease_abc12345',
  name: 'Test Lease',
  tenant: 'Tenant',
  landlord: 'Landlord',
  start_date: '2025-01-01',
  end_date: '2025-12-31',
  rent_amount: '$1,000/month',
  location: 'Not yet extracted',
};

describe('MetadataRefreshButton', () => {
  beforeEach(() => vi.clearAllMocks());

  it('reports updated fields and refreshes server-rendered data', async () => {
    mocks.refreshLeaseMetadata.mockResolvedValue({
      data: { status: 'updated', updated_fields: ['tenant'], lease },
      status: 200,
    });
    render(<MetadataRefreshButton leaseId={lease.id} />);

    await userEvent.click(screen.getByRole('button', { name: /retry extraction/i }));

    const status = await screen.findByRole('status');
    expect(status.textContent).toContain('1 metadata field updated.');
    expect(mocks.routerRefresh).toHaveBeenCalledOnce();
  });

  it('announces no-fields result and disables repeated retries', async () => {
    mocks.refreshLeaseMetadata.mockResolvedValue({
      data: { status: 'no_fields', updated_fields: [], lease },
      status: 200,
    });
    render(<MetadataRefreshButton leaseId={lease.id} />);

    await userEvent.click(screen.getByRole('button', { name: /retry extraction/i }));

    const status = await screen.findByRole('status');
    expect(status.textContent).toContain('No additional metadata was found in this document.');
    const button = screen.getByRole('button', { name: /no more metadata/i });
    expect(button.hasAttribute('disabled')).toBe(true);
    expect(mocks.routerRefresh).not.toHaveBeenCalled();
  });

  it('announces provider failures without claiming success', async () => {
    mocks.refreshLeaseMetadata.mockResolvedValue({
      error: {
        detail: 'Metadata extraction is temporarily unavailable',
        error_code: 'LLMError',
        status: 503,
      },
      status: 503,
    });
    render(<MetadataRefreshButton leaseId={lease.id} />);

    await userEvent.click(screen.getByRole('button', { name: /retry extraction/i }));

    const status = await screen.findByRole('status');
    expect(status.textContent).toContain('Metadata extraction is temporarily unavailable');
    expect(mocks.routerRefresh).not.toHaveBeenCalled();
  });
});