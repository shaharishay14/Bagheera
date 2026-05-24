import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { ApiError, getJob, type JobDetail } from '../lib/api';

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
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-6 backdrop-blur-sm"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Job log"
        onClick={(e) => e.stopPropagation()}
        className="flex h-[80vh] w-[900px] max-w-[95vw] flex-col overflow-hidden rounded-lg bg-white shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-slate-900">Job log</p>
            <p className="truncate font-mono text-[11px] text-slate-500">
              {data
                ? `${data.job_type} · ${data.status} · ${jobId}`
                : jobId}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 hover:bg-slate-100"
          >
            Close ✕
          </button>
        </div>
        <div className="flex-1 overflow-auto bg-slate-950 p-4">
          {error ? (
            <p className="text-xs text-rose-300">{error}</p>
          ) : data ? (
            <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-slate-100">
              {data.log_tail || '(no log output yet)'}
            </pre>
          ) : (
            <p className="text-xs text-slate-400">Loading log…</p>
          )}
        </div>
        {data?.error_message ? (
          <div className="border-t border-rose-200 bg-rose-50 px-5 py-3 text-xs text-rose-800">
            <span className="font-semibold">error_message:</span>{' '}
            <span className="font-mono">{data.error_message}</span>
          </div>
        ) : null}
      </div>
    </div>,
    document.body
  );
}
