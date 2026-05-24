import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link, useParams } from 'react-router-dom';
import DirectoryBrowser from '../components/DirectoryBrowser';
import JobStatusPoller from '../components/JobStatusPoller';
import NotesThread from '../components/NotesThread';
import {
  ApiError,
  createInferences,
  getInference,
  getModel,
  getModelTridentParams,
  listInferenceExamplePatches,
  listInferences,
  lookupInference,
  rerunInference,
  resolveVizUrl,
  vizPlaceholderUrl,
  type ExamplePatchesResponse,
  type InferenceInfo,
  type ModelInfo,
  type TridentParamsResponse,
} from '../lib/api';

type Mode = 'single' | 'batch';

const WSI_EXTENSIONS = ['.svs', '.tif', '.tiff', '.ndpi', '.czi', '.zarr', '.sdpc'];

type CacheState = 'pending' | { hit: InferenceInfo } | { miss: true };

export default function InferencePage() {
  const { modelId = '' } = useParams<{ modelId: string }>();

  const [model, setModel] = useState<ModelInfo | null>(null);
  const [params, setParams] = useState<TridentParamsResponse | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);
  const [history, setHistory] = useState<InferenceInfo[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);

  const [mode, setMode] = useState<Mode>('single');
  const [browserOpen, setBrowserOpen] = useState(false);
  const [selectedPaths, setSelectedPaths] = useState<string[]>([]);
  const [cacheStates, setCacheStates] = useState<Record<string, CacheState>>({});
  const [rerunSet, setRerunSet] = useState<Set<string>>(() => new Set());

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // After submit: the inference IDs we're tracking (cache hits + freshly queued).
  const [trackingIds, setTrackingIds] = useState<string[]>([]);
  const [trackedInferences, setTrackedInferences] = useState<InferenceInfo[]>([]);
  const [activeResultId, setActiveResultId] = useState<string | null>(null);

  // --- Boot: fetch model + params + history --------------------------------
  useEffect(() => {
    if (!modelId) return;
    let cancelled = false;
    (async () => {
      try {
        const [m, tp, h] = await Promise.all([
          getModel(modelId),
          getModelTridentParams(modelId),
          listInferences({ modelId, limit: 50 }),
        ]);
        if (cancelled) return;
        setModel(m);
        setParams(tp);
        setHistory(h);
      } catch (err) {
        if (!cancelled) {
          setBootError(err instanceof ApiError ? err.message : 'Failed to load model.');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [modelId]);

  // --- Cache pre-check on selection ---------------------------------------
  useEffect(() => {
    if (!modelId || selectedPaths.length === 0) {
      setCacheStates({});
      return;
    }
    let cancelled = false;
    // Mark every selected path as pending so the UI shows a spinner.
    setCacheStates((prev) => {
      const next: Record<string, CacheState> = { ...prev };
      for (const p of selectedPaths) {
        if (!(p in next)) next[p] = 'pending';
      }
      // Drop entries no longer in the selection.
      for (const k of Object.keys(next)) {
        if (!selectedPaths.includes(k)) delete next[k];
      }
      return next;
    });
    (async () => {
      for (const p of selectedPaths) {
        try {
          const hit = await lookupInference(modelId, p);
          if (cancelled) return;
          setCacheStates((prev) => ({
            ...prev,
            [p]: hit ? { hit } : { miss: true },
          }));
        } catch {
          if (cancelled) return;
          // Treat lookup error as miss; the server will revalidate on POST.
          setCacheStates((prev) => ({ ...prev, [p]: { miss: true } }));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [modelId, selectedPaths]);

  // --- Poll tracked inferences after submit -------------------------------
  useEffect(() => {
    if (trackingIds.length === 0) {
      setTrackedInferences([]);
      return;
    }
    let cancelled = false;
    const poll = async () => {
      try {
        const fetched = await Promise.all(trackingIds.map((id) => getInference(id)));
        if (cancelled) return;
        setTrackedInferences(fetched);
        const allDone = fetched.every(
          (inf) => inf.status === 'ready' || inf.status === 'failed'
        );
        if (!allDone) {
          setTimeout(poll, 2000);
        }
      } catch {
        if (!cancelled) setTimeout(poll, 4000);
      }
    };
    poll();
    return () => {
      cancelled = true;
    };
  }, [trackingIds]);

  const onBrowserSingle = (path: string) => {
    setSelectedPaths([path]);
    setRerunSet(new Set());
    setBrowserOpen(false);
    setTrackingIds([]);
    setActiveResultId(null);
  };

  const onBrowserMulti = (paths: string[]) => {
    setSelectedPaths(paths);
    setRerunSet(new Set());
    setBrowserOpen(false);
    setTrackingIds([]);
    setActiveResultId(null);
  };

  const toggleRerun = (path: string) => {
    setRerunSet((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const aggregateCacheCounts = useMemo(() => {
    let cached = 0;
    let willProcess = 0;
    let pending = 0;
    for (const p of selectedPaths) {
      const s = cacheStates[p];
      if (!s || s === 'pending') pending += 1;
      else if ('hit' in s) {
        if (rerunSet.has(p)) willProcess += 1;
        else cached += 1;
      } else willProcess += 1;
    }
    return { cached, willProcess, pending };
  }, [selectedPaths, cacheStates, rerunSet]);

  const onRun = async () => {
    setSubmitError(null);
    if (!modelId || selectedPaths.length === 0) return;

    // Separate cache-hit short-circuit (no rerun) from paths needing processing.
    const cacheHits: InferenceInfo[] = [];
    const pathsToSend: string[] = [];
    let needsRerunFlag = false;

    for (const p of selectedPaths) {
      const s = cacheStates[p];
      if (s && s !== 'pending' && 'hit' in s && !rerunSet.has(p)) {
        cacheHits.push(s.hit);
      } else {
        pathsToSend.push(p);
        if (s && s !== 'pending' && 'hit' in s && rerunSet.has(p)) needsRerunFlag = true;
      }
    }

    // All cache hits, no rerun → no POST, just display.
    if (pathsToSend.length === 0) {
      const ids = cacheHits.map((c) => c.id);
      setTrackingIds(ids);
      setActiveResultId(ids[0] ?? null);
      return;
    }

    setSubmitting(true);
    try {
      // If any path was a cache hit toggled for re-run, we use the existing
      // rerun endpoint per-path; otherwise POST /api/inferences.
      const ids: string[] = [...cacheHits.map((c) => c.id)];

      if (needsRerunFlag) {
        // Single rerun-toggled cache hit per path.
        for (const p of pathsToSend) {
          const s = cacheStates[p];
          if (s && s !== 'pending' && 'hit' in s && rerunSet.has(p)) {
            const r = await rerunInference(s.hit.id);
            ids.push(r.new_inference_id);
          }
        }
        // Anything remaining is a true miss → batch POST below.
        const trueMisses = pathsToSend.filter((p) => {
          const s = cacheStates[p];
          return !(s && s !== 'pending' && 'hit' in s);
        });
        if (trueMisses.length > 0) {
          const res = await createInferences({
            model_id: modelId,
            wsi_paths: trueMisses,
          });
          for (const e of res.inferences) {
            if (e.id) ids.push(e.id);
          }
        }
      } else {
        const res = await createInferences({
          model_id: modelId,
          wsi_paths: pathsToSend,
        });
        for (const e of res.inferences) {
          if (e.id) ids.push(e.id);
        }
      }

      setTrackingIds(ids);
      setActiveResultId(ids[0] ?? null);

      // Refresh history in the background.
      try {
        const h = await listInferences({ modelId, limit: 50 });
        setHistory(h);
      } catch {
        /* non-fatal */
      }
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : 'Failed to start inference.');
    } finally {
      setSubmitting(false);
    }
  };

  const openHistoryResult = (inf: InferenceInfo) => {
    setTrackingIds([inf.id]);
    setActiveResultId(inf.id);
    setSelectedPaths([]);
    setCacheStates({});
  };

  // --- Render --------------------------------------------------------------

  if (bootError) {
    return (
      <div className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
        {bootError}
      </div>
    );
  }
  if (!model || !params) {
    return <p className="text-sm text-slate-500">Loading…</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <Link
          to={`/models/${encodeURIComponent(model.group_id)}`}
          className="text-xs text-slate-500 hover:text-slate-900"
        >
          ← {model.display_name || model.base_name}
        </Link>
        <h2 className="mt-1 text-xl font-semibold text-slate-900">
          Inference · Fold {model.fold_index + 1} of {model.fold_k}
        </h2>
        <p className="text-xs text-slate-500 font-mono">{model.model_name}</p>
      </div>

      <ParamsCard params={params} />

      <HistorySection
        open={historyOpen}
        onToggle={() => setHistoryOpen((v) => !v)}
        history={history}
        onOpen={openHistoryResult}
      />

      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <fieldset className="space-y-3">
          <legend className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Mode
          </legend>
          <div className="flex gap-2">
            <ModeButton active={mode === 'single'} onClick={() => setMode('single')}>
              Single slide
            </ModeButton>
            <ModeButton active={mode === 'batch'} onClick={() => setMode('batch')}>
              Batch (multiple slides)
            </ModeButton>
          </div>
        </fieldset>

        <div className="mt-4">
          <button
            type="button"
            onClick={() => setBrowserOpen(true)}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100"
          >
            {mode === 'single' ? 'Choose WSI file…' : 'Choose WSI files…'}
          </button>
          {selectedPaths.length > 0 ? (
            <p className="mt-2 text-xs text-slate-500">
              {mode === 'batch' ? `${selectedPaths.length} file(s) selected` : selectedPaths[0]}
            </p>
          ) : null}
        </div>

        {selectedPaths.length > 0 ? (
          <SelectionList
            paths={selectedPaths}
            cacheStates={cacheStates}
            rerunSet={rerunSet}
            onToggleRerun={toggleRerun}
          />
        ) : null}

        {selectedPaths.length > 0 && mode === 'batch' ? (
          <p className="mt-2 text-xs text-slate-500">
            {aggregateCacheCounts.cached} cached · {aggregateCacheCounts.willProcess} will
            process{aggregateCacheCounts.pending > 0 ? ` · ${aggregateCacheCounts.pending} checking…` : ''}
          </p>
        ) : null}

        {submitError ? (
          <div className="mt-3 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800">
            {submitError}
          </div>
        ) : null}

        <button
          type="button"
          onClick={onRun}
          disabled={submitting || selectedPaths.length === 0}
          className="mt-4 w-full rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting
            ? 'Queuing…'
            : mode === 'single'
              ? 'Run inference'
              : `Queue ${aggregateCacheCounts.willProcess || selectedPaths.length} job${
                  (aggregateCacheCounts.willProcess || selectedPaths.length) === 1 ? '' : 's'
                }`}
        </button>
      </div>

      {trackingIds.length > 0 ? (
        <ResultsSection
          mode={mode}
          model={model}
          inferences={trackedInferences}
          activeId={activeResultId}
          onActive={setActiveResultId}
        />
      ) : null}

      <DirectoryBrowser
        key={mode}
        open={browserOpen}
        mode="file"
        extensions={WSI_EXTENSIONS}
        onCancel={() => setBrowserOpen(false)}
        {...(mode === 'single'
          ? { onSelect: onBrowserSingle }
          : { onSelectMulti: onBrowserMulti })}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ParamsCard({ params }: { params: TridentParamsResponse }) {
  if (!params.patch_encoder) {
    return (
      <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
        This model has no recorded TRIDENT run. Inference can't be queued without
        knowing the patch encoder / magnification / patch size used at training time.
      </div>
    );
  }
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
      <p className="font-medium text-slate-900">This model expects:</p>
      <dl className="mt-1 grid grid-cols-[140px_1fr] gap-x-3 gap-y-1 font-mono text-xs">
        <dt className="text-slate-500">Patch encoder</dt>
        <dd>{params.patch_encoder}</dd>
        <dt className="text-slate-500">Magnification</dt>
        <dd>{params.mag}×</dd>
        <dt className="text-slate-500">Patch size</dt>
        <dd>{params.patch_size}px</dd>
        <dt className="text-slate-500">GPUs</dt>
        <dd>{params.gpus ?? '0'}</dd>
        <dt className="text-slate-500">Features dir</dt>
        <dd>{params.expected_features_dir_name ?? '—'}</dd>
      </dl>
      <p className="mt-2 text-xs text-slate-500">
        New slides will be processed with these settings automatically.
      </p>
    </div>
  );
}

function HistorySection({
  open,
  onToggle,
  history,
  onOpen,
}: {
  open: boolean;
  onToggle: () => void;
  history: InferenceInfo[];
  onOpen: (inf: InferenceInfo) => void;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <span className="text-sm font-medium text-slate-900">
          Previous inferences for this fold model ({history.length})
        </span>
        <span className="text-xs text-slate-500">{open ? 'Hide' : 'Show'}</span>
      </button>
      {open ? (
        history.length === 0 ? (
          <p className="border-t border-slate-200 px-4 py-3 text-xs text-slate-500">
            No inferences yet.
          </p>
        ) : (
          <ul className="divide-y divide-slate-200 border-t border-slate-200">
            {history.map((inf) => (
              <li
                key={inf.id}
                className="flex items-center justify-between px-4 py-2 text-xs hover:bg-slate-50"
              >
                <button
                  type="button"
                  onClick={() => onOpen(inf)}
                  className="flex-1 truncate text-left font-mono text-slate-700 hover:text-slate-900"
                >
                  {inf.wsi_filename}
                </button>
                <span className="ml-3 shrink-0">
                  <InferenceStatusPill status={inf.status} />
                </span>
                <span className="ml-3 shrink-0 text-slate-500">
                  {new Date(inf.created_at).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        )
      ) : null}
    </div>
  );
}

function SelectionList({
  paths,
  cacheStates,
  rerunSet,
  onToggleRerun,
}: {
  paths: string[];
  cacheStates: Record<string, CacheState>;
  rerunSet: Set<string>;
  onToggleRerun: (path: string) => void;
}) {
  return (
    <ul className="mt-3 divide-y divide-slate-200 rounded-md border border-slate-200">
      {paths.map((p) => {
        const s = cacheStates[p];
        const basename = p.split('/').pop() ?? p;
        return (
          <li key={p} className="flex items-center justify-between px-3 py-2 text-xs">
            <span className="flex-1 truncate font-mono text-slate-700" title={p}>
              {basename}
            </span>
            <span className="ml-3 shrink-0">
              {!s || s === 'pending' ? (
                <span className="text-slate-400">checking…</span>
              ) : 'hit' in s ? (
                <span className="flex items-center gap-2">
                  <span className="text-emerald-700">✓ Cached</span>
                  <label className="flex items-center gap-1 text-slate-600">
                    <input
                      type="checkbox"
                      checked={rerunSet.has(p)}
                      onChange={() => onToggleRerun(p)}
                      className="h-3.5 w-3.5"
                    />
                    Re-run
                  </label>
                </span>
              ) : (
                <span className="text-slate-500">○ Will be processed</span>
              )}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function ResultsSection({
  mode,
  model,
  inferences,
  activeId,
  onActive,
}: {
  mode: Mode;
  model: ModelInfo;
  inferences: InferenceInfo[];
  activeId: string | null;
  onActive: (id: string) => void;
}) {
  const active = inferences.find((i) => i.id === activeId) ?? inferences[0];

  if (mode === 'batch' && inferences.length > 1) {
    const ready = inferences.filter((i) => i.status === 'ready').length;
    const failed = inferences.filter((i) => i.status === 'failed').length;
    const running = inferences.length - ready - failed;
    return (
      <div className="space-y-3">
        <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3 text-sm">
          <p className="font-medium text-slate-900">Batch progress</p>
          <p className="mt-1 text-xs text-slate-600">
            {ready}/{inferences.length} ready
            {running > 0 ? ` · ${running} running` : ''}
            {failed > 0 ? ` · ${failed} failed` : ''}
          </p>
        </div>
        <ul className="divide-y divide-slate-200 rounded-md border border-slate-200">
          {inferences.map((inf) => (
            <li
              key={inf.id}
              className={`flex items-center gap-3 px-3 py-2 text-xs ${
                activeId === inf.id ? 'bg-slate-100' : 'hover:bg-slate-50'
              }`}
            >
              <button
                type="button"
                onClick={() => onActive(inf.id)}
                className="flex-1 truncate text-left font-mono text-slate-700 hover:text-slate-900"
              >
                {inf.wsi_filename}
              </button>
              <InferenceStatusPill status={inf.status} />
              {inf.error_message ? (
                <span className="text-rose-600" title={inf.error_message}>
                  ⚠
                </span>
              ) : null}
            </li>
          ))}
        </ul>
        {active ? <SingleResultView inference={active} model={model} /> : null}
      </div>
    );
  }

  if (!active) return null;
  return (
    <div className="space-y-3">
      <JobStatusPoller refTable="inferences" refId={active.id} />
      <SingleResultView inference={active} model={model} />
    </div>
  );
}

function SingleResultView({
  inference,
  model,
}: {
  inference: InferenceInfo;
  model: ModelInfo;
}) {
  const [tsneOpen, setTsneOpen] = useState(false);

  if (inference.status === 'failed') {
    return (
      <div className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
        <p className="font-medium">Inference failed for {inference.wsi_filename}</p>
        {inference.error_message ? (
          <pre className="mt-1 whitespace-pre-wrap font-mono text-xs">{inference.error_message}</pre>
        ) : null}
      </div>
    );
  }

  if (inference.status !== 'ready') {
    return (
      <div className="rounded-md border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900">
        <p>
          {inference.wsi_filename}: <InferenceStatusPill status={inference.status} />
        </p>
        <p className="mt-1 text-xs">Polling for completion…</p>
      </div>
    );
  }

  return (
    <div className="space-y-5 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div>
        <p className="text-xs text-slate-500">Slide</p>
        <p className="font-mono text-sm text-slate-900">{inference.wsi_filename}</p>
      </div>

      <section>
        <SectionHeader title="Assignment heatmap" />
        <img
          src={resolveVizUrl(
            inference.heatmap_path,
            () => vizPlaceholderUrl('heatmap', { label: 'Heatmap', width: 800, height: 500 })
          )}
          alt="Assignment heatmap"
          className="mt-2 w-full rounded border border-slate-200 bg-white"
        />
      </section>

      <section>
        <SectionHeader title="Mixture" />
        <img
          src={resolveVizUrl(
            inference.mixture_plot_path,
            () => vizPlaceholderUrl('mixture', { label: 'Mixture', width: 600, height: 300 })
          )}
          alt="Mixture plot"
          className="mt-2 w-full max-w-xl rounded border border-slate-200 bg-white"
        />
      </section>

      <section>
        <SectionHeader title="Example patches" />
        <ExamplePatchesGrid inferenceId={inference.id} nProto={model.n_proto} />
      </section>

      <section>
        <button
          type="button"
          onClick={() => setTsneOpen((v) => !v)}
          className="flex w-full items-center justify-between text-left"
        >
          <SectionHeader title="t-SNE (per slide)" />
          <span className="text-xs text-slate-500">{tsneOpen ? 'Hide' : 'Show'}</span>
        </button>
        {tsneOpen ? (
          <img
            src={resolveVizUrl(
              inference.tsne_path,
              () => vizPlaceholderUrl('tsne', { label: 't-SNE', width: 600, height: 500 })
            )}
            alt="t-SNE"
            className="mt-2 w-full max-w-xl rounded border border-slate-200 bg-white"
          />
        ) : null}
      </section>

      <section>
        <SectionHeader title="Dataset-wide reference" />
        <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <DatasetReferenceTile
            label="Top-K representative patches"
            src={resolveVizUrl(
              model.topk_grid_path,
              () =>
                vizPlaceholderUrl('topk', {
                  label: `${model.n_proto} × ${model.topk_per_proto}`,
                  width: 720,
                  height: 320,
                })
            )}
          />
          <DatasetReferenceTile
            label="UMAP"
            src={resolveVizUrl(
              model.umap_path,
              () => vizPlaceholderUrl('umap', { label: 'UMAP', width: 720, height: 320 })
            )}
          />
        </div>
      </section>

      <section>
        <SectionHeader title="Notes" />
        <div className="mt-2">
          <NotesThread target={{ kind: 'inference', inferenceId: inference.id }} />
        </div>
      </section>
    </div>
  );
}

function ExamplePatchesGrid({
  inferenceId,
  nProto,
}: {
  inferenceId: string;
  nProto: number;
}) {
  const [data, setData] = useState<ExamplePatchesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const res = await listInferenceExamplePatches(inferenceId);
        if (!cancelled) setData(res);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Failed to load patches.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [inferenceId]);

  if (loading) {
    return <p className="mt-2 text-xs text-slate-500">Loading patches…</p>;
  }
  if (error) {
    return (
      <p className="mt-2 rounded border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800">
        {error}
      </p>
    );
  }
  if (!data || data.groups.length === 0) {
    return (
      <div className="mt-2">
        <img
          src={vizPlaceholderUrl('patches', {
            label: `${nProto} × example patches`,
            width: 720,
            height: 320,
          })}
          alt="Example patches"
          className="w-full rounded border border-slate-200 bg-white"
        />
        <p className="mt-1 text-[11px] text-slate-500">
          No patches on disk yet — the inference handler hasn't written them, or the
          directory was cleaned. Showing placeholder.
        </p>
      </div>
    );
  }

  return (
    <div className="mt-2">
      <div className="overflow-x-auto">
        <table className="border-separate border-spacing-1">
          <tbody>
            {data.groups.map((g) => (
              <tr key={g.prototype_index}>
                <td className="pr-2 text-right align-middle text-[11px] text-slate-500 whitespace-nowrap">
                  <div className="font-mono text-slate-800">P{g.prototype_index}</div>
                  {g.label ? <div className="italic">{g.label}</div> : null}
                </td>
                {g.urls.map((u, i) => (
                  <td key={i} className="align-middle">
                    <button
                      type="button"
                      onClick={() => setLightbox(u)}
                      className="block focus:outline-none focus:ring-2 focus:ring-slate-500"
                      aria-label={`Enlarge patch ${i + 1} of prototype ${g.prototype_index}`}
                    >
                      <img
                        src={u}
                        alt={`Prototype ${g.prototype_index} patch ${i + 1}`}
                        className="h-16 w-16 cursor-zoom-in rounded border border-slate-200 bg-slate-50 object-cover hover:border-slate-500"
                      />
                    </button>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {lightbox ? <Lightbox src={lightbox} onClose={() => setLightbox(null)} /> : null}
    </div>
  );
}

function Lightbox({ src, onClose }: { src: string; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return createPortal(
    <div
      role="presentation"
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/75 p-6 backdrop-blur-sm"
    >
      <img
        src={src}
        alt="Patch"
        onClick={(e) => e.stopPropagation()}
        className="max-h-full max-w-full rounded shadow-xl"
      />
      <button
        type="button"
        onClick={onClose}
        className="absolute right-4 top-4 rounded-full bg-white/90 px-3 py-1 text-sm font-medium text-slate-800 shadow hover:bg-white"
      >
        Close ✕
      </button>
    </div>,
    document.body
  );
}

function DatasetReferenceTile({ label, src }: { label: string; src: string }) {
  return (
    <div>
      <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">{label}</p>
      <img
        src={src}
        alt={label}
        className="w-full rounded border border-slate-200 bg-white"
      />
    </div>
  );
}

function SectionHeader({ title }: { title: string }) {
  return (
    <h4 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{title}</h4>
  );
}

function ModeButton({
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

function InferenceStatusPill({ status }: { status: InferenceInfo['status'] }) {
  const tones: Record<InferenceInfo['status'], string> = {
    queued: 'bg-slate-100 text-slate-700 border-slate-200',
    running_trident: 'bg-blue-50 text-blue-800 border-blue-200 animate-pulse',
    running_viz: 'bg-violet-50 text-violet-800 border-violet-200 animate-pulse',
    ready: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    failed: 'bg-rose-50 text-rose-800 border-rose-200',
  };
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${tones[status]}`}
    >
      {status.replace('_', ' ')}
    </span>
  );
}
