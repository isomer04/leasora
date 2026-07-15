import Link from 'next/link';
import { CheckCircle2 } from 'lucide-react';
import { Badge, Card, CardContent, CardFooter, CardHeader } from '@/components/ui';
import { cn } from '@/lib/utils';

// Static plan data — restyling only.
const plans = [
  {
    name: 'Starter',
    price: '$29',
    description: 'Perfect for individuals',
    features: ['Up to 10 leases', 'Basic analysis', 'Email support'],
    highlighted: false,
  },
  {
    name: 'Professional',
    price: '$99',
    description: 'For small teams',
    features: ['Up to 100 leases', 'Advanced analysis', 'Priority support', 'Team collaboration'],
    highlighted: true,
  },
  {
    name: 'Enterprise',
    price: 'Custom',
    description: 'For large organizations',
    features: ['Unlimited leases', 'Custom integrations', 'Dedicated support', 'SLA guarantee'],
    highlighted: false,
  },
];

const primaryButtonClasses = cn(
  'inline-flex w-full items-center justify-center rounded-md bg-brand-500 px-4 py-2 font-semibold !text-black',
  'transition-colors duration-150 hover:bg-brand-400 active:bg-brand-700 active:!text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400'
);
const outlineButtonClasses = cn(
  'inline-flex w-full items-center justify-center rounded-md border border-border-strong px-4 py-2 font-semibold text-ink-primary',
  'transition-colors duration-150 hover:bg-surface-overlay focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400'
);

export default function PricingPage() {
  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
      <h1 className="text-4xl font-bold text-center mb-4 text-ink-primary">Simple, Transparent Pricing</h1>
      <p className="text-center text-ink-secondary mb-12 text-lg">Choose the plan that fits your needs</p>

      <div className="grid md:grid-cols-3 gap-8">
        {plans.map((plan) => (
          <Card
            key={plan.name}
            className={cn(
              'flex flex-col',
              plan.highlighted && 'border-2 border-brand-500 shadow-elevation-3'
            )}
          >
            <CardHeader>
              {plan.highlighted && (
                <Badge status="info" className="mb-4 w-fit">
                  Most Popular
                </Badge>
              )}
              <h3 className="text-2xl font-bold text-ink-primary">{plan.name}</h3>
              <p className="mt-1 text-ink-secondary">{plan.description}</p>
              <div className="mt-6">
                <span className="font-tabular text-4xl font-bold text-ink-primary">{plan.price}</span>
                {plan.price !== 'Custom' && <span className="text-ink-secondary">/month</span>}
              </div>
            </CardHeader>
            <CardContent className="flex-1">
              <ul className="space-y-3">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-start gap-3">
                    <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-success/10 text-success">
                      <CheckCircle2 size={14} strokeWidth={1.75} aria-hidden="true" />
                    </div>
                    <span className="text-ink-secondary">{feature}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
            <CardFooter>
              <Link
                href="/dashboard"
                className={plan.highlighted ? primaryButtonClasses : outlineButtonClasses}
              >
                Get Started
              </Link>
            </CardFooter>
          </Card>
        ))}
      </div>
    </div>
  );
}
