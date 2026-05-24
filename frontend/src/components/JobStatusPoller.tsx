import { useEffect, useRef, useState } from 'react';
import { ApiError, listJobs, type JobInfo } from '../lib/api';
import JobLogViewer from './JobLogViewer';

interface Props {
  /** Polls /api/jobs?ref_id=… for this group's training + viz jobs. */
  refId: string;
  refTable?: string;
  /** Stop polling once all jobs are in a terminal state (default: true). */
  stopWhenIdle?: boolean;
  /** Notification when a job moves to succeeded/failed. */
  onJobFinished?: (job: JobInfo) => void;
  /** Polling cadence in ms (default 2000). */
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
        // Fire onJobFinished for jobs whose status changed to a terminal value.
        for (const j of res) {
          const prev = previousStatuses.current.get(j.id);
          if (prev !== j.status && (j.status === 'succeeded' || j.status === 'failed')) {
            onJobFinished?.(j);
          }
          previousStatuses.current.set(j.id, j.status);
        }
        const allIdle = res.every(
          (j) => j.status === 'succeeded' || j.status === 'failed'
        );
        if (stopWhenIdle && res.length > 0 && allIdle) {
          return; // exit loop
        }
      } catch (err) {
        if (!cancelled) {
          const msg = err instanceof ApiError ? err.message : 'Failed to poll jobs.';
          setError(msg);
        }
      }
      if (!cancelled) {
        timer = window.setTimeout(poll, intervalMs);
      }
    };
    poll();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [refId, refTable, stopWhenIdle, intervalMs, onJobFinished]);

  if (error) {
    return (
      <p className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800">
        {error}
      </p>
    );
  }
  if (jobs.length === 0) {
    return null;
  }
  return (
    <>
      <ul className="space-y-1 text-xs">
        {jobs.map((j) => (
          <li key={j.id} className="flex items-center justify-between gap-2">
            <span className="font-mono text-slate-700">{j.job_type}</span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setViewingLogFor(j.id)}
                className="text-[11px] text-slate-500 underline hover:text-slate-900"
                title="View log tail"
              >
                log
              </button>
              <StatusBadge status={j.status} />
            </div>
          </li>
        ))}
      </ul>
      {viewingLogFor ? (
        <JobLogViewer
          jobId={viewingLogFor}
          onClose={() => setViewingLogFor(null)}
        />
      ) : null}
    </>
  );
}

function StatusBadge({ status }: { status: JobInfo['status'] }) {
  const tones: Record<JobInfo['status'], string> = {
    queued: 'bg-slate-100 text-slate-700 border-slate-200',
    running: 'bg-blue-50 text-blue-800 border-blue-200 animate-pulse',
    succeeded: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    failed: 'bg-rose-50 text-rose-800 border-rose-200',
  };
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${tones[status]}`}
    >
      {status}
    </span>
  );
}
