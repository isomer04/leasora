import { CheckCircle2 } from 'lucide-react';
import { Card, CardContent, CardHeader } from '@/components/ui';

const whyLeasora = [
  'Fast: Analyze documents in seconds, not hours',
  'Accurate: AI-powered classification and extraction',
  'Secure: Your documents remain private and encrypted',
  'Intelligent: Ask questions and get contextual answers',
];

export default function AboutPage() {
  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
      <h1 className="text-4xl font-bold mb-8 text-ink-primary">About Leasora</h1>

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <h2 className="text-2xl font-bold text-ink-primary">Our Mission</h2>
          </CardHeader>
          <CardContent>
            <p className="text-lg text-ink-secondary">
              Leasora makes lease analysis accessible to everyone. By leveraging AI and RAG
              (Retrieval-Augmented Generation), we help you understand lease agreements faster, reduce
              risk, and make better decisions.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <h2 className="text-2xl font-bold text-ink-primary">How It Works</h2>
          </CardHeader>
          <CardContent>
            <p className="text-lg text-ink-secondary mb-4">
              Upload your lease documents, and our AI engine will automatically:
            </p>
            <ul className="list-disc list-inside space-y-2 text-ink-secondary ml-4">
              <li>Extract and classify key clauses</li>
              <li>Identify important signals and risks</li>
              <li>Answer your specific questions about terms</li>
              <li>Compare multiple leases side-by-side</li>
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <h2 className="text-2xl font-bold text-ink-primary">Why Leasora?</h2>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              {whyLeasora.map((line) => (
                <li key={line} className="flex items-start gap-3">
                  <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-success/10 text-success">
                    <CheckCircle2 size={14} strokeWidth={1.75} aria-hidden="true" />
                  </div>
                  <span className="text-ink-secondary">{line}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
