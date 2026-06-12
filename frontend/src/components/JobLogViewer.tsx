import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { ApiError, getJob, type JobDetail } from '../lib/api';
import { StatusPill } from './ui';

interface Props {
  jobId: string;
  onClose: () => void;
}

/**
 * Modal that displays the job's `log_tail` (last ~8000 chars per the backend).
 * Re-fetches every 2s while the job is still in flight so the viewer feels
 * live; stops polling once the job hits a terminal state.
 */
export default function JobLogViewer({ jobId, onClose }: Props) {
  const [data, setData] = useState<JobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const poll = async () => {
      try {
        const res = await getJob(jobId);
        if (cancelled) return;
        setData(res);
        setError(null);
        if (res.status === 'queued' || res.status === 'running') {
          timer = window.setTimeout(poll, 2000);
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : 'Failed to load log.');
        timer = window.setTimeout(poll, 4000);
      }
    };
    poll();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);

    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
      window.removeEventListener('keydown', onKey);
    };
  }, [jobId, onClose]);

  return createPortal(
    <div
      role="presentation"
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/60 p-6 backdrop-blur-sm"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Job log"
        onClick={(e) => e.stopPropagation()}
        className="flex h-[80vh] w-[900px] max-w-[95vw] flex-col overflow-hidden rounded-2xl bg-surface shadow-modal"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <div className="min-w-0 flex items-center gap-3">
            {data ? <StatusPill status={data.status} /> : null}
            <div className="min-w-0">
              <p className="text-sm font-semibold text-ink">Job log</p>
              <p className="truncate font-mono text-[11px] text-ink-faint">
                {data
                  ? `${data.job_type} · ${jobId}`
                  : jobId}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-border bg-surface px-2 py-1 text-xs text-ink hover:bg-surface-subtle transition-colors"
          >
            Close ✕
          </button>
        </div>

        {/* Log body */}
        <div className="flex-1 overflow-auto bg-ink p-4">
          {error ? (
            <p className="text-xs text-[var(--s-failed-text)]">{error}</p>
          ) : data ? (
            <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-surface/90">
              {data.log_tail || '(no log output yet)'}
            </pre>
          ) : (
            <p className="text-xs text-ink-faint/70">Loading log…</p>
          )}
        </div>

        {/* Error message footer */}
        {data?.error_message ? (
          <div className="border-t border-[var(--s-failed-border)] bg-[var(--s-failed-bg)] px-5 py-3 text-xs text-[var(--s-failed-text)]">
            <span className="font-semibold">error_message:</span>{' '}
            <span className="font-mono">{data.error_message}</span>
          </div>
        ) : null}
      </div>
    </div>,
    document.body
  );
}
