/**
 * Canonical status pill — maps every status string in the system to a
 * semantic color. Use this instead of inlining status classes in pages.
 *
 * Covers:
 *   Job:       queued | running | succeeded | failed | canceled
 *   Model:     pending | running | ready | failed
 *   Inference: queued | running_trident | running_viz | ready | failed
 *   Viz:       pending | rendering | ready | failed
 */

type Status =
  | 'queued'
  | 'running'
  | 'running_trident'
  | 'running_viz'
  | 'succeeded'
  | 'ready'
  | 'failed'
  | 'canceled'
  | 'pending'
  | 'rendering'
  | string; // fallback for unknown

const TONES: Record<string, string> = {
  queued:          'bg-[var(--s-queued-bg)]   text-[var(--s-queued-text)]   border-[var(--s-queued-border)]',
  pending:         'bg-[var(--s-queued-bg)]   text-[var(--s-queued-text)]   border-[var(--s-queued-border)]',
  running:         'bg-[var(--s-running-bg)]  text-[var(--s-running-text)]  border-[var(--s-running-border)]  animate-pulse-slow',
  running_trident: 'bg-[var(--s-running-bg)]  text-[var(--s-running-text)]  border-[var(--s-running-border)]  animate-pulse-slow',
  running_viz:     'bg-[var(--s-rendering-bg)] text-[var(--s-rendering-text)] border-[var(--s-rendering-border)] animate-pulse-slow',
  rendering:       'bg-[var(--s-rendering-bg)] text-[var(--s-rendering-text)] border-[var(--s-rendering-border)] animate-pulse-slow',
  succeeded:       'bg-[var(--s-success-bg)]  text-[var(--s-success-text)]  border-[var(--s-success-border)]',
  ready:           'bg-[var(--s-success-bg)]  text-[var(--s-success-text)]  border-[var(--s-success-border)]',
  failed:          'bg-[var(--s-failed-bg)]   text-[var(--s-failed-text)]   border-[var(--s-failed-border)]',
  canceled:        'bg-[var(--s-warn-bg)]     text-[var(--s-warn-text)]     border-[var(--s-warn-border)]',
};

interface Props {
  status: Status;
  label?: string;
  className?: string;
}

export default function StatusPill({ status, label, className = '' }: Props) {
  const tone = TONES[status] ?? TONES['queued'];
  const display = label ?? status.replace(/_/g, ' ');
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${tone} ${className}`}
    >
      {display}
    </span>
  );
}
