import { useEffect, useState } from 'react';
import { FiLoader, FiAlertTriangle } from 'react-icons/fi';
import JobStatusPoller from './JobStatusPoller';
import SectionAPanel from './SectionAPanel';
import SectionCPanel from './SectionCPanel';
import SectionDPanel from './SectionDPanel';
import ViolinPanel from './ViolinPanel';
import { Card, Chip, StatusPill } from './ui';
import { type Transform } from './ZoomPanImage';
import {
  ApiError,
  getSlideViz,
  renderSlide,
  type JobInfo,
  type ModelInfo,
  type SlideVizArtifacts,
} from '../lib/api';

/**
 * Render-slide lifecycle for one model + slide:
 *   idle       → no slide chosen yet
 *   loading    → POST render-slide in flight
 *   rendering  → a render job was queued; poll slide-viz until ready
 *   ready      → manifest artifacts available
 *   error      → render failed / job failed / still missing
 */
type PanelState = 'idle' | 'loading' | 'rendering' | 'ready' | 'error';

interface Props {
  model: ModelInfo;
  slideId: string | null;
  /** Controlled pan/zoom shared across panels; only applied when `syncEnabled`. */
  syncTransform?: Transform;
  onSyncTransformChange?: (t: Transform) => void;
  syncEnabled: boolean;
}

/**
 * One column of the Model Comparison grid: renders a chosen slide through a
 * single model's paper-style panels. The per-slide A / on-tissue / violin come
 * from the slide's render-slide MANIFEST (arbitrary slide); Section D (the
 * prototype dictionary) is global to the model and needs no slide.
 */
export default function CompareModelPanel({
  model,
  slideId,
  syncTransform,
  onSyncTransformChange,
  syncEnabled,
}: Props) {
  const [state, setState] = useState<PanelState>(slideId ? 'loading' : 'idle');
  const [artifacts, setArtifacts] = useState<SlideVizArtifacts | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Bumped by the Retry button to re-run the kickoff effect.
  const [retryKey, setRetryKey] = useState(0);

  // Kickoff: POST render-slide. Cache hit → ready; queued → rendering (poll).
  useEffect(() => {
    if (!slideId) {
      setState('idle');
      setArtifacts(null);
      setJobId(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setState('loading');
    setArtifacts(null);
    setJobId(null);
    setError(null);
    (async () => {
      try {
        const res = await renderSlide(model.id, slideId);
        if (cancelled) return;
        if (res.status === 'ready') {
          setArtifacts(res.artifacts);
          setState('ready');
        } else {
          setJobId(res.job_id);
          setState('rendering');
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : 'Failed to render this slide.');
        setState('error');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [model.id, slideId, retryKey]);

  // Poll slide-viz while a render job is in flight; flip to ready on cache hit.
  useEffect(() => {
    if (state !== 'rendering' || !slideId) return;
    let cancelled = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const res = await getSlideViz(model.id, slideId);
        if (cancelled) return;
        if (res.status === 'ready') {
          setArtifacts(res.artifacts);
          setState('ready');
          return;
        }
      } catch {
        // Transient poll error — keep trying; a failed job is caught below.
      }
      if (!cancelled) timer = window.setTimeout(poll, 2000);
    };
    timer = window.setTimeout(poll, 2000);
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [state, model.id, slideId]);

  // A failed render job (matched by id) ends the wait with an error.
  const onJobFinished = (job: JobInfo) => {
    if (job.id !== jobId) return;
    if (job.status === 'failed') {
      setError('The render job failed for this slide.');
      setState('error');
    }
    // succeeded → the slide-viz poll transitions us to ready.
  };

  const retry = () => {
    setRetryKey((k) => k + 1);
  };

  const transformFor = syncEnabled ? syncTransform : undefined;
  const onTransformFor = syncEnabled ? onSyncTransformChange : undefined;

  return (
    <Card className="flex flex-col overflow-hidden">
      {/* Header chip — model identity + status. */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border bg-surface-subtle px-4 py-3">
        <span className="min-w-0 flex-1 truncate text-sm font-bold text-ink" title={model.display_name}>
          {model.display_name || model.base_name}
        </span>
        <Chip mono>{model.dataset_name}</Chip>
        <StatusPill status={model.status} />
      </div>

      <div className="p-4">
        {state === 'idle' ? (
          <Prompt>Choose a slide above to render this model.</Prompt>
        ) : state === 'loading' || state === 'rendering' ? (
          <RenderingState modelId={model.id} onJobFinished={onJobFinished} />
        ) : state === 'error' ? (
          <ErrorState message={error} onRetry={retry} />
        ) : artifacts ? (
          <div className="space-y-6">
            <SectionAPanel
              model={model}
              slideId={slideId ?? undefined}
              section={artifacts}
              imageTransform={transformFor}
              onImageTransformChange={onTransformFor}
            />
            <ViolinPanel violin={artifacts.violin} />
            <SectionCPanel model={model} onTissue={artifacts.on_tissue} slideId={slideId ?? undefined} />
            <SectionDPanel model={model} />
          </div>
        ) : (
          <Prompt>No artifacts were returned for this slide.</Prompt>
        )}
      </div>
    </Card>
  );
}

function RenderingState({
  modelId,
  onJobFinished,
}: {
  modelId: string;
  onJobFinished: (job: JobInfo) => void;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 rounded-lg border border-[var(--s-rendering-border)] bg-[var(--s-rendering-bg)] px-3 py-2.5 text-xs font-semibold text-[var(--s-rendering-text)]">
        <FiLoader className="animate-spin" size={14} />
        Rendering this slide…
      </div>
      <JobStatusPoller refId={modelId} refTable="models" onJobFinished={onJobFinished} />
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string | null; onRetry: () => void }) {
  return (
    <div className="space-y-3 rounded-lg border border-[var(--s-failed-border)] bg-[var(--s-failed-bg)] p-3 text-xs text-[var(--s-failed-text)]">
      <div className="flex items-start gap-2">
        <FiAlertTriangle className="mt-0.5 shrink-0" size={14} />
        <span>{message ?? 'Failed to render this slide.'}</span>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="rounded-full border border-[var(--s-failed-border)] bg-surface px-3 py-1 font-semibold hover:opacity-80 transition-opacity"
      >
        Retry
      </button>
    </div>
  );
}

function Prompt({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-lg border border-dashed border-border bg-surface-subtle px-4 py-8 text-center text-xs text-ink-faint">
      {children}
    </p>
  );
}
