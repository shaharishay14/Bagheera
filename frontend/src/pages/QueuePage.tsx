import { useEffect, useRef, useState } from 'react';
import JobLogViewer from '../components/JobLogViewer';
import {
  ApiError,
  cancelJob,
  getQueue,
  reorderQueue,
  retryJob,
  type JobView,
  type QueueResponse,
} from '../lib/api';

const POLL_MS = 2000;

export default function QueuePage() {
  const [queue, setQueue] = useState<QueueResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [recentOpen, setRecentOpen] = useState(false);
  const [viewingLogFor, setViewingLogFor] = useState<string | null>(null);

  // Drag state. `order` is non-null only while a drag is in progress and holds
  // the optimistic ordering; the poll is frozen during that window so the row
  // under the cursor never jumps.
  const [dragId, setDragId] = useState<string | null>(null);
  const [order, setOrder] = useState<JobView[] | null>(null);
  const draggingRef = useRef(false);
  const originalIdsRef = useRef<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const res = await getQueue();
        if (cancelled) return;
        if (!draggingRef.current) {
          setQueue(res);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Failed to load the queue.');
        }
      }
      if (!cancelled) timer = window.setTimeout(poll, POLL_MS);
    };
    poll();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, []);

  const refresh = async () => {
    try {
      setQueue(await getQueue());
    } catch {
      /* next poll reconciles */
    }
  };

  // --- Drag-and-drop (native HTML5) ---------------------------------------

  const waiting = order ?? queue?.waiting ?? [];

  const onDragStart = (job: JobView) => {
    const base = queue?.waiting ?? [];
    originalIdsRef.current = base.map((j) => j.id);
    setDragId(job.id);
    setOrder([...base]);
    draggingRef.current = true;
  };

  const onDragOverRow = (e: React.DragEvent, target: JobView) => {
    if (!dragId) return;
    e.preventDefault();
    setOrder((prev) => moveBefore(prev ?? [], dragId, target.id));
  };

  const finishDrag = async () => {
    const current = order;
    const wasDragging = draggingRef.current;
    setDragId(null);
    setOrder(null);
    draggingRef.current = false;
    if (!wasDragging || !current) return;
    const ids = current.map((j) => j.id);
    if (sameOrder(ids, originalIdsRef.current)) {
      void refresh();
      return;
    }
    // Optimistically show the new order, then persist + reconcile.
    setQueue((q) => (q ? { ...q, waiting: current } : q));
    try {
      setQueue(await reorderQueue(ids));
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : 'Failed to save the new order.');
      void refresh();
    }
  };

  // --- Actions ------------------------------------------------------------

  const onCancel = async (id: string) => {
    setNotice(null);
    try {
      await cancelJob(id);
      await refresh();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setNotice('That job already started — it can no longer be canceled.');
      } else {
        setNotice(err instanceof ApiError ? err.message : 'Failed to cancel the job.');
      }
      await refresh();
    }
  };

  const onRerun = async (id: string) => {
    setNotice(null);
    try {
      await retryJob(id);
      await refresh();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : 'Failed to re-run the job.');
    }
  };

  // --- Render -------------------------------------------------------------

  const running = queue?.running ?? null;
  const recent = queue?.recent ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Queue</h2>
        <p className="text-sm text-slate-500">
          Jobs run one at a time on the GPU. Drag waiting jobs to reorder, or cancel them
          before they start. Shared across everyone using Bagheera.
        </p>
      </div>

      {error ? (
        <Banner tone="error" onDismiss={() => setError(null)}>
          {error}
        </Banner>
      ) : null}
      {notice ? (
        <Banner tone="warn" onDismiss={() => setNotice(null)}>
          {notice}
        </Banner>
      ) : null}

      {/* Now running */}
      <section>
        <SectionHeader title="Now running" />
        {running ? (
          <div className="mt-2 flex items-start justify-between gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <StatusBadge status={running.status} />
                <span className="truncate text-sm font-semibold text-slate-900">
                  {running.title}
                </span>
              </div>
              {running.subtitle ? (
                <p className="mt-0.5 text-xs text-slate-600">{running.subtitle}</p>
              ) : null}
              <p className="mt-1 text-[11px] text-slate-500">
                Started {fmtTime(running.started_at)} · running for {since(running.started_at)}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setViewingLogFor(running.id)}
              className="shrink-0 rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 hover:bg-slate-100"
            >
              log
            </button>
          </div>
        ) : (
          <p className="mt-2 rounded-lg border border-dashed border-slate-300 bg-white px-4 py-3 text-sm text-slate-500">
            Idle — nothing is running.
          </p>
        )}
      </section>

      {/* Waiting */}
      <section>
        <SectionHeader title={`Waiting (${waiting.length})`} />
        {waiting.length === 0 ? (
          <p className="mt-2 rounded-lg border border-dashed border-slate-300 bg-white px-4 py-3 text-sm text-slate-500">
            The queue is empty.
          </p>
        ) : (
          <ul className="mt-2 space-y-2">
            {waiting.map((job, i) => (
              <li
                key={job.id}
                draggable
                onDragStart={() => onDragStart(job)}
                onDragOver={(e) => onDragOverRow(e, job)}
                onDrop={(e) => e.preventDefault()}
                onDragEnd={finishDrag}
                className={`flex items-center gap-3 rounded-lg border bg-white p-3 shadow-sm ${
                  dragId === job.id
                    ? 'border-slate-400 opacity-60'
                    : 'border-slate-200 hover:border-slate-300'
                }`}
              >
                <span
                  className="cursor-grab select-none text-slate-400 active:cursor-grabbing"
                  title="Drag to reorder"
                  aria-hidden="true"
                >
                  ⠿
                </span>
                <span className="w-6 shrink-0 text-center font-mono text-xs text-slate-400">
                  {i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <StatusBadge status={job.status} />
                    <span className="truncate text-sm font-medium text-slate-900">
                      {job.title}
                    </span>
                  </div>
                  {job.subtitle ? (
                    <p className="mt-0.5 text-xs text-slate-500">{job.subtitle}</p>
                  ) : null}
                </div>
                <button
                  type="button"
                  onClick={() => setViewingLogFor(job.id)}
                  className="shrink-0 rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 hover:bg-slate-100"
                >
                  log
                </button>
                <button
                  type="button"
                  onClick={() => onCancel(job.id)}
                  className="shrink-0 rounded border border-rose-200 bg-white px-2 py-1 text-xs text-rose-700 hover:bg-rose-50"
                >
                  Cancel
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Recent */}
      <section>
        <button
          type="button"
          onClick={() => setRecentOpen((v) => !v)}
          className="flex w-full items-center justify-between text-left"
        >
          <SectionHeader title={`Recent (${recent.length})`} />
          <span className="text-xs text-slate-500">{recentOpen ? 'Hide' : 'Show'}</span>
        </button>
        {recentOpen ? (
          recent.length === 0 ? (
            <p className="mt-2 text-sm text-slate-500">No finished jobs yet.</p>
          ) : (
            <ul className="mt-2 divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
              {recent.map((job) => (
                <li key={job.id} className="flex items-center gap-3 px-3 py-2">
                  <StatusBadge status={job.status} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-slate-800">{job.title}</p>
                    <p className="text-[11px] text-slate-500">
                      {job.finished_at ? `finished ${fmtTime(job.finished_at)}` : ''}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setViewingLogFor(job.id)}
                    className="shrink-0 rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 hover:bg-slate-100"
                  >
                    log
                  </button>
                  {job.status === 'failed' || job.status === 'canceled' || job.status === 'succeeded' ? (
                    <button
                      type="button"
                      onClick={() => onRerun(job.id)}
                      className="shrink-0 rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 hover:bg-slate-100"
                    >
                      Re-run
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          )
        ) : null}
      </section>

      {viewingLogFor ? (
        <JobLogViewer jobId={viewingLogFor} onClose={() => setViewingLogFor(null)} />
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Move `id` so it sits at `target`'s current index. */
function moveBefore(list: JobView[], id: string, targetId: string): JobView[] {
  if (id === targetId) return list;
  const from = list.findIndex((j) => j.id === id);
  const to = list.findIndex((j) => j.id === targetId);
  if (from < 0 || to < 0) return list;
  const next = list.slice();
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  return next;
}

function sameOrder(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  return a.every((x, i) => x === b[i]);
}

function fmtTime(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleTimeString();
}

function since(iso: string | null): string {
  if (!iso) return '—';
  const secs = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ${secs % 60}s`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m`;
}

function SectionHeader({ title }: { title: string }) {
  return (
    <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
  );
}

function StatusBadge({ status }: { status: JobView['status'] }) {
  const tones: Record<JobView['status'], string> = {
    queued: 'bg-slate-100 text-slate-700 border-slate-200',
    running: 'bg-blue-50 text-blue-800 border-blue-200 animate-pulse',
    succeeded: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    failed: 'bg-rose-50 text-rose-800 border-rose-200',
    canceled: 'bg-amber-50 text-amber-800 border-amber-200',
  };
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${tones[status]}`}
    >
      {status}
    </span>
  );
}

function Banner({
  tone,
  onDismiss,
  children,
}: {
  tone: 'error' | 'warn';
  onDismiss: () => void;
  children: React.ReactNode;
}) {
  const cls =
    tone === 'error'
      ? 'border-rose-200 bg-rose-50 text-rose-800'
      : 'border-amber-200 bg-amber-50 text-amber-900';
  return (
    <div className={`flex items-start justify-between gap-3 rounded-md border px-4 py-3 text-sm ${cls}`}>
      <span>{children}</span>
      <button type="button" onClick={onDismiss} aria-label="Dismiss" className="opacity-60 hover:opacity-100">
        ×
      </button>
    </div>
  );
}
