import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import DirectoryBrowser from './DirectoryBrowser';
import {
  ApiError,
  getCsvRowCount,
  listSplits,
  startPantherRun,
  type PantherKFoldRunResponse,
  type PantherMode,
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
  // existing fields
  existingSplitName: string;
  // seeds — fully independent. splitSeed is only used when CREATING a split (deterministic
  // shuffle). pantherSeed is the PANTHER --seed (k-means/faiss init) and applies in both modes.
  splitSeed: number;
  pantherSeed: number;
  // hyperparameters
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
  existingSplitName: '',
  splitSeed: 1,
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

function buildCommandPreview(
  s: PantherFormState,
  splitDirRel: string,
): string {
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

function splitDirRelPreview(state: PantherFormState, splits: SplitInfo[]): string {
  if (state.splitMode === 'existing') {
    const picked = splits.find((s) => s.split_name === state.existingSplitName);
    if (!picked) return 'datasets_splits/<dataset>/<split>/k=<i>';
    return `datasets_splits/${picked.dataset_name}/${picked.split_name}/k=<i>`;
  }
  const ds = state.modelName || '<model_name>';
  return `datasets_splits/${ds}/<auto>/k=<i>`;
}

export default function PantherForm() {
  const [state, setState] = useState<PantherFormState>(INITIAL);
  const [modelTouched, setModelTouched] = useState(false);
  const [browser, setBrowser] = useState<null | 'features' | 'source'>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PantherKFoldRunResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const [sourceRows, setSourceRows] = useState<number | null>(null);
  const [rowsLoading, setRowsLoading] = useState(false);
  const [rowsError, setRowsError] = useState<string | null>(null);
  const [splits, setSplits] = useState<SplitInfo[]>([]);
  const [splitsError, setSplitsError] = useState<string | null>(null);

  const update = <K extends keyof PantherFormState>(key: K, value: PantherFormState[K]) =>
    setState((prev) => ({ ...prev, [key]: value }));

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await listSplits();
        if (!cancelled) setSplits(res);
      } catch (err) {
        if (!cancelled) {
          const msg = err instanceof ApiError ? err.message : 'Failed to load splits.';
          setSplitsError(msg);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

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

  const splitDirRel = useMemo(() => splitDirRelPreview(state, splits), [state, splits]);
  const commandPreview = useMemo(() => buildCommandPreview(state, splitDirRel), [state, splitDirRel]);

  const pickedExistingSplit = useMemo(
    () =>
      state.splitMode === 'existing'
        ? splits.find((s) => s.split_name === state.existingSplitName) ?? null
        : null,
    [state.splitMode, state.existingSplitName, splits],
  );

  // K used for the submit-button label and helper text.
  const effectiveK = pickedExistingSplit?.k ?? state.k;

  // --- validation ---------------------------------------------------------
  const modelError =
    modelTouched && !state.modelName
      ? 'Model name is required.'
      : state.modelName && !MODEL_NAME_RE.test(state.modelName)
        ? 'Only letters, digits, underscores, and hyphens are allowed.'
        : null;

  const kError = state.splitMode === 'create' && state.k < 2 ? 'K must be ≥ 2.' : null;
  const splitSeedError =
    state.splitMode === 'create' && state.splitSeed < 0 ? 'Split seed must be ≥ 0.' : null;
  const pantherSeedError = state.pantherSeed < 0 ? 'PANTHER seed must be ≥ 0.' : null;
  const csvError =
    state.splitMode === 'create' && !state.sourceCsv.trim() ? 'Source CSV is required.' : null;
  const existingError =
    state.splitMode === 'existing' && !state.existingSplitName
      ? 'Pick an existing split.'
      : null;

  const formInvalid =
    !!modelError ||
    !state.modelName ||
    !state.featuresDir.trim() ||
    !!kError ||
    !!splitSeedError ||
    !!pantherSeedError ||
    !!csvError ||
    !!existingError;

  // --- per-fold size hint (create mode) -----------------------------------
  const foldHint = useMemo(() => {
    if (state.splitMode !== 'create') return null;
    if (sourceRows == null || kError) return null;
    const k = state.k;
    if (k < 2 || sourceRows < k) return null;
    const base = Math.floor(sourceRows / k);
    const test = base;
    const val = base;
    const train = sourceRows - test - val;
    return { k, train, val, test, total: sourceRows };
  }, [state.splitMode, sourceRows, state.k, kError]);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(commandPreview);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore
    }
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setResult(null);
    setModelTouched(true);
    if (formInvalid) {
      setError(
        modelError ??
          kError ??
          splitSeedError ??
          pantherSeedError ??
          csvError ??
          existingError ??
          'Form is invalid.',
      );
      return;
    }

    setSubmitting(true);
    try {
      const datasetName =
        state.splitMode === 'existing' && pickedExistingSplit
          ? pickedExistingSplit.dataset_name
          : state.modelName;
      const payload =
        state.splitMode === 'create'
          ? {
              model_name: state.modelName,
              features_dir: state.featuresDir.trim(),
              dataset_name: datasetName,
              source_csv: state.sourceCsv.trim(),
              k: state.k,
              split_seed: state.splitSeed,
              seed: state.pantherSeed,
              mode: state.mode,
              in_dim: state.inDim,
              n_proto_patches: state.nProtoPatches,
              n_proto: state.nProto,
              n_init: state.nInit,
              num_workers: state.numWorkers,
            }
          : {
              model_name: state.modelName,
              features_dir: state.featuresDir.trim(),
              dataset_name: datasetName,
              split_name: state.existingSplitName,
              seed: state.pantherSeed,
              mode: state.mode,
              in_dim: state.inDim,
              n_proto_patches: state.nProtoPatches,
              n_proto: state.nProto,
              n_init: state.nInit,
              num_workers: state.numWorkers,
            };
      const run = await startPantherRun(payload);
      setResult(run);
      if (run.summary.succeeded === 0) {
        setError(`All ${run.summary.total} folds failed.`);
      }
      // Refresh the splits list so a newly-created split appears.
      try {
        setSplits(await listSplits());
      } catch {
        // non-fatal
      }
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Failed to start run.';
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-slate-900">Prototype training with PANTHER</h2>
        <p className="text-sm text-slate-500">
          Train K prototype models via K-fold cross-validation. Each form submission produces K
          models from one PANTHER run group.
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
          <legend className="text-xs font-semibold uppercase tracking-wide text-slate-500">Dataset split</legend>
          <div className="flex gap-2">
            <ToggleButton
              active={state.splitMode === 'create'}
              onClick={() => update('splitMode', 'create')}
            >
              Create new split
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
                  <p className="mt-1 text-xs text-slate-500">{sourceRows.toLocaleString()} data rows.</p>
                ) : null}
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <NumberInput
                  label="K (number of folds)"
                  value={state.k}
                  onChange={(v) => update('k', Math.max(2, Math.round(v)))}
                  min={2}
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
              <p className="text-[11px] text-slate-500">
                Split seed controls the deterministic shuffle when partitioning rows into folds.
                It's stored on the saved split and never read again after creation. Unrelated to the
                PANTHER <code className="font-mono">--seed</code> below.
              </p>
              <p className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
                K-fold CV produces K folds. With K={state.k}: each fold uses{' '}
                {pctLabel((state.k - 2) / state.k)} train /{' '}
                {pctLabel(1 / state.k)} val /{' '}
                {pctLabel(1 / state.k)} test (1/K val, 1/K test, (K−2)/K train). Every slide appears
                in test exactly once across folds.
              </p>
              {foldHint ? (
                <p className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
                  With {foldHint.total.toLocaleString()} source rows and K={foldHint.k}: ~
                  {foldHint.train.toLocaleString()} train / {foldHint.val.toLocaleString()} val /{' '}
                  {foldHint.test.toLocaleString()} test per fold.
                </p>
              ) : null}
              {kError || splitSeedError || csvError ? (
                <ul className="space-y-1 text-xs text-rose-600">
                  {kError ? <li>{kError}</li> : null}
                  {splitSeedError ? <li>{splitSeedError}</li> : null}
                  {csvError ? <li>{csvError}</li> : null}
                </ul>
              ) : null}
            </div>
          ) : (
            <div className="space-y-3">
              {splitsError ? (
                <p className="text-xs text-rose-600">{splitsError}</p>
              ) : splits.length === 0 ? (
                <p className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
                  No saved splits yet. Switch to <em>Create new split</em> to make one.
                </p>
              ) : (
                <Field label="Existing split" htmlFor="existing_split">
                  <select
                    id="existing_split"
                    value={state.existingSplitName}
                    onChange={(e) => update('existingSplitName', e.target.value)}
                    className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-sm shadow-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
                  >
                    <option value="">— select a split —</option>
                    {splits.map((s) => {
                      const fold0 = s.per_fold_counts[0];
                      const sizes = fold0
                        ? `train ${fold0.train} / val ${fold0.val} / test ${fold0.test}`
                        : 'sizes unknown';
                      return (
                        <option key={s.id} value={s.split_name}>
                          {s.split_name} — K={s.k}, {sizes}, dataset {s.dataset_name}
                        </option>
                      );
                    })}
                  </select>
                </Field>
              )}
              {existingError ? (
                <ul className="space-y-1 text-xs text-rose-600">
                  <li>{existingError}</li>
                </ul>
              ) : null}
            </div>
          )}
        </fieldset>

        <fieldset className="space-y-3">
          <legend className="text-xs font-semibold uppercase tracking-wide text-slate-500">PANTHER parameters</legend>
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
          {pantherSeedError ? (
            <p className="text-xs text-rose-600">{pantherSeedError}</p>
          ) : null}
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
            Runs from <code className="font-mono">$PANTHER_REPO_PATH/src</code>. K models train
            sequentially; this may take a while.
          </p>
        </div>

        {error ? (
          <div className="flex items-start justify-between gap-3 rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
            <span className="whitespace-pre-wrap font-mono text-xs">{error}</span>
            <button
              type="button"
              onClick={() => setError(null)}
              aria-label="Dismiss"
              className="text-rose-500 hover:text-rose-800"
            >
              ×
            </button>
          </div>
        ) : null}

        {result ? (
          <div
            className={`rounded-md border px-4 py-3 text-sm ${
              result.summary.failed === 0
                ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
                : 'border-amber-200 bg-amber-50 text-amber-900'
            }`}
          >
            <div className="font-medium">
              Trained {result.summary.succeeded} / {result.summary.total} models
              {result.summary.failed > 0 ? ` (${result.summary.failed} failed)` : ''}
            </div>
            <dl className="mt-2 space-y-1 text-xs">
              <Row k="Group ID" v={result.group_id} />
              <Row k="Split" v={`${result.split_name} (K=${result.k})`} />
            </dl>
            <ul className="mt-3 space-y-1 text-xs font-mono">
              {result.models.map((m) => (
                <li key={m.model_id} className="flex items-center gap-2">
                  <span
                    className={`inline-block w-14 shrink-0 rounded px-1.5 py-0.5 text-center text-[10px] uppercase tracking-wide ${
                      m.status === 'ready'
                        ? 'bg-emerald-200 text-emerald-900'
                        : 'bg-rose-200 text-rose-900'
                    }`}
                  >
                    k={m.fold_index}
                  </span>
                  <span className="flex-1 break-all">{m.model_name}</span>
                  <span className="text-slate-500">{m.status}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs">
              <Link to={`/models?group=${result.group_id}`} className="underline hover:no-underline">
                View this run group in Models →
              </Link>
            </p>
          </div>
        ) : null}

        <button
          type="submit"
          disabled={submitting || formInvalid}
          className="w-full rounded-md bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? `Training ${effectiveK} models…` : `Train ${effectiveK} Models`}
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
      <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">{label}</label>
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

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-2">
      <dt className="w-20 shrink-0 text-slate-600">{k}</dt>
      <dd className="flex-1 break-all">{v}</dd>
    </div>
  );
}
