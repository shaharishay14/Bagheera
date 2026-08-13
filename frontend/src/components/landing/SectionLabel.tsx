import type { ReactNode } from 'react';

interface Props {
  children: ReactNode;
  className?: string;
}

/**
 * Small-caps, letter-spaced muted label that sits above section headings.
 * The veto-style eyebrow text.
 */
export default function SectionLabel({ children, className = '' }: Props) {
  return (
    <span
      className={`inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-ink-faint ${className}`}
    >
      <span className="h-px w-6 bg-accent" aria-hidden />
      {children}
    </span>
  );
}
