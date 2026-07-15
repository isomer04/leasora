import { describe, expect, it, vi, beforeEach } from 'vitest';
import { Suspense } from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import AskPage from './page';
import * as api from '@/lib/api';

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof api>('@/lib/api');
  return {
    ...actual,
    askQuestion: vi.fn(),
  };
});

// AskPage uses `use(params)` (React 19) which requires Suspense.
// jsdom doesn't flush Suspense on the initial render the way browsers do,
// so we render inside act() and wait for a microtask flush before
// continuing. The pattern below is the one documented in the React 19
// testing notes for `use()` of resolved promises in jsdom.
const renderAsk = async () => {
  let utils!: ReturnType<typeof render>;
  await act(async () => {
    utils = render(
      <Suspense fallback={<div>loading</div>}>
        <AskPage params={Promise.resolve({ id: 'lease_demo' })} />
      </Suspense>
    );
  });
  await waitFor(() => {
    expect(
      screen.getByRole('heading', { name: /ask about this lease/i })
    ).toBeInTheDocument();
  });
  return utils;
};

describe('AskPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the heading and example questions', async () => {
    await renderAsk();

    expect(
      screen.getByRole('heading', { name: /ask about this lease/i })
    ).toBeInTheDocument();

    // Common-question cards render as buttons; assert at least one is
    // visible so we know the section mounted.
    expect(
      screen.getByRole('button', { name: /what is the lease term/i })
    ).toBeInTheDocument();
  });

  it('submitting a question calls askQuestion and renders the answer', async () => {
    vi.mocked(api.askQuestion).mockResolvedValue({
      data: {
        answer: 'Rent is due on the first of each month.',
        sources: [
          {
            clause_id: 'chunk-0',
            clause_type: 'rental_term',
            excerpt: 'Rent is due on the first day of each month.',
          },
        ],
        confidence: 0.9,
      },
      status: 200,
    } as Awaited<ReturnType<typeof api.askQuestion>>);

    const user = userEvent.setup();
    await renderAsk();

    const textarea = screen.getByLabelText(/your question/i);
    await user.type(textarea, 'When is rent due?');

    const submit = screen.getByRole('button', { name: /get answer/i });
    await user.click(submit);

    await waitFor(() => {
      expect(
        screen.getByText('Rent is due on the first of each month.')
      ).toBeInTheDocument();
    });
    // The source clause must also render.
    expect(screen.getByText('chunk-0')).toBeInTheDocument();
    expect(api.askQuestion).toHaveBeenCalledWith('lease_demo', 'When is rent due?');
  });

  it('renders the signal badge and verbatim quote when the API returns them', async () => {
    vi.mocked(api.askQuestion).mockResolvedValue({
      data: {
        answer: 'The lease allows the landlord to enter with only 1 hour notice.',
        sources: [],
        confidence: 0.95,
        quote: 'Landlord may enter the premises upon one (1) hour notice.',
        signal: 'red_flag',
      },
      status: 200,
    } as Awaited<ReturnType<typeof api.askQuestion>>);

    const user = userEvent.setup();
    await renderAsk();

    await user.type(screen.getByLabelText(/your question/i), 'Can the landlord enter without notice?');
    await user.click(screen.getByRole('button', { name: /get answer/i }));

    await waitFor(() => {
      expect(screen.getByText('Red Flag')).toBeInTheDocument();
    });
    expect(
      screen.getByText('“Landlord may enter the premises upon one (1) hour notice.”')
    ).toBeInTheDocument();
  });

  it('shows an error message when askQuestion fails', async () => {
    vi.mocked(api.askQuestion).mockRejectedValue(new Error('upstream down'));
    // The page logs to console.error when askQuestion fails. Silence it
    // so the test output stays clean — the error is the expected outcome.
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const user = userEvent.setup();
    await renderAsk();

    await user.type(screen.getByLabelText(/your question/i), 'When is rent due?');
    await user.click(screen.getByRole('button', { name: /get answer/i }));

    await waitFor(() => {
      expect(screen.getByText('upstream down')).toBeInTheDocument();
    });
    errSpy.mockRestore();
  });
});