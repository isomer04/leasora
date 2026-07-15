import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import ComparePage from './page';
import { useCompare } from '@/hooks/useCompare';
import { useLeases } from '@/hooks/useLeases';

// Mock the hooks that ComparePage depends on, so we can drive the
// page through its loading / interaction states without standing up the
// full comparison backend.

vi.mock('@/hooks/useCompare');
vi.mock('@/hooks/useLeases');

const mockUseCompare = vi.mocked(useCompare);
const mockUseLeases = vi.mocked(useLeases);

describe('ComparePage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('shows a heading and a loading state while leases are fetched', () => {
    mockUseLeases.mockReturnValue({
      leases: [],
      loading: true,
      error: null,
      refetch: vi.fn(),
    });
    mockUseCompare.mockReturnValue({
      compare: vi.fn(),
      loading: false,
      error: null,
      result: null,
    });

    render(<ComparePage />);

    expect(
      screen.getByRole('heading', { name: /compare leases/i })
    ).toBeInTheDocument();
    expect(screen.getByText(/loading leases/i)).toBeInTheDocument();
  });

  it('renders an empty-state when no leases are available', async () => {
    mockUseLeases.mockReturnValue({
      leases: [],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseCompare.mockReturnValue({
      compare: vi.fn(),
      loading: false,
      error: null,
      result: null,
    });

    render(<ComparePage />);

    await waitFor(() => {
      expect(screen.getByText(/no leases to compare/i)).toBeInTheDocument();
    });
  });

  it('lists leases as checkboxes and triggers compare on submit', async () => {
    const compareMock = vi.fn().mockResolvedValue(undefined);
    mockUseLeases.mockReturnValue({
      leases: [
        { id: 'lease_a', name: 'Lease A' },
        { id: 'lease_b', name: 'Lease B' },
      ],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseCompare.mockReturnValue({
      compare: compareMock,
      loading: false,
      error: null,
      result: null,
    });

    const user = userEvent.setup();
    render(<ComparePage />);

    // Find the two checkboxes (one per lease).
    const checkboxA = screen.getByLabelText('Lease A') as HTMLInputElement;
    const checkboxB = screen.getByLabelText('Lease B') as HTMLInputElement;
    expect(checkboxA).not.toBeChecked();
    expect(checkboxB).not.toBeChecked();

    await user.click(checkboxA);
    await user.click(checkboxB);
    expect(checkboxA).toBeChecked();
    expect(checkboxB).toBeChecked();

    // Submit button must be enabled once 2+ leases are selected.
    const submit = screen.getByRole('button', { name: /compare selected/i });
    expect(submit).not.toBeDisabled();
    await user.click(submit);

    expect(compareMock).toHaveBeenCalledWith(['lease_a', 'lease_b']);
  });
});
