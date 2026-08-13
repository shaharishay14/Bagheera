import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

type Variant = 'filled' | 'outline';

interface Props {
  to: string;
  children: ReactNode;
  variant?: Variant;
  className?: string;
}

const VARIANTS: Record<Variant, string> = {
  filled:
    'bg-accent text-ink shadow-glow hover:bg-accent-dark hover:shadow-glow-lg hover:-translate-y-0.5',
  outline:
    'bg-surface text-ink border border-border-strong hover:border-accent hover:text-accent-text hover:-translate-y-0.5',
};

/**
 * Filled orange pill CTA link — the primary call-to-action on the landing page.
 */
export default function CTAButton({ to, children, variant = 'filled', className = '' }: Props) {
  return (
    <Link
      to={to}
      className={`inline-flex items-center justify-center gap-2 rounded-full px-7 py-3 text-sm font-semibold transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 ${VARIANTS[variant]} ${className}`}
    >
      {children}
    </Link>
  );
}
