'use client';

import { FormEvent, useRef, useState, use } from 'react';
import Link from 'next/link';
import { AlertCircle, ArrowLeft, HelpCircle, Quote } from 'lucide-react';
import { Badge, Button, Card, Textarea, type BadgeStatus } from '@/components/ui';
import { MotionList, MotionListItem } from '@/components/motion';
import { askQuestion } from '@/lib/api';
import type { AskResponse, SignalLabel, SourceReference } from '@leasora/shared-types';

interface Exchange {
  id: string;
  question: string;
  answer: string;
  sources: SourceReference[];
  confidence: number;
  quote: string | null;
  signal: SignalLabel | null;
}

// How each signal compares to standard lease practice, per SignalLabel in
// the API schema — surfaced so the badge reflects the same taxonomy the
// LLM was asked to classify against, not an ad-hoc UI-only label set.
const SIGNAL_CONFIG: Record<SignalLabel, { label: string; status: BadgeStatus }> = {
  standard: { label: 'Standard', status: 'neutral' },
  tenant_friendly: { label: 'Tenant-Friendly', status: 'success' },
  landlord_friendly: { label: 'Landlord-Friendly', status: 'warning' },
  unusual: { label: 'Unusual', status: 'warning' },
  red_flag: { label: 'Red Flag', status: 'danger' },
};

const COMMON_QUESTIONS = [
  'What is the lease term and renewal conditions?',
  'What are the maintenance responsibilities?',
  'Can the tenant assign or sublet?',
  'What are the termination conditions?',
  'What insurance is required?',
  'What are the late payment penalties?',
];

export default function LeaseAskPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [question, setQuestion] = useState('');
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const threadEndRef = useRef<HTMLDivElement>(null);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const submittedQuestion = question.trim();
    if (!submittedQuestion) return;

    setLoading(true);
    setError('');

    try {
      const response = await askQuestion(id, submittedQuestion);

      if (response.error) {
        throw new Error(response.error.detail);
      }

      const data = response.data;
      if (!data) {
        throw new Error('No answer returned. Please try again.');
      }

      const exchange: Exchange = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        question: submittedQuestion,
        answer: data.answer,
        sources: data.sources ?? [],
        confidence: data.confidence ?? 0,
        quote: data.quote ?? null,
        signal: data.signal ?? null,
      };

      setExchanges((prev) => [...prev, exchange]);
      setQuestion('');
      // Scroll to the new answer after state update. Optional-chain the
      // method too — jsdom doesn't implement Element#scrollIntoView, and
      // the ref may unmount before the timer fires.
      setTimeout(() => threadEndRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' }), 50);
    } catch (err) {
      console.error('Error calling ask API:', err);
      setError(err instanceof Error ? err.message : 'Failed to get answer. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex h-[calc(100dvh-8rem)] min-h-112 flex-col overflow-hidden">
      {/* Header */}
      <div className="shrink-0 pb-6">
        <Link
          href={`/leases/${id}`}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-secondary hover:text-ink-primary"
        >
          <ArrowLeft size={16} strokeWidth={1.75} aria-hidden="true" />
          Back to Lease
        </Link>
        <h1 className="mt-4 text-4xl font-bold text-ink-primary">Ask About This Lease</h1>
        <p className="mt-2 text-ink-secondary">
          Use AI to find specific information in the lease agreement
        </p>
      </div>

      {/* Scrollable conversation */}
      <div className="min-h-0 flex-1 space-y-8 overflow-y-auto overscroll-contain pb-6 pr-1">
      {exchanges.length > 0 && (
        <MotionList as="div" className="space-y-6">
          {exchanges.map((exchange) => (
            <MotionListItem key={exchange.id} as="div" className="space-y-3">
              {/* Question bubble */}
              <div className="flex justify-end">
                <div className="max-w-[75%] rounded-lg bg-surface-overlay px-4 py-3 text-ink-primary">
                  <p className="leading-relaxed">{exchange.question}</p>
                </div>
              </div>

              {/* Answer bubble */}
              <div className="flex justify-start">
                <Card className="w-full max-w-[85%] border-l-4 border-l-brand-500">
                  <div className="mb-3 flex items-start justify-between gap-4">
                    <h2 className="text-lg font-bold text-ink-primary">Answer</h2>
                    <div className="flex shrink-0 items-center gap-2">
                      {exchange.signal && SIGNAL_CONFIG[exchange.signal] && (
                        <Badge status={SIGNAL_CONFIG[exchange.signal].status}>
                          {SIGNAL_CONFIG[exchange.signal].label}
                        </Badge>
                      )}
                      <Badge status="info">{Math.round((exchange.confidence ?? 0) * 100)}% confident</Badge>
                    </div>
                  </div>
                  <p className="leading-relaxed text-ink-secondary">{exchange.answer}</p>

                  {exchange.quote && (
                    <blockquote className="mt-4 flex gap-2 rounded-md border-l-4 border-l-brand-300 bg-surface-overlay/50 px-4 py-3">
                      <Quote size={16} strokeWidth={1.75} className="mt-0.5 shrink-0 text-ink-muted" aria-hidden="true" />
                      <p className="italic leading-relaxed text-ink-secondary">&ldquo;{exchange.quote}&rdquo;</p>
                    </blockquote>
                  )}

                  {exchange.sources.length > 0 && (
                    <div className="mt-6 border-t border-border-subtle pt-6">
                      <h3 className="mb-3 font-bold text-ink-primary">Source Clauses</h3>
                      <div className="space-y-3">
                        {exchange.sources.map((source) => (
                          <Card key={source.clause_id} className="p-4">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="font-medium text-ink-primary">{source.clause_id}</span>
                              <Badge status="neutral" size="sm">
                                {source.clause_type}
                              </Badge>
                            </div>
                            <p className="text-sm text-ink-secondary">{source.excerpt}</p>
                          </Card>
                        ))}
                      </div>
                    </div>
                  )}
                </Card>
              </div>
            </MotionListItem>
          ))}
        </MotionList>
      )}
      {/* Scroll anchor — scrolled into view after each new answer */}
      <div ref={threadEndRef} />

      {/* Example Questions */}
      <div>
        <h2 className="mb-4 text-2xl font-bold text-ink-primary">Common Questions</h2>
        <div className="grid gap-4 md:grid-cols-2">
          {COMMON_QUESTIONS.map((q, idx) => (
            <Card
              key={idx}
              variant="interactive"
              role="button"
              tabIndex={0}
              onClick={() => setQuestion(q)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  setQuestion(q);
                }
              }}
              className="focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
            >
              <div className="flex items-start gap-3">
                <HelpCircle size={20} strokeWidth={1.75} className="mt-0.5 shrink-0 text-brand-400" aria-hidden="true" />
                <p className="font-medium text-ink-primary">{q}</p>
              </div>
            </Card>
          ))}
        </div>
      </div>
      </div>

      {/* Bottom composer — remains visible while the conversation scrolls. */}
      <div className="shrink-0 border-t border-border-subtle bg-surface-base pt-4">
        <Card className="shadow-elevation-2">
          <form onSubmit={handleSubmit} className="space-y-4">
            <Textarea
              id="question"
              label="Your Question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g., What are the maintenance responsibilities? Who pays for repairs?"
              required
              rows={3}
            />

            {error && (
              <div className="flex items-start gap-2 rounded-md border border-danger/30 bg-danger/10 p-3 text-danger">
                <AlertCircle size={18} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden="true" />
                <p>{error}</p>
              </div>
            )}

            <div className="flex justify-end">
              <Button type="submit" disabled={loading || !question.trim()} isLoading={loading}>
                Get Answer
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </div>
  );
}
