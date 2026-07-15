import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import UploadPage from './page';
import * as api from '@/lib/api';

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof api>('@/lib/api');
  return {
    ...actual,
    uploadLeaseWithProgress: vi.fn(),
  };
});

describe('UploadPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the heading and the drag-and-drop upload zone', () => {
    render(<UploadPage />);

    expect(
      screen.getByRole('heading', { name: /upload lease/i })
    ).toBeInTheDocument();

    // The hidden <input type=file> must be present.
    const fileInput = document.querySelector('input[type="file"]');
    expect(fileInput).toBeInTheDocument();
  });

  it('rejects a non-PDF file selection', async () => {
    const user = userEvent.setup();
    render(<UploadPage />);

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    const txt = new File(['hello'], 'lease.txt', { type: 'text/plain' });
    // user.upload skips files that violate the input's `accept` attribute,
    // so we bypass that filter by calling the change handler directly.
    fireEvent.change(fileInput, { target: { files: [txt] } });

    // The error lives inside a <p>, so use a function matcher that's
    // resilient to surrounding markup.
    expect(
      screen.getByText((content, element) => {
        return (
          element?.tagName.toLowerCase() === 'p' &&
          /please upload a pdf file/i.test(content)
        );
      })
    ).toBeInTheDocument();
  });

  it('submits the form and shows the success state when upload succeeds', async () => {
    vi.mocked(api.uploadLeaseWithProgress).mockImplementation((_form, onProgress) => {
      onProgress?.(100);
      return {
        promise: Promise.resolve({
          data: {
            lease_id: 'lease_xyz123',
            name: 'Test Lease',
            status: 'complete',
            message: 'ok',
          },
          status: 200,
        }),
        abort: vi.fn(),
      };
    });

    const user = userEvent.setup();
    render(<UploadPage />);

    // Drop in a valid PDF.
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    const pdf = new File(['%PDF-1.4'], 'demo.pdf', { type: 'application/pdf' });
    await user.upload(fileInput, pdf);

    // Fill the required name field.
    const nameInput = screen.getByLabelText(/lease name/i);
    await user.type(nameInput, 'Test Lease');

    await user.click(screen.getByRole('button', { name: /upload lease/i }));

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /upload received/i })
      ).toBeInTheDocument();
    });
    expect(api.uploadLeaseWithProgress).toHaveBeenCalled();
  });
});