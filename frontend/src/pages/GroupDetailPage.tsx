import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import JobLogViewer from '../components/JobLogViewer';
import JobStatusPoller from '../components/JobStatusPoller';
import NotesThread from '../components/NotesThread';
import PrototypeLabels from '../components/PrototypeLabels';
import {
  ApiError,
  getModelGroup,
  listJobs,
  patchModel,
  patchModelGroup,
  resolveVizUrl,
  shuffleModelPreview,
  vizPlaceholderUrl,
  type ModelGroupDetail,
  type ModelInfo,
} from '../lib/api';

type DrawerTab = null | 'analysis' | 'parameters' | 'notes';

export default function GroupDetailPage() {
  const { groupId = '' } = useParams<{ groupId: string }>();
  const [data, setData] = useState<ModelGroupDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingName, setEditingName] = useState(false);
  const [draftName, setDraftName] = useState('');
  const [openDrawer, setOpenDrawer] = useState<Record<string, DrawerTab>>({});

  const reload = useCallback(async () => {
    if (!groupId) return;
    try {
      const res = await getModelGroup(groupId);
      setData(res);
      setError(null);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Failed to load group.';
      setError(msg);
    }
  }, [groupId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const res = await getModelGroup(groupId);
        if (!cancelled) setData(res);
      } catch (err) {
        if (!cancelled) {
          const msg = err instanceof ApiError ? err.message : 'Failed to load group.';
          setError(msg);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [groupId]);

  const onSaveName = async () => {
    if (!data) return;
    const next = draftName.trim();
    if (!next || next === data.group.display_name) {
      setEditingName(false);
      return;
    }
    try {
      await patchModelGroup(groupId, { display_name: next });
      await reload();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Failed to rename.';
      setError(msg);
    } finally {
      setEditingName(false);
    }
  };

  const toggleFavorite = async (model: ModelInfo) => {
    try {
      await patchModel(model.id, { is_favorite: !model.is_favorite });
      await reload();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Failed to toggle favorite.';
      setError(msg);
    }
  };

  const shufflePreview = async (modelId: string) => {
    try {
      await shuffleModelPreview(modelId);
      await reload();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Failed to shuffle preview.';
      setError(msg);
    }
  };

  const trainingActive = useMemo(() => {
    if (!data) return false;
    return data.models.some((m) => m.status === 'running' || m.status === 'pending');
  }, [data]);

  if (loading) {
    return <p className="text-sm text-slate-500">Loading…</p>;
  }
  if (error || !data) {
    return (
      <div className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
        {error ?? 'Group not found.'}
        <div className="mt-2">
          <Link to="/models" className="text-rose-900 underline">
            ← Back to models
          </Link>
        </div>
      </div>
    );
  }

  const { group, models, split } = data;

  return (
    <div className="space-y-6">
      <div>
        <Link to="/models" className="text-xs text-slate-500 hover:text-slate-900">
          ← Models
        </Link>
        <div className="mt-1 flex items-start justify-between gap-3">
          {editingName ? (
            <div className="flex items-center gap-2">
              <input
                autoFocus
                value={draftName}
                onChange={(e) => setDraftName(e.target.value)}
                onBlur={onSaveName}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') onSaveName();
                  if (e.key === 'Escape') setEditingName(false);
                }}
                className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xl font-semibold shadow-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
              />
            </div>
          ) : (
            <button
              type="button"
              onClick={() => {
                setDraftName(group.display_name);
                setEditingName(true);
              }}
              className="text-left text-xl font-semibold text-slate-900 hover:text-slate-700"
              title="Click to rename"
            >
              {group.display_name}
            </button>
          )}
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <span className="rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 font-mono text-slate-700">
            {group.dataset_name}
          </span>
          <span>K={group.k}</span>
          <span>·</span>
          <span>n_proto={group.n_proto}</span>
          <span>·</span>
          <span>{group.mode}</span>
          <span>·</span>
          <span>{new Date(group.created_at).toLocaleString()}</span>
          {group.trident_run_id ? (
            <>
              <span>·</span>
              <Link to={`/training/trident`} className="underline hover:text-slate-900">
                training run
              </Link>
            </>
          ) : null}
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Split: <span className="font-mono">{split.split_name}</span> ({split.total_rows} rows)
        </p>
      </div>

      {trainingActive ? (
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-3">
          <div className="mb-2 flex items-center justify-between text-xs font-medium text-blue-900">
            <span>Active jobs for this group</span>
          </div>
          <JobStatusPoller refId={group.id} refTable="model_groups" onJobFinished={reload} />
        </div>
      ) : null}

      <div className="space-y-3">
        {models.map((m) => (
          <FoldRow
            key={m.id}
            model={m}
            drawer={openDrawer[m.id] ?? null}
            onToggleDrawer={(tab) =>
              setOpenDrawer((prev) => ({ ...prev, [m.id]: prev[m.id] === tab ? null : tab }))
            }
            onToggleFavorite={() => toggleFavorite(m)}
            onShuffle={() => shufflePreview(m.id)}
            onJobsRefresh={reload}
          />
        ))}
      </div>
    </div>
  );
}

function FoldRow({
  model,
  drawer,
  onToggleDrawer,
  onToggleFavorite,
  onShuffle,
  onJobsRefresh,
}: {
  model: ModelInfo;
  drawer: DrawerTab;
  onToggleDrawer: (tab: DrawerTab) => void;
  onToggleFavorite: () => void;
  onShuffle: () => void;
  onJobsRefresh: () => void;
}) {
  const previewIds = model.preview_slide_ids ?? [];
  const previews = (previewIds.length > 0 ? previewIds : ['fold preview 1', 'fold preview 2', 'fold preview 3']).slice(0, 3);

  return (
    <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex items-start gap-3 p-3">
        <button
          type="button"
          onClick={onToggleFavorite}
          aria-label={model.is_favorite ? 'Unfavorite' : 'Favorite'}
          className={`mt-1 ${model.is_favorite ? 'text-amber-500' : 'text-slate-300 hover:text-slate-500'}`}
        >
          <StarIcon filled={model.is_favorite} />
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-slate-900">
              Fold {model.fold_index + 1} of {model.fold_k}
            </h3>
            <ModelStatusPill status={model.status} />
            <VizStatusPill status={model.viz_status} />
            <span className="font-mono text-[11px] text-slate-500">{model.model_name}</span>
          </div>
          <div className="mt-2 flex gap-2">
            {previews.map((_label, i) => (
              <img
                key={i}
                src={resolveVizUrl(
                  model.preview_heatmap_paths?.[i],
                  () =>
                    vizPlaceholderUrl('heatmap', {
                      label: `Slide ${i + 1}`,
                      width: 200,
                      height: 140,
                    })
                )}
                alt={`Preview ${i + 1}`}
                className="h-20 w-32 rounded border border-slate-200 bg-slate-50 object-cover"
              />
            ))}
            {model.status === 'failed' || model.viz_status === 'failed' ? (
              <FailureLogLink model={model} />
            ) : null}
            <button
              type="button"
              onClick={onShuffle}
              className="rounded border border-slate-300 bg-white px-2 text-xs text-slate-700 hover:bg-slate-100"
              title="Pick new preview slides"
            >
              ↻ Shuffle
            </button>
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1 text-xs">
          <div className="flex gap-1">
            <ActionButton active={drawer === 'analysis'} onClick={() => onToggleDrawer('analysis')}>
              Analysis
            </ActionButton>
            <ActionButton active={drawer === 'parameters'} onClick={() => onToggleDrawer('parameters')}>
              Parameters
            </ActionButton>
            <ActionButton active={drawer === 'notes'} onClick={() => onToggleDrawer('notes')}>
              Notes
            </ActionButton>
            <Link
              to={`/models/${encodeURIComponent(model.id)}/inference`}
              className="rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 hover:bg-slate-100"
              title="Run inference with this fold model (PR 5)"
            >
              Inference →
            </Link>
          </div>
          <span className="text-[11px] text-slate-500">
            {new Date(model.created_at).toLocaleString()}
          </span>
        </div>
      </div>

      {drawer === 'analysis' ? (
        <AnalysisDrawer model={model} onJobsRefresh={onJobsRefresh} />
      ) : null}
      {drawer === 'parameters' ? <ParametersPanel model={model} /> : null}
      {drawer === 'notes' ? (
        <div className="border-t border-slate-200 bg-slate-50 p-4">
          <NotesThread modelId={model.id} />
        </div>
      ) : null}
    </div>
  );
}

function AnalysisDrawer({ model, onJobsRefresh }: { model: ModelInfo; onJobsRefresh: () => void }) {
  const previewIds = model.preview_slide_ids ?? [];
  const previews = previewIds.length > 0 ? previewIds : ['Slide 1', 'Slide 2', 'Slide 3'];
  return (
    <div className="space-y-5 border-t border-slate-200 bg-slate-50 p-4">
      <section>
        <SectionHeader title="On 3 example slides" />
        <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-3">
          {previews.slice(0, 3).map((_label, i) => (
            <img
              key={i}
              src={resolveVizUrl(
                model.preview_heatmap_paths?.[i],
                () =>
                  vizPlaceholderUrl('heatmap', {
                    label: `Heatmap ${i + 1}`,
                    width: 360,
                    height: 240,
                  })
              )}
              alt={`Heatmap ${i + 1}`}
              className="w-full rounded border border-slate-200 bg-white"
            />
          ))}
        </div>
        {model.viz_status !== 'ready' ? (
          <p className="mt-1 text-[11px] text-slate-500">
            Placeholders — viz hasn't finished rendering yet.
          </p>
        ) : null}
      </section>

      <section>
        <SectionHeader title="Representative patches" />
        <img
          src={resolveVizUrl(
            model.topk_grid_path,
            () =>
              vizPlaceholderUrl('topk', {
                label: `${model.n_proto}×${model.topk_per_proto} grid`,
                width: 720,
                height: 320,
              })
          )}
          alt="Top-K grid"
          className="mt-2 w-full rounded border border-slate-200 bg-white"
        />
      </section>

      <section>
        <SectionHeader title="Across the dataset" />
        <img
          src={resolveVizUrl(
            model.umap_path,
            () => vizPlaceholderUrl('umap', { label: 'UMAP', width: 720, height: 320 })
          )}
          alt="UMAP"
          className="mt-2 w-full rounded border border-slate-200 bg-white"
        />
      </section>

      <section>
        <SectionHeader title="Prototype labels" />
        <div className="mt-2">
          <PrototypeLabels modelId={model.id} nProto={model.n_proto} />
        </div>
      </section>

      <section>
        <SectionHeader title="Viz jobs" />
        <div className="mt-2">
          <JobStatusPoller refId={model.id} refTable="models" onJobFinished={onJobsRefresh} />
        </div>
      </section>
    </div>
  );
}

function FailureLogLink({ model }: { model: ModelInfo }) {
  // Pick the right ref: training failures live under the group's panther_train
  // job; viz failures live under the model's post_train_viz job.
  const [openJobId, setOpenJobId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onOpen = async () => {
    setLoading(true);
    setError(null);
    try {
      const refTable = model.status === 'failed' ? 'model_groups' : 'models';
      const refId = model.status === 'failed' ? model.group_id : model.id;
      // Look up the most recent failed job for this ref.
      const failedJobs = await listJobs({
        refTable,
        refId,
        status: 'failed',
        limit: 1,
      });
      if (failedJobs.length > 0) {
        setOpenJobId(failedJobs[0].id);
        return;
      }
      // Fall back to most recent job of any status — the failure might be in
      // a job that's still 'running' (unlikely if the model is already marked
      // failed) or we missed it.
      const anyJobs = await listJobs({ refTable, refId, limit: 1 });
      if (anyJobs.length > 0) {
        setOpenJobId(anyJobs[0].id);
        return;
      }
      setError('No job found for this model.');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to find job.');
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
        className="inline-flex h-20 w-32 flex-col items-center justify-center rounded border border-rose-200 bg-rose-50 px-2 text-[11px] text-rose-700 hover:border-rose-400 hover:bg-rose-100 disabled:opacity-50"
        title="View the error log for this fold"
      >
        <span className="text-lg">⚠</span>
        <span>{loading ? 'Loading…' : 'View error log'}</span>
        {error ? <span className="text-rose-500">{error}</span> : null}
      </button>
      {openJobId ? (
        <JobLogViewer jobId={openJobId} onClose={() => setOpenJobId(null)} />
      ) : null}
    </>
  );
}

function ParametersPanel({ model }: { model: ModelInfo }) {
  return (
    <div className="border-t border-slate-200 bg-slate-50 p-4">
      <div className="grid grid-cols-2 gap-x-6 gap-y-2 font-mono text-xs">
        <Param k="mode" v={model.mode} />
        <Param k="in_dim" v={String(model.in_dim)} />
        <Param k="n_proto" v={String(model.n_proto)} />
        <Param k="n_proto_patches" v={model.n_proto_patches.toLocaleString()} />
        <Param k="n_init" v={String(model.n_init)} />
        <Param k="seed" v={String(model.seed)} />
        <Param k="num_workers" v={String(model.num_workers)} />
        <Param k="fold_index" v={`${model.fold_index} / ${model.fold_k - 1}`} />
        <Param k="split_name" v={model.split_name} />
        <Param k="trident_run_id" v={model.trident_run_id ?? '—'} />
        <Param k="features_dir" v={model.features_dir} />
        <Param k="prototypes_dir" v={model.prototypes_dir} />
      </div>
    </div>
  );
}

function Param({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-2">
      <dt className="w-32 shrink-0 text-slate-500">{k}</dt>
      <dd className="flex-1 break-all text-slate-800">{v}</dd>
    </div>
  );
}

function SectionHeader({ title }: { title: string }) {
  return (
    <h4 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{title}</h4>
  );
}

function ActionButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded border px-2 py-1 text-xs ${
        active
          ? 'border-slate-900 bg-slate-900 text-white'
          : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-100'
      }`}
    >
      {children}
    </button>
  );
}

function ModelStatusPill({ status }: { status: ModelInfo['status'] }) {
  const tones: Record<ModelInfo['status'], string> = {
    pending: 'bg-slate-100 text-slate-700 border-slate-200',
    running: 'bg-blue-50 text-blue-800 border-blue-200 animate-pulse',
    ready: 'bg-emerald-50 text-emerald-800 border-emerald-200',
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

function VizStatusPill({ status }: { status: ModelInfo['viz_status'] }) {
  if (status === 'ready') return null;
  const tones: Record<ModelInfo['viz_status'], string> = {
    pending: 'bg-slate-100 text-slate-600 border-slate-200',
    rendering: 'bg-amber-50 text-amber-800 border-amber-200 animate-pulse',
    ready: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    failed: 'bg-rose-50 text-rose-800 border-rose-200',
  };
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${tones[status]}`}
      title={`Visualization status: ${status}`}
    >
      viz: {status}
    </span>
  );
}

function StarIcon({ filled = false }: { filled?: boolean }) {
  return (
    <svg
      width="16"
      height="16"
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
