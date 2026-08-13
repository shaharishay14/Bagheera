import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import JobLogViewer from '../components/JobLogViewer';
import JobStatusPoller from '../components/JobStatusPoller';
import NotesThread from '../components/NotesThread';
import PrototypeLabels from '../components/PrototypeLabels';
import SectionAPanel from '../components/SectionAPanel';
import SectionBPanel from '../components/SectionBPanel';
import SectionCPanel from '../components/SectionCPanel';
import SectionDPanel from '../components/SectionDPanel';
import {
  ApiError,
  getModel,
  listJobs,
  patchModel,
  type ModelInfo,
} from '../lib/api';
import { Card, Chip, SectionHeader, StatusPill } from '../components/ui';

/**
 * Standalone single-model detail page (`/models/:modelId`). Renders the same
 * paper-style analysis surface as the legacy K-fold GroupDetailPage drawer, but
 * without any fold framing — a single model has one 100%-train fold.
 */
export default function ModelDetailPage() {
  const { modelId = '' } = useParams<{ modelId: string }>();
  const [model, setModel] = useState<ModelInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingName, setEditingName] = useState(false);
  const [draftName, setDraftName] = useState('');

  const reload = useCallback(async () => {
    if (!modelId) return;
    try {
      const res = await getModel(modelId);
      setModel(res);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load model.');
    }
  }, [modelId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const res = await getModel(modelId);
        if (!cancelled) setModel(res);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Failed to load model.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [modelId]);

  const onSaveName = async () => {
    if (!model) return;
    const next = draftName.trim();
    if (!next || next === model.display_name) {
      setEditingName(false);
      return;
    }
    try {
      await patchModel(model.id, { display_name: next });
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to rename.');
    } finally {
      setEditingName(false);
    }
  };

  const toggleFavorite = async () => {
    if (!model) return;
    try {
      await patchModel(model.id, { is_favorite: !model.is_favorite });
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to toggle favorite.');
    }
  };

  if (loading) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }
  if (error || !model) {
    return (
      <div className="rounded-md border border-[var(--s-failed-border)] bg-[var(--s-failed-bg)] px-4 py-3 text-sm text-[var(--s-failed-text)]">
        {error ?? 'Model not found.'}
        <div className="mt-2">
          <Link to="/models" className="underline hover:opacity-80">
            ← Back to models
          </Link>
        </div>
      </div>
    );
  }

  const trainingActive = model.status === 'running' || model.status === 'pending';
  const vizActive = model.viz_status === 'pending' || model.viz_status === 'rendering';
  const showFailure = model.status === 'failed' || model.viz_status === 'failed';

  return (
    <div className="space-y-6">
      <div>
        <Link to="/models" className="text-xs text-ink-faint hover:text-ink transition-colors">
          ← Models
        </Link>
        <div className="mt-1 flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <button
              type="button"
              onClick={toggleFavorite}
              aria-label={model.is_favorite ? 'Unfavorite' : 'Favorite'}
              className={`shrink-0 transition-colors ${
                model.is_favorite
                  ? 'text-[var(--s-warn-text)]'
                  : 'text-ink-faint hover:text-ink-muted'
              }`}
            >
              <StarIcon filled={model.is_favorite} />
            </button>
            {editingName ? (
              <input
                autoFocus
                value={draftName}
                onChange={(e) => setDraftName(e.target.value)}
                onBlur={onSaveName}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') onSaveName();
                  if (e.key === 'Escape') setEditingName(false);
                }}
                className="rounded-md border border-border-strong bg-surface px-2 py-1 text-xl font-bold shadow-card focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent"
              />
            ) : (
              <button
                type="button"
                onClick={() => {
                  setDraftName(model.display_name);
                  setEditingName(true);
                }}
                className="min-w-0 truncate text-left text-xl font-bold text-ink hover:text-accent transition-colors"
                title="Click to rename"
              >
                {model.display_name || model.base_name}
              </button>
            )}
          </div>
          <Link
            to={`/models/${encodeURIComponent(model.id)}/inference`}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-grad-accent px-4 py-1.5 text-sm font-semibold text-white shadow-glow hover:shadow-glow-lg hover:brightness-105 transition-all duration-150"
          >
            Inference →
          </Link>
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
          <Chip>single model</Chip>
          <Chip mono>{model.dataset_name}</Chip>
          <StatusPill status={model.status} />
          {model.viz_status !== 'ready' ? (
            <StatusPill status={model.viz_status} label={`viz: ${model.viz_status}`} />
          ) : null}
          <span>·</span>
          <span>n_proto={model.n_proto}</span>
          <span>·</span>
          <span>{model.mode}</span>
          <span>·</span>
          <span>{new Date(model.created_at).toLocaleString()}</span>
        </div>
        <p className="mt-1.5 text-xs text-ink-faint">
          Split: <span className="font-mono text-ink-muted">{model.split_name}</span>{' '}
          <span className="opacity-70">(single fold · 100% train)</span>
        </p>
        <p className="mt-0.5 font-mono text-[11px] text-ink-faint">{model.model_name}</p>
      </div>

      {trainingActive || vizActive ? (
        <div className="rounded-lg border border-[var(--s-running-border)] bg-[var(--s-running-bg)] p-3">
          <div className="mb-2 text-xs font-semibold text-[var(--s-running-text)]">
            {trainingActive ? 'Training in progress' : 'Rendering visualizations'}
          </div>
          <JobStatusPoller refId={model.id} refTable="models" onJobFinished={reload} />
        </div>
      ) : null}

      {showFailure ? (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-[var(--s-failed-border)] bg-[var(--s-failed-bg)] p-3 text-xs text-[var(--s-failed-text)]">
          <span>
            {model.status === 'failed'
              ? 'Training failed for this model.'
              : 'Visualization rendering failed.'}
          </span>
          <FailureLogLink model={model} />
        </div>
      ) : null}

      {/* Analysis surface — mirrors the paper-style figure panels. Ordered A → C
          → D so the per-slide analysis reads before the dictionary. Section B
          (validation consistency) only renders when the model has held-out
          slides, which single 100%-train models never do — it degrades to a
          muted note. NOTE: a future per-slide validation violin panel can slot
          in right after Section C without disturbing the rest. */}
      <div className="space-y-5">
        <SectionAPanel model={model} />
        <SectionCPanel model={model} />
        <SectionDPanel model={model} />
        {model.viz_artifacts?.section_b ? <SectionBPanel model={model} /> : null}

        <Card className="p-4">
          <SectionHeader title="Prototype labels" className="mb-3" />
          <PrototypeLabels modelId={model.id} nProto={model.n_proto} />
        </Card>

        <ParametersPanel model={model} />

        <Card className="p-4">
          <SectionHeader title="Notes" className="mb-3" />
          <NotesThread target={{ kind: 'model', modelId: model.id }} />
        </Card>

        <section>
          <SectionHeader title="Jobs" />
          <div className="mt-2">
            <JobStatusPoller refId={model.id} refTable="models" onJobFinished={reload} />
          </div>
        </section>
      </div>
    </div>
  );
}

function ParametersPanel({ model }: { model: ModelInfo }) {
  return (
    <Card className="p-4">
      <SectionHeader title="Parameters & paths" className="mb-3" />
      <div className="grid grid-cols-1 gap-x-6 gap-y-2 font-mono text-xs sm:grid-cols-2">
        <Param k="mode" v={model.mode} />
        <Param k="in_dim" v={String(model.in_dim)} />
        <Param k="n_proto" v={String(model.n_proto)} />
        <Param k="n_proto_patches" v={model.n_proto_patches.toLocaleString()} />
        <Param k="n_init" v={String(model.n_init)} />
        <Param k="seed" v={String(model.seed)} />
        <Param k="num_workers" v={String(model.num_workers)} />
        <Param k="run_kind" v={model.run_kind ?? '-'} />
        <Param k="split_name" v={model.split_name} />
        <Param k="trident_run_id" v={model.trident_run_id ?? '-'} />
        <Param k="features_dir" v={model.features_dir} />
        <Param k="prototypes_dir" v={model.prototypes_dir} />
      </div>
    </Card>
  );
}

function Param({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-2">
      <dt className="w-32 shrink-0 text-ink-faint">{k}</dt>
      <dd className="flex-1 break-all text-ink">{v}</dd>
    </div>
  );
}

function FailureLogLink({ model }: { model: ModelInfo }) {
  const [openJobId, setOpenJobId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const onOpen = async () => {
    setLoading(true);
    setErr(null);
    try {
      const failed = await listJobs({ refTable: 'models', refId: model.id, status: 'failed', limit: 1 });
      if (failed.length > 0) { setOpenJobId(failed[0].id); return; }
      const any = await listJobs({ refTable: 'models', refId: model.id, limit: 1 });
      if (any.length > 0) { setOpenJobId(any[0].id); return; }
      setErr('No job found for this model.');
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'Failed to find job.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={onOpen}
        disabled={loading}
        className="shrink-0 rounded-full border border-[var(--s-failed-border)] bg-surface px-3 py-1 font-semibold hover:opacity-80 disabled:opacity-50 transition-opacity"
      >
        {loading ? 'Loading…' : err ?? 'View error log'}
      </button>
      {openJobId ? (
        <JobLogViewer jobId={openJobId} onClose={() => setOpenJobId(null)} />
      ) : null}
    </>
  );
}

function StarIcon({ filled = false }: { filled?: boolean }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    </svg>
  );
}
