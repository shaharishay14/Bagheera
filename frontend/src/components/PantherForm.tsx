import { useEffect, useMemo, useState } from 'react';
import DirectoryBrowser from './DirectoryBrowser';
import {
  ApiError,
  getCsvRowCount,
  startPantherRun,
  type PantherMode,
  type PantherRunResponse,
} from '../lib/api';

const DATASET_NAME_RE = /^[A-Za-z0-9_-]+$/;
const MODES: PantherMode[] = ['faiss', 'kmeans'];

interface PantherFormState {
  datasetName: string;
  featuresDir: string;
  sourceCsv: string;
  trainPct: number;
  valPct: number;
  testPct: number;
  nChunks: number;
  mode: PantherMode;
  inDim: number;
  nProtoPatches: number;
  nProto: number;
  nInit: number;
  seed: number;
  numWorkers: number;
}

const INITIAL: PantherFormState = {
  datasetName: '',
  featuresDir: '',
  sourceCsv: '',
  trainPct: 0,
  valPct: 0,
  testPct: 0,
  nChunks: 2,
  mode: 'faiss',
  inDim: 1024,
  nProtoPatches: 1_000_000,
  nProto: 16,
  nInit: 5,
  seed: 1,
  numWorkers: 10,
};

function shellQuote(s: string): string {
  if (!s) return s;
  if (/^[\w./-]+$/.test(s)) return s;
  return `'${s.replace(/'/g, `'\\''`)}'`;
}

function buildCommandPreview(s: PantherFormState): string {
  const features = shellQuote(s.featuresDir.trim() || '<features_dir>');
  const split = `splits/${s.datasetName || '<dataset_name>'}`;
  return [
    'CUDA_VISIBLE_DEVICES=0 python -m training.main_prototype',
    `--mode ${s.mode}`,
    `--data_source ${features}`,
    `--split_dir ${split}`,
    `--split_names train`,
    `--in_dim ${s.inDim}`,
    `--n_proto_patches ${s.nProtoPatches}`,
    `--n_proto ${s.nProto}`,
    `--n_init ${s.nInit}`,
    `--seed ${s.seed}`,
    `--num_workers ${s.numWorkers}`,
  ].join(' \\\n  ');
}

export default function PantherForm() {
  const [state, setState] = useState<PantherFormState>(INITIAL);
  const [datasetTouched, setDatasetTouched] = useState(false);
  const [browser, setBrowser] = useState<null | 'features' | 'source'>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PantherRunResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const [sourceRows, setSourceRows] = useState<number | null>(null);
  const [rowsLoading, setRowsLoading] = useState(false);
  const [rowsError, setRowsError] = useState<string | null>(null);

  const update = <K extends keyof PantherFormState>(key: K, value: PantherFormState[K]) =>
    setState((prev) => ({ ...prev, [key]: value }));

  useEffect(() => {
    setSourceRows(null);
    setRowsError(null);
    const csv = state.sourceCsv.trim();
    if (!csv) return;
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
  }, [state.sourceCsv]);

  const commandPreview = useMemo(() => buildCommandPreview(state), [state]);

  // --- validation ---------------------------------------------------------
  const datasetError =
    datasetTouched && !state.datasetName
      ? 'Dataset name is required.'
      : state.datasetName && !DATASET_NAME_RE.test(state.datasetName)
        ? 'Only letters, digits, underscores, and hyphens are allowed.'
        : null;

  const pctSum = state.trainPct + state.valPct + state.testPct;
  const pctSumError = pctSum > 100 ? 'Train + validation + test must be ≤ 100.' : null;
  const pctZeroError =
    state.trainPct <= 0 || state.valPct <= 0 || state.testPct <= 0
      ? 'Train, validation, and test must each be > 0.'
      : null;
  const nChunksError = state.nChunks < 2 ? 'n must be ≥ 2.' : null;
  const seedError = state.seed < 0 ? 'Seed must be ≥ 0.' : null;

  const formInvalid =
    !!datasetError ||
    !state.datasetName ||
    !state.featuresDir.trim() ||
    !state.sourceCsv.trim() ||
    !!pctSumError ||
    !!pctZeroError ||
    !!nChunksError ||
    !!seedError;

  // --- live split hint ----------------------------------------------------
  const splitHint = useMemo(() => {
    if (sourceRows == null || pctSumError || pctZeroError || nChunksError) return null;
    const perChunk = Math.floor(sourceRows / state.nChunks);
    if (perChunk <= 0) return null;
    const tr = Math.round((perChunk * state.trainPct) / 100);
    const va = Math.round((perChunk * state.valPct) / 100);
    const te = Math.round((perChunk * state.testPct) / 100);
    return {
      perChunk,
      tr,
      va,
      te,
      total: { tr: tr * state.nChunks, va: va * state.nChunks, te: te * state.nChunks },
    };
  }, [sourceRows, state.nChunks, state.trainPct, state.valPct, state.testPct, pctSumError, pctZeroError, nChunksError]);

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
    setDatasetTouched(true);
    if (formInvalid) {
      setError(datasetError ?? pctSumError ?? pctZeroError ?? nChunksError ?? 'Form is invalid.');
      return;
    }

    setSubmitting(true);
    try {
      const run = await startPantherRun({
        dataset_name: state.datasetName,
        features_dir: state.featuresDir.trim(),
        source_csv: state.sourceCsv.trim(),
        train_pct: state.trainPct,
        val_pct: state.valPct,
        test_pct: state.testPct,
        n_chunks: state.nChunks,
        mode: state.mode,
        in_dim: state.inDim,
        n_proto_patches: state.nProtoPatches,
        n_proto: state.nProto,
        n_init: state.nInit,
        seed: state.seed,
        num_workers: state.numWorkers,
      });
      setResult(run);
      if (run.status === 'failed') {
        setError(run.stderr || `Run failed (exit code ${run.return_code ?? '?'}).`);
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
          Stratify the source CSV into train/val/test splits and train prototypes over the TRIDENT features.
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

        <Field label="Dataset name" htmlFor="dataset_name">
          <input
            id="dataset_name"
            type="text"
            value={state.datasetName}
            onChange={(e) => update('datasetName', e.target.value)}
            onBlur={() => setDatasetTouched(true)}
            placeholder="e.g., tcga_brca_pilot"
            aria-invalid={!!datasetError}
            aria-describedby={datasetError ? 'dataset_name_error' : undefined}
            className={`block w-full rounded-md border bg-white px-3 py-2 font-mono text-sm shadow-sm focus:outline-none focus:ring-1 ${
              datasetError
                ? 'border-rose-400 focus:border-rose-500 focus:ring-rose-500'
                : 'border-slate-300 focus:border-slate-500 focus:ring-slate-500'
            }`}
          />
          {datasetError ? (
            <p id="dataset_name_error" className="mt-1 text-xs text-rose-600">
              {datasetError}
            </p>
          ) : null}
        </Field>

        <fieldset className="space-y-3">
          <legend className="text-xs font-semibold uppercase tracking-wide text-slate-500">Dataset split</legend>
          <div className="grid grid-cols-4 gap-3">
            <NumberInput
              label="Train %"
              value={state.trainPct}
              onChange={(v) => update('trainPct', v)}
              min={0}
              max={100}
              step={1}
            />
            <NumberInput
              label="Validation %"
              value={state.valPct}
              onChange={(v) => update('valPct', v)}
              min={0}
              max={100}
              step={1}
            />
            <NumberInput
              label="Test %"
              value={state.testPct}
              onChange={(v) => update('testPct', v)}
              min={0}
              max={100}
              step={1}
            />
            <NumberInput
              label="CV chunks (n)"
              value={state.nChunks}
              onChange={(v) => update('nChunks', Math.max(2, Math.round(v)))}
              min={2}
              step={1}
            />
          </div>
          <NumberInput
            label="Random seed"
            value={state.seed}
            onChange={(v) => update('seed', Math.max(0, Math.round(v)))}
            min={0}
            step={1}
            className="w-32"
          />
          {pctSumError || pctZeroError || nChunksError || seedError ? (
            <ul className="space-y-1 text-xs text-rose-600">
              {pctSumError ? <li>{pctSumError}</li> : null}
              {pctZeroError ? <li>{pctZeroError}</li> : null}
              {nChunksError ? <li>{nChunksError}</li> : null}
              {seedError ? <li>{seedError}</li> : null}
            </ul>
          ) : null}
          {splitHint ? (
            <p className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
              With {sourceRows?.toLocaleString()} source rows and n={state.nChunks}: ~{splitHint.perChunk} per chunk →{' '}
              {splitHint.tr} train, {splitHint.va} validation, {splitHint.te} test per chunk → {splitHint.total.tr.toLocaleString()}{' '}
              train / {splitHint.total.va.toLocaleString()} validation / {splitHint.total.te.toLocaleString()} test total.
            </p>
          ) : null}
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
          </div>
        </fieldset>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-wide text-slate-500">Command preview</span>
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
            Runs from <code className="font-mono">$PANTHER_REPO_PATH/src</code>.
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

        {result && result.status === 'succeeded' ? (
          <div className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
            <div className="font-medium">Run {result.status}</div>
            <dl className="mt-2 space-y-1 text-xs">
              <Row k="Run ID" v={result.id} />
              <Row k="Status" v={result.status} />
              <Row
                k="Splits"
                v={`train ${result.split_counts.train} / val ${result.split_counts.val} / test ${result.split_counts.test} / unused ${result.split_counts.unused} / total ${result.split_counts.total}`}
              />
            </dl>
          </div>
        ) : null}

        <button
          type="submit"
          disabled={submitting || formInvalid}
          className="w-full rounded-md bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? 'Running…' : 'Start PANTHER'}
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
      <dt className="w-20 shrink-0 text-emerald-700/70">{k}</dt>
      <dd className="flex-1 break-all">{v}</dd>
    </div>
  );
}
