import { useMemo, useState } from 'react';
import EncoderSelect, { patchSizeFor } from './EncoderSelect';
import DirectoryBrowser from './DirectoryBrowser';
import {
  ApiError,
  startTridentRun,
  type PatchEncoder,
  type TridentRunResponse,
} from '../lib/api';

const MAG = 20;
const TASK = 'feat';
const JOB_DIR_ROOT = './trident_processed';
const DATASET_NAME_RE = /^[A-Za-z0-9_-]+$/;

function jobDirFor(dataset: string): string {
  return `${JOB_DIR_ROOT}/${dataset || '<dataset_name>'}`;
}

function outputDirFor(dataset: string, encoder: PatchEncoder): string {
  const ps = patchSizeFor(encoder);
  return `${jobDirFor(dataset)}/${MAG}x_${ps}px_0px_overlap/features_${encoder}`;
}

function buildCommandPreview(
  dataset: string,
  wsiDir: string,
  encoder: PatchEncoder
): string {
  const patchSize = patchSizeFor(encoder);
  const wsi = wsiDir.trim() || '<wsi_dir>';
  return [
    'python run_batch_of_slides.py',
    `--task ${TASK}`,
    `--wsi_dir ${shellQuote(wsi)}`,
    `--job_dir ${shellQuote(jobDirFor(dataset))}`,
    `--patch_encoder ${encoder}`,
    `--mag ${MAG}`,
    `--patch_size ${patchSize}`,
  ].join(' \\\n  ');
}

function shellQuote(s: string): string {
  if (/^[\w./-]+$/.test(s)) return s;
  return `'${s.replace(/'/g, `'\\''`)}'`;
}

export default function TridentForm() {
  const [datasetName, setDatasetName] = useState('');
  const [datasetTouched, setDatasetTouched] = useState(false);
  const [wsiDir, setWsiDir] = useState('');
  const [encoder, setEncoder] = useState<PatchEncoder>('uni_v1');
  const [browserOpen, setBrowserOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TridentRunResponse | null>(null);
  const [copied, setCopied] = useState(false);

  const patchSize = patchSizeFor(encoder);
  const jobDir = jobDirFor(datasetName);
  const commandPreview = useMemo(
    () => buildCommandPreview(datasetName, wsiDir, encoder),
    [datasetName, wsiDir, encoder]
  );

  const datasetError =
    datasetTouched && !datasetName
      ? 'Dataset name is required.'
      : datasetName && !DATASET_NAME_RE.test(datasetName)
        ? 'Only letters, digits, underscores, and hyphens are allowed.'
        : null;

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(commandPreview);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard might be unavailable in non-secure contexts; ignore.
    }
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setResult(null);
    setDatasetTouched(true);

    if (!datasetName || !DATASET_NAME_RE.test(datasetName)) {
      setError(datasetError ?? 'Invalid dataset name.');
      return;
    }
    if (!wsiDir.trim()) {
      setError('WSI directory is required.');
      return;
    }

    setSubmitting(true);
    try {
      const run = await startTridentRun({
        dataset_name: datasetName,
        wsi_dir: wsiDir.trim(),
        patch_encoder: encoder,
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
        <h2 className="text-xl font-semibold text-slate-900">Pre-processing with TRIDENT</h2>
        <p className="text-sm text-slate-500">Feature extraction over a directory of whole-slide images.</p>
      </div>

      <form onSubmit={onSubmit} className="space-y-5 rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <Field label="Dataset name" htmlFor="dataset_name">
          <input
            id="dataset_name"
            type="text"
            value={datasetName}
            onChange={(e) => setDatasetName(e.target.value)}
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

        <LockedField label="Task" value={TASK} />

        <Field label="WSI directory" htmlFor="wsi_dir">
          <div className="flex gap-2">
            <input
              id="wsi_dir"
              type="text"
              value={wsiDir}
              onChange={(e) => setWsiDir(e.target.value)}
              placeholder="/data/wsis/batch_2024"
              className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-sm shadow-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
            />
            <button
              type="button"
              onClick={() => setBrowserOpen(true)}
              className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 hover:bg-slate-100"
            >
              Browse…
            </button>
          </div>
        </Field>

        <LockedField label="Job directory" value={jobDir} mono />

        <Field label="Patch encoder" htmlFor="patch_encoder">
          <EncoderSelect id="patch_encoder" value={encoder} onChange={setEncoder} />
        </Field>

        <div className="grid grid-cols-2 gap-4">
          <LockedField label="Magnification" value={`${MAG}`} />
          <LockedField label="Patch size" value={`${patchSize}`} />
        </div>

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
              <Row k="Output" v={outputDirFor(result.dataset_name, result.patch_encoder)} mono />
            </dl>
          </div>
        ) : null}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? 'Running…' : 'Start TRIDENT'}
        </button>
      </form>

      <DirectoryBrowser
        open={browserOpen}
        initialPath={wsiDir || undefined}
        onCancel={() => setBrowserOpen(false)}
        onSelect={(p) => {
          setWsiDir(p);
          setBrowserOpen(false);
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

function LockedField({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="mb-1 flex items-center gap-1 text-xs font-medium uppercase tracking-wide text-slate-500">
        <span>{label}</span>
        <LockIcon />
      </div>
      <div
        className={`rounded-md border border-slate-200 bg-slate-100 px-3 py-2 text-sm text-slate-600 ${
          mono ? 'font-mono' : ''
        }`}
      >
        {value}
      </div>
    </div>
  );
}

function LockIcon() {
  return (
    <svg
      width="11"
      height="11"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-slate-400"
      aria-hidden="true"
    >
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}

function Row({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex gap-2">
      <dt className="w-20 shrink-0 text-emerald-700/70">{k}</dt>
      <dd className={`flex-1 break-all ${mono ? 'font-mono' : ''}`}>{v}</dd>
    </div>
  );
}
