import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import DirectoryBrowser from './DirectoryBrowser';
import {
  ApiError,
  createSplit,
  getCsvRowCount,
  listSplits,
  resolveFeaturesDir,
  startPantherKFoldRun,
  type PantherMode,
  type RunResolveResponse,
  type SplitInfo,
} from '../lib/api';

const MODEL_NAME_RE = /^[A-Za-z0-9_-]+$/;
const MODES: PantherMode[] = ['faiss', 'kmeans'];

type SplitMode = 'create' | 'existing';

interface PantherFormState {
  modelName: string;
  featuresDir: string;
  splitMode: SplitMode;
  // create-new fields
  sourceCsv: string;
  k: number;
  splitSeed: number;
  // existing-split fields
  selectedSplitId: string;
  // hyperparameters
  pantherSeed: number;
  mode: PantherMode;
  inDim: number;
  nProtoPatches: number;
  nProto: number;
  nInit: number;
  numWorkers: number;
}

const INITIAL: PantherFormState = {
  modelName: '',
  featuresDir: '',
  splitMode: 'create',
  sourceCsv: '',
  k: 5,
  splitSeed: 42,
  selectedSplitId: '',
  pantherSeed: 1,
  mode: 'faiss',
  inDim: 1024,
  nProtoPatches: 1_000_000,
  nProto: 16,
  nInit: 5,
  numWorkers: 10,
};

function shellQuote(s: string): string {
  if (!s) return s;
  if (/^[\w./=-]+$/.test(s)) return s;
  return `'${s.replace(/'/g, `'\\''`)}'`;
}

function buildCommandPreview(s: PantherFormState, splitDirRel: string): string {
  const features = shellQuote(s.featuresDir.trim() || '<features_dir>');
  return [
    'CUDA_VISIBLE_DEVICES=0 python -m training.main_prototype',
    `--mode ${s.mode}`,
    `--data_source ${features}`,
    `--split_dir ${shellQuote(splitDirRel)}`,
    `--split_names train`,
    `--in_dim ${s.inDim}`,
    `--n_proto_patches ${s.nProtoPatches}`,
    `--n_proto ${s.nProto}`,
    `--n_init ${s.nInit}`,
    `--seed ${s.pantherSeed}`,
    `--num_workers ${s.numWorkers}`,
  ].join(' \\\n  ');
}

export default function PantherForm() {
  const navigate = useNavigate();
  const [state, setState] = useState<PantherFormState>(INITIAL);
  const [modelTouched, setModelTouched] = useState(false);
  const [browser, setBrowser] = useState<null | 'features' | 'source'>(null);

  // resolve features_dir → trident_run
  const [resolved, setResolved] = useState<RunResolveResponse | null>(null);
  const [resolveError, setResolveError] = useState<string | null>(null);
  const [resolving, setResolving] = useState(false);

  // splits for the resolved dataset
  const [splits, setSplits] = useState<SplitInfo[]>([]);
  const [splitsError, setSplitsError] = useState<string | null>(null);
  const [splitsLoading, setSplitsLoading] = useState(false);

  // source CSV row count (create-new mode)
  const [sourceRows, setSourceRows] = useState<number | null>(null);
  const [rowsLoading, setRowsLoading] = useState(false);
  const [rowsError, setRowsError] = useState<string | null>(null);

  // create-split action
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // submit (training)
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const update = <K extends keyof PantherFormState>(key: K, value: PantherFormState[K]) =>
    setState((prev) => ({ ...prev, [key]: value }));

  // Resolve features_dir → trident_run + dataset_name
  useEffect(() => {
    const dir = state.featuresDir.trim();
    setResolved(null);
    setResolveError(null);
    if (!dir) return;
    let cancelled = false;
    setResolving(true);
    (async () => {
      try {
        const r = await resolveFeaturesDir(dir);
        if (!cancelled) setResolved(r);
      } catch (err) {
        if (!cancelled) {
          const msg = err instanceof ApiError ? err.message : 'Failed to resolve features directory.';
          setResolveError(msg);
        }
      } finally {
        if (!cancelled) setResolving(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [state.featuresDir]);

  // Load splits for the resolved dataset
  useEffect(() => {
    setSplits([]);
    setSplitsError(null);
    setState((s) => ({ ...s, selectedSplitId: '' }));
    if (!resolved) return;
    let cancelled = false;
    setSplitsLoading(true);
    (async () => {
      try {
        const res = await listSplits(resolved.dataset_name);
        if (!cancelled) setSplits(res);
      } catch (err) {
        if (!cancelled) {
          const msg = err instanceof ApiError ? err.message : 'Failed to load splits.';
          setSplitsError(msg);
        }
      } finally {
        if (!cancelled) setSplitsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [resolved]);

  // Count source CSV rows (create-new mode)
  useEffect(() => {
    setSourceRows(null);
    setRowsError(null);
    const csv = state.sourceCsv.trim();
    if (!csv || state.splitMode !== 'create') return;
    let cancelled = false;
    setRowsLoading(true);
    (async () => {
      try {
        const res = await getCsvRowCount(csv);
        if (!cancelled) setSourceRows(res.rows);
      } catch (err) {
        if (!cancelled) {
          const msg = err instanceof ApiError ? err.message : 'Failed to read CSV.';
          setRowsError(msg);
        }
      } finally {
        if (!cancelled) setRowsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [state.sourceCsv, state.splitMode]);

  const selectedSplit = useMemo(
    () => splits.find((s) => s.id === state.selectedSplitId) ?? null,
    [splits, state.selectedSplitId],
  );

  const splitDirRel = useMemo(() => {
    if (selectedSplit) {
      return `datasets_splits/${selectedSplit.dataset_name}/${selectedSplit.split_name}/k=<i>`;
    }
    const ds = resolved?.dataset_name ?? '<dataset>';
    return `datasets_splits/${ds}/<split>/k=<i>`;
  }, [selectedSplit, resolved]);

  const commandPreview = useMemo(() => buildCommandPreview(state, splitDirRel), [state, splitDirRel]);

  const effectiveK = selectedSplit?.k ?? state.k;

  // --- validation ---------------------------------------------------------
  const modelError =
    modelTouched && !state.modelName
      ? 'Model name is required.'
      : state.modelName && !MODEL_NAME_RE.test(state.modelName)
        ? 'Only letters, digits, underscores, and hyphens are allowed.'
        : null;

  const kError = state.splitMode === 'create' && state.k < 3 ? 'K must be ≥ 3.' : null;
  const splitSeedError =
    state.splitMode === 'create' && state.splitSeed < 0 ? 'Split seed must be ≥ 0.' : null;
  const csvError =
    state.splitMode === 'create' && !state.sourceCsv.trim() ? 'Source CSV is required.' : null;

  const canCreateSplit =
    !!resolved && state.splitMode === 'create' && !kError && !splitSeedError && !csvError;

  const submitInvalid =
    !!modelError || !state.modelName || !resolved || !state.selectedSplitId || state.pantherSeed < 0;

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(commandPreview);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore
    }
  };

  const onCreateSplit = async () => {
    setCreateError(null);
    if (!resolved || !canCreateSplit) return;
    setCreating(true);
    try {
      const created = await createSplit({
        dataset_name: resolved.dataset_name,
        source_csv: state.sourceCsv.trim(),
        k: state.k,
        seed: state.splitSeed,
      });
      // Refresh the dropdown and switch to existing-split mode with the new split selected.
      try {
        const refreshed = await listSplits(resolved.dataset_name);
        setSplits(refreshed);
      } catch {
        setSplits((prev) => [created, ...prev]);
      }
      setState((s) => ({ ...s, splitMode: 'existing', selectedSplitId: created.id }));
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Failed to create split.';
      setCreateError(msg);
    } finally {
      setCreating(false);
    }
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);
    setModelTouched(true);
    if (submitInvalid || !resolved || !selectedSplit) {
      setSubmitError(
        modelError ?? 'Resolve a features directory and pick a split before training.',
      );
      return;
    }
    setSubmitting(true);
    try {
      const res = await startPantherKFoldRun({
        model_name: state.modelName,
        features_dir: state.featuresDir.trim(),
        dataset_name: resolved.dataset_name,
        split_id: selectedSplit.id,
        mode: state.mode,
        in_dim: state.inDim,
        n_proto_patches: state.nProtoPatches,
        n_proto: state.nProto,
        n_init: state.nInit,
        seed: state.pantherSeed,
        num_workers: state.numWorkers,
      });
      navigate(`/models/${encodeURIComponent(res.group_id)}`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Failed to start training.';
      setSubmitError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-slate-900">Prototype training with PANTHER</h2>
        <p className="text-sm text-slate-500">
          Train K prototype models via K-fold cross-validation. Each form submission queues one
          training job for K folds. Returns immediately; watch progress on the Models page.
        </p>
      </div>

      <form onSubmit={onSubmit} className="space-y-6 rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <Field label="Features directory" htmlFor="features_dir">
          <div className="flex gap-2">
            <input
              id="features_dir"
              type="text"
              value={state.featuresDir}
              onChange={(e) => update('featuresDir', e.target.value)}
              placeholder="./trident_processed/<dataset>/20x_256px_0px_overlap/features_uni_v1"
              className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-sm shadow-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
            />
            <button
              type="button"
              onClick={() => setBrowser('features')}
              className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 hover:bg-slate-100"
            >
              Browse…
            </button>
          </div>
          {resolving ? (
            <p className="mt-1 text-xs text-slate-500">Resolving…</p>
          ) : resolveError ? (
            <p className="mt-1 text-xs text-rose-600">{resolveError}</p>
          ) : resolved ? (
            <div className="mt-2 inline-flex items-center gap-2 rounded-full border border-emerald-300 bg-emerald-50 px-3 py-1 text-xs text-emerald-900">
              <span className="font-medium">Dataset:</span>
              <span className="font-mono">{resolved.dataset_name}</span>
              <span className="text-emerald-700/60">
                · {resolved.patch_encoder} · {resolved.mag}× · {resolved.patch_size}px
              </span>
            </div>
          ) : null}
        </Field>

        <Field label="Model name" htmlFor="model_name">
          <input
            id="model_name"
            type="text"
            value={state.modelName}
            onChange={(e) => update('modelName', e.target.value)}
            onBlur={() => setModelTouched(true)}
            placeholder="e.g., tcga_brca_pilot"
            aria-invalid={!!modelError}
            aria-describedby={modelError ? 'model_name_error' : undefined}
            className={`block w-full rounded-md border bg-white px-3 py-2 font-mono text-sm shadow-sm focus:outline-none focus:ring-1 ${
              modelError
                ? 'border-rose-400 focus:border-rose-500 focus:ring-rose-500'
                : 'border-slate-300 focus:border-slate-500 focus:ring-slate-500'
            }`}
          />
          <p className="mt-1 text-xs text-slate-500">
            Each fold's model is named{' '}
            <code className="font-mono">
              {state.modelName || '<model_name>'}_k{'{i}'}_{'{rand8}'}
            </code>
            .
          </p>
          {modelError ? (
            <p id="model_name_error" className="mt-1 text-xs text-rose-600">
              {modelError}
            </p>
          ) : null}
        </Field>

        <fieldset className="space-y-3">
          <legend className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Dataset split
          </legend>
          {!resolved ? (
            <p className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
              You can configure the split now; creating or selecting one becomes
              available once a features directory is resolved above.
            </p>
          ) : null}
          <div className="flex gap-2">
            <ToggleButton
              active={state.splitMode === 'create'}
              onClick={() => update('splitMode', 'create')}
            >
              Create new K-fold split
            </ToggleButton>
            <ToggleButton
              active={state.splitMode === 'existing'}
              onClick={() => update('splitMode', 'existing')}
            >
              Use existing split
            </ToggleButton>
          </div>

          {state.splitMode === 'create' ? (
            <div className="space-y-3">
              <Field label="Source CSV" htmlFor="source_csv">
                <div className="flex gap-2">
                  <input
                    id="source_csv"
                    type="text"
                    value={state.sourceCsv}
                    onChange={(e) => update('sourceCsv', e.target.value)}
                    placeholder="/data/manifests/tcga_brca.csv"
                    className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-sm shadow-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
                  />
                  <button
                    type="button"
                    onClick={() => setBrowser('source')}
                    className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 hover:bg-slate-100"
                  >
                    Browse…
                  </button>
                </div>
                {rowsLoading ? (
                  <p className="mt-1 text-xs text-slate-500">Counting rows…</p>
                ) : rowsError ? (
                  <p className="mt-1 text-xs text-rose-600">{rowsError}</p>
                ) : sourceRows != null ? (
                  <p className="mt-1 text-xs text-slate-500">
                    {sourceRows.toLocaleString()} data rows.
                  </p>
                ) : null}
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <NumberInput
                  label="K (folds)"
                  value={state.k}
                  onChange={(v) => update('k', Math.max(3, Math.round(v)))}
                  min={3}
                  step={1}
                />
                <NumberInput
                  label="Split seed"
                  value={state.splitSeed}
                  onChange={(v) => update('splitSeed', Math.max(0, Math.round(v)))}
                  min={0}
                  step={1}
                />
              </div>
              <p className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
                K-fold CV produces K folds. With K={state.k}: each fold uses ~
                {pctLabel((state.k - 2) / state.k)} train / {pctLabel(1 / state.k)} val /{' '}
                {pctLabel(1 / state.k)} test. Every slide appears in test exactly once across folds.
              </p>
              {createError ? (
                <p className="text-xs text-rose-600">{createError}</p>
              ) : null}
              <button
                type="button"
                disabled={!canCreateSplit || creating}
                onClick={onCreateSplit}
                className="rounded-md border border-slate-900 bg-white px-3 py-1.5 text-sm font-medium text-slate-900 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {creating ? 'Creating split…' : 'Create split'}
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {splitsError ? (
                <p className="text-xs text-rose-600">{splitsError}</p>
              ) : splitsLoading ? (
                <p className="text-xs text-slate-500">Loading splits…</p>
              ) : splits.length === 0 ? (
                <p className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
                  No saved splits for this dataset yet. Switch to <em>Create new K-fold split</em>.
                </p>
              ) : (
                <Field label="Existing split" htmlFor="existing_split">
                  <select
                    id="existing_split"
                    value={state.selectedSplitId}
                    onChange={(e) => update('selectedSplitId', e.target.value)}
                    className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-sm shadow-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
                  >
                    <option value="">— select a split —</option>
                    {splits.map((s) => {
                      const fold0 = s.per_fold_counts[0];
                      const sizes = fold0
                        ? `train ${fold0.train} / val ${fold0.val} / test ${fold0.test}`
                        : 'sizes unknown';
                      return (
                        <option key={s.id} value={s.id}>
                          {s.split_name} — K={s.k}, {sizes}
                        </option>
                      );
                    })}
                  </select>
                </Field>
              )}
            </div>
          )}
        </fieldset>

        <fieldset className="space-y-3">
          <legend className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            PANTHER parameters
          </legend>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Mode" htmlFor="mode">
              <select
                id="mode"
                value={state.mode}
                onChange={(e) => update('mode', e.target.value as PantherMode)}
                className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
              >
                {MODES.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </Field>
            <NumberInput
              label="Input dimension"
              value={state.inDim}
              onChange={(v) => update('inDim', Math.max(1, Math.round(v)))}
              min={1}
              step={1}
            />
            <NumberInput
              label="Patches per prototype"
              value={state.nProtoPatches}
              onChange={(v) => update('nProtoPatches', Math.max(1, Math.round(v)))}
              min={1}
              step={1000}
            />
            <NumberInput
              label="Number of prototypes"
              value={state.nProto}
              onChange={(v) => update('nProto', Math.max(1, Math.round(v)))}
              min={1}
              step={1}
            />
            <NumberInput
              label="K-means initializations"
              value={state.nInit}
              onChange={(v) => update('nInit', Math.max(1, Math.round(v)))}
              min={1}
              step={1}
            />
            <NumberInput
              label="Workers"
              value={state.numWorkers}
              onChange={(v) => update('numWorkers', Math.max(0, Math.round(v)))}
              min={0}
              step={1}
            />
            <NumberInput
              label="PANTHER --seed"
              value={state.pantherSeed}
              onChange={(v) => update('pantherSeed', Math.max(0, Math.round(v)))}
              min={0}
              step={1}
            />
          </div>
          <p className="text-[11px] text-slate-500">
            in_dim depends on the patch encoder used in TRIDENT — UNI=1024, UNI2-h=1536, Phikon=768.
          </p>
        </fieldset>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
              Command preview (per fold)
            </span>
            <button
              type="button"
              onClick={onCopy}
              className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-100 hover:bg-slate-700"
            >
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
          <pre className="overflow-x-auto whitespace-pre rounded-md bg-slate-900 px-4 py-3 font-mono text-xs leading-relaxed text-slate-100">
            {commandPreview}
          </pre>
          <p className="mt-1 text-xs text-slate-500">
            Runs from <code className="font-mono">$PANTHER_REPO_PATH/src</code>. The K commands are
            executed sequentially by the worker thread.
          </p>
        </div>

        {submitError ? (
          <div className="flex items-start justify-between gap-3 rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
            <span className="whitespace-pre-wrap font-mono text-xs">{submitError}</span>
            <button
              type="button"
              onClick={() => setSubmitError(null)}
              aria-label="Dismiss"
              className="text-rose-500 hover:text-rose-800"
            >
              ×
            </button>
          </div>
        ) : null}

        <button
          type="submit"
          disabled={submitting || submitInvalid}
          className="w-full rounded-md bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? `Queuing ${effectiveK} models…` : `Train ${effectiveK} Models`}
        </button>
      </form>

      <DirectoryBrowser
        open={browser === 'features'}
        mode="dir"
        initialPath={state.featuresDir || undefined}
        onCancel={() => setBrowser(null)}
        onSelect={(p) => {
          update('featuresDir', p);
          setBrowser(null);
        }}
      />
      <DirectoryBrowser
        open={browser === 'source'}
        mode="file"
        extensions={['.csv']}
        initialPath={state.sourceCsv || undefined}
        onCancel={() => setBrowser(null)}
        onSelect={(p) => {
          update('sourceCsv', p);
          setBrowser(null);
        }}
      />
    </div>
  );
}

function pctLabel(fraction: number): string {
  return `${Math.round(fraction * 100)}%`;
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </label>
      {children}
    </div>
  );
}

function ToggleButton({
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
      className={`rounded-md border px-3 py-1.5 text-sm font-medium ${
        active
          ? 'border-slate-900 bg-slate-900 text-white'
          : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-100'
      }`}
    >
      {children}
    </button>
  );
}

function NumberInput({
  label,
  value,
  onChange,
  min,
  max,
  step,
  className,
}: {
  label: string;
  value: number;
  onChange: (n: number) => void;
  min?: number;
  max?: number;
  step?: number;
  className?: string;
}) {
  return (
    <div className={className}>
      <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </label>
      <input
        type="number"
        value={Number.isFinite(value) ? value : 0}
        min={min}
        max={max}
        step={step}
        onChange={(e) => {
          const n = Number(e.target.value);
          onChange(Number.isFinite(n) ? n : 0);
        }}
        className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-sm shadow-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
      />
    </div>
  );
}
