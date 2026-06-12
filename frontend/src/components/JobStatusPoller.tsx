import { useEffect, useRef, useState } from 'react';
import { ApiError, listJobs, type JobInfo } from '../lib/api';
import { StatusPill } from './ui';
import JobLogViewer from './JobLogViewer';

interface Props {
  refId: string;
  refTable?: string;
  stopWhenIdle?: boolean;
  onJobFinished?: (job: JobInfo) => void;
  intervalMs?: number;
}

export default function JobStatusPoller({
  refId,
  refTable,
  stopWhenIdle = true,
  onJobFinished,
  intervalMs = 2000,
}: Props) {
  const [jobs, setJobs] = useState<JobInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [viewingLogFor, setViewingLogFor] = useState<string | null>(null);
  const previousStatuses = useRef<Map<string, string>>(new Map());

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const poll = async () => {
      try {
        const res = await listJobs({ refId, refTable, limit: 50 });
        if (cancelled) return;
        setJobs(res);
        setError(null);
        for (const j of res) {
          const prev = previousStatuses.current.get(j.id);
          if (prev !== j.status && (j.status === 'succeeded' || j.status === 'failed')) {
            onJobFinished?.(j);
          }
          previousStatuses.current.set(j.id, j.status);
        }
        const allIdle = res.every((j) => j.status === 'succeeded' || j.status === 'failed');
        if (stopWhenIdle && res.length > 0 && allIdle) return;
      } catch (err) {
        if (!cancelled) {
          const msg = err instanceof ApiError ? err.message : 'Failed to poll jobs.';
          setError(msg);
        }
      }
      if (!cancelled) timer = window.setTimeout(poll, intervalMs);
    };
    poll();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [refId, refTable, stopWhenIdle, intervalMs, onJobFinished]);

  if (error) {
    return (
      <p className="rounded-md border border-[var(--s-failed-border)] bg-[var(--s-failed-bg)] px-3 py-2 text-xs text-[var(--s-failed-text)]">
        {error}
      </p>
    );
  }
  if (jobs.length === 0) return null;

  return (
    <>
      <ul className="space-y-1 text-xs">
        {jobs.map((j) => (
          <li key={j.id} className="flex items-center justify-between gap-2">
            <span className="font-mono text-ink-muted">{j.job_type}</span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setViewingLogFor(j.id)}
                className="text-[11px] text-ink-faint underline hover:text-ink transition-colors"
                title="View log tail"
              >
                log
              </button>
              <StatusPill status={j.status} />
            </div>
          </li>
        ))}
      </ul>
      {viewingLogFor ? (
        <JobLogViewer jobId={viewingLogFor} onClose={() => setViewingLogFor(null)} />
      ) : null}
    </>
  );
}
