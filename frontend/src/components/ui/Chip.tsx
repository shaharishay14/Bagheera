import type { ReactNode } from 'react';

interface Props {
  children: ReactNode;
  mono?: boolean;
  className?: string;
}

/**
 * Inline metadata chip — dataset name, encoder, etc.
 */
export default function Chip({ children, mono = false, className = '' }: Props) {
  return (
    <span
      className={`inline-flex items-center rounded-full border border-border bg-surface-subtle px-2.5 py-0.5 text-xs text-ink-muted ${mono ? 'font-mono' : ''} ${className}`}
    >
      {children}
    </span>
  );
}
