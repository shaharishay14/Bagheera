import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { FiTrash2 } from 'react-icons/fi';
import JobLogViewer from '../components/JobLogViewer';
import JobStatusPoller from '../components/JobStatusPoller';
import NotesThread from '../components/NotesThread';
import ConfirmDeleteModal from '../components/ConfirmDeleteModal';
import SectionAPanel from '../components/SectionAPanel';
import SectionBPanel from '../components/SectionBPanel';
import SectionCPanel from '../components/SectionCPanel';
import SectionDPanel from '../components/SectionDPanel';
import {
  ApiError,
  deleteModelGroup,
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
import { Card, Chip, SectionHeader, StatusPill } from '../components/ui';

type DrawerTab = null | 'analysis' | 'parameters' | 'notes';

export default function GroupDetailPage() {
  const { groupId = '' } = useParams<{ groupId: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<ModelGroupDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingName, setEditingName] = useState(false);
  const [draftName, setDraftName] = useState('');
  const [openDrawer, setOpenDrawer] = useState<Record<string, DrawerTab>>({});
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

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
    return () => { cancelled = true; };
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

  const onConfirmDelete = async () => {
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteModelGroup(groupId);
      navigate('/models');
    } catch (err) {
      // Keep the modal open so the user sees why (e.g. 409: a job is running).
      setDeleteError(
        err instanceof ApiError ? err.message : 'Failed to delete this model group.',
      );
      setDeleting(false);
    }
  };

  const trainingActive = useMemo(() => {
    if (!data) return false;
    return data.models.some((m) => m.status === 'running' || m.status === 'pending');
  }, [data]);

  if (loading) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }
  if (error || !data) {
    return (
      <div className="rounded-md border border-[var(--s-failed-border)] bg-[var(--s-failed-bg)] px-4 py-3 text-sm text-[var(--s-failed-text)]">
        {error ?? 'Group not found.'}
        <div className="mt-2">
          <Link to="/models" className="underline hover:opacity-80">
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
        <Link to="/models" className="text-xs text-ink-faint hover:text-ink transition-colors">
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
                className="rounded-md border border-border-strong bg-surface px-2 py-1 text-xl font-bold shadow-card focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent"
              />
            </div>
          ) : (
            <button
              type="button"
              onClick={() => {
                setDraftName(group.display_name);
                setEditingName(true);
              }}
              className="text-left text-xl font-bold text-ink hover:text-accent transition-colors"
              title="Click to rename"
            >
              {group.display_name}
            </button>
          )}
          <button
            type="button"
            onClick={() => {
              setDeleteError(null);
              setConfirmingDelete(true);
            }}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-[var(--s-failed-border)] bg-surface px-3 py-1.5 text-xs font-semibold text-[var(--s-failed-text)] hover:bg-[var(--s-failed-bg)] transition-colors"
            title="Delete this model group"
          >
            <FiTrash2 size={13} /> Delete group
          </button>
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
          <Chip mono>{group.dataset_name}</Chip>
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
              <Link to="/training/trident" className="underline hover:text-ink">
                training run
              </Link>
            </>
          ) : null}
        </div>
        <p className="mt-1.5 text-xs text-ink-faint">
          Split: <span className="font-mono text-ink-muted">{split.split_name}</span>{' '}
          ({split.total_rows} rows)
        </p>
      </div>

      {trainingActive ? (
        <div className="rounded-lg border border-[var(--s-running-border)] bg-[var(--s-running-bg)] p-3">
          <div className="mb-2 flex items-center justify-between text-xs font-semibold text-[var(--s-running-text)]">
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

      <ConfirmDeleteModal
        open={confirmingDelete}
        title="Delete model group"
        name={group.display_name}
        busy={deleting}
        error={deleteError}
        onCancel={() => {
          if (!deleting) {
            setConfirmingDelete(false);
            setDeleteError(null);
          }
        }}
        onConfirm={onConfirmDelete}
      >
        This permanently deletes all {group.k} fold models, their prototypes,
        visualizations, inference outputs, and database records for this group.{' '}
        <span className="font-semibold text-ink">This cannot be undone.</span>
      </ConfirmDeleteModal>
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
    <Card>
      <div className="flex items-start gap-3 p-3">
        <button
          type="button"
          onClick={onToggleFavorite}
          aria-label={model.is_favorite ? 'Unfavorite' : 'Favorite'}
          className={`mt-1 transition-colors ${
            model.is_favorite
              ? 'text-[var(--s-warn-text)]'
              : 'text-ink-faint hover:text-ink-muted'
          }`}
        >
          <StarIcon filled={model.is_favorite} />
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-ink">
              Fold {model.fold_index + 1} of {model.fold_k}
            </h3>
            <StatusPill status={model.status} />
            {model.viz_status !== 'ready' && (
              <StatusPill status={model.viz_status} label={`viz: ${model.viz_status}`} />
            )}
            <span className="font-mono text-[11px] text-ink-faint">{model.model_name}</span>
          </div>
          <div className="mt-2 flex gap-2">
            {previews.map((_label, i) => (
              <img
                key={i}
                src={resolveVizUrl(
                  model.preview_heatmap_paths?.[i],
                  () => vizPlaceholderUrl('heatmap', { label: `Slide ${i + 1}`, width: 200, height: 140 })
                )}
                alt={`Preview ${i + 1}`}
                className="h-20 w-32 rounded border border-border bg-surface-subtle object-cover"
              />
            ))}
            {model.status === 'failed' || model.viz_status === 'failed' ? (
              <FailureLogLink model={model} />
            ) : null}
            <button
              type="button"
              onClick={onShuffle}
              className="rounded border border-border-strong bg-surface px-2 text-xs text-ink-muted hover:bg-surface-subtle transition-colors"
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
              className="rounded border border-border-strong bg-surface px-2 py-1 text-xs text-ink hover:bg-surface-subtle transition-colors"
            >
              Inference →
            </Link>
          </div>
          <span className="text-[11px] text-ink-faint">
            {new Date(model.created_at).toLocaleString()}
          </span>
        </div>
      </div>

      {drawer === 'analysis' ? (
        <AnalysisDrawer model={model} onJobsRefresh={onJobsRefresh} />
      ) : null}
      {drawer === 'parameters' ? <ParametersPanel model={model} /> : null}
      {drawer === 'notes' ? (
        <div className="border-t border-border bg-surface-subtle p-4">
          <NotesThread modelId={model.id} />
        </div>
      ) : null}
    </Card>
  );
}

function AnalysisDrawer({ model, onJobsRefresh }: { model: ModelInfo; onJobsRefresh: () => void }) {
  return (
    <div className="space-y-5 border-t border-border bg-surface-subtle p-4">
      <SectionAPanel model={model} />

      <SectionBPanel model={model} />

      <SectionDPanel model={model} />

      <SectionCPanel model={model} />

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
  const [openJobId, setOpenJobId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onOpen = async () => {
    setLoading(true);
    setError(null);
    try {
      const refTable = model.status === 'failed' ? 'model_groups' : 'models';
      const refId = model.status === 'failed' ? model.group_id : model.id;
      const failedJobs = await listJobs({ refTable, refId, status: 'failed', limit: 1 });
      if (failedJobs.length > 0) { setOpenJobId(failedJobs[0].id); return; }
      const anyJobs = await listJobs({ refTable, refId, limit: 1 });
      if (anyJobs.length > 0) { setOpenJobId(anyJobs[0].id); return; }
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
        className="inline-flex h-20 w-32 flex-col items-center justify-center rounded border border-[var(--s-failed-border)] bg-[var(--s-failed-bg)] px-2 text-[11px] text-[var(--s-failed-text)] hover:opacity-80 disabled:opacity-50 transition-opacity"
        title="View the error log for this fold"
      >
        <span className="text-lg">⚠</span>
        <span>{loading ? 'Loading…' : 'View error log'}</span>
        {error ? <span className="text-[10px]">{error}</span> : null}
      </button>
      {openJobId ? (
        <JobLogViewer jobId={openJobId} onClose={() => setOpenJobId(null)} />
      ) : null}
    </>
  );
}

function ParametersPanel({ model }: { model: ModelInfo }) {
  return (
    <div className="border-t border-border bg-surface-subtle p-4">
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
        <Param k="trident_run_id" v={model.trident_run_id ?? '-'} />
        <Param k="features_dir" v={model.features_dir} />
        <Param k="prototypes_dir" v={model.prototypes_dir} />
      </div>
    </div>
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
      className={`rounded border px-2 py-1 text-xs font-medium transition-colors ${
        active
          ? 'border-accent bg-accent text-white'
          : 'border-border-strong bg-surface text-ink hover:bg-surface-subtle'
      }`}
    >
      {children}
    </button>
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
