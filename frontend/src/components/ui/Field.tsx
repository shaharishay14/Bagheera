import type { ReactNode } from 'react';

interface Props {
  label: string;
  htmlFor?: string;
  hint?: string;
  children: ReactNode;
}

/**
 * Form field wrapper — uppercase tracking label + optional hint line.
 */
export default function Field({ label, htmlFor, hint, children }: Props) {
  return (
    <div>
      <label
        htmlFor={htmlFor}
        className="mb-1 block text-xs font-semibold uppercase tracking-wide text-ink-muted"
      >
        {label}
      </label>
      {children}
      {hint ? <p className="mt-1 text-xs text-ink-faint">{hint}</p> : null}
    </div>
  );
}

/** Shared class string for text/number/select inputs. */
export const inputCls = (error?: boolean) =>
  `block w-full rounded-md border bg-surface px-3 py-2 text-sm font-mono shadow-inner-sm transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-0 ${
    error
      ? 'border-[var(--s-failed-border)] focus:border-[var(--s-failed-text)]'
      : 'border-border-strong focus:border-accent'
  }`;
