import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import DashboardPage from './page';
import * as api from '@/lib/api';

// Smoke test for DashboardPage.
//
// One component test per page; assert the page renders + a key
// interaction (data load via listLeases). We mock @/lib/api to keep the
// test offline; the real fetch surface is exercised by E2E tests.

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the heading and dashboard shell', async () => {
    vi.spyOn(api, 'listLeases').mockResolvedValue({
      data: [],
      status: 200,
    });
    vi.spyOn(api, 'getComparisonCount').mockResolvedValue({
      data: { count: 0 },
      status: 200,
    });

    render(<DashboardPage />);

    // The page renders the heading immediately; loading state appears
    // until the mocked fetch resolves.
    expect(screen.getByRole('heading', { name: /dashboard/i })).toBeInTheDocument();

    // Once the mock resolves, the empty-state appears.
    await waitFor(() => {
      expect(screen.getByText(/no leases yet/i)).toBeInTheDocument();
    });
  });

  it('renders lease rows when leases are returned', async () => {
    vi.spyOn(api, 'listLeases').mockResolvedValue({
      data: [
        {
          id: 'lease_demo_1',
          name: 'Office Space 2024',
          location: '123 Main St',
          tenant: 'Alice',
          landlord: 'Bob',
          start_date: '2024-01-01',
          end_date: '2024-12-31',
          rent_amount: '$2000',
          created_at: new Date().toISOString(),
        },
      ],
      status: 200,
    });
    vi.spyOn(api, 'getComparisonCount').mockResolvedValue({
      data: { count: 3 },
      status: 200,
    });

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText('Office Space 2024')).toBeInTheDocument();
    });
  });

  it('surfaces an error banner when listLeases rejects', async () => {
    vi.spyOn(api, 'listLeases').mockRejectedValue(new Error('boom'));
    vi.spyOn(api, 'getComparisonCount').mockResolvedValue({
      data: { count: 0 },
      status: 200,
    });

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText('boom')).toBeInTheDocument();
    });
  });
});