import type { ReactNode } from 'react';

interface Props {
  children: ReactNode;
  className?: string;
  hover?: boolean;
}

/**
 * Standard surface card — bg-surface, border-border, shadow-card.
 * Pass `hover` for the clickable/linked card variant with shadow-card-hover.
 */
export default function Card({ children, className = '', hover = false }: Props) {
  return (
    <div
      className={`rounded-xl border border-border bg-surface shadow-card ${
        hover ? 'transition-all duration-200 hover:-translate-y-0.5 hover:border-accent/30 hover:shadow-card-hover' : ''
      } ${className}`}
    >
      {children}
    </div>
  );
}
