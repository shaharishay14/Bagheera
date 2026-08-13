import { useEffect, useRef, useState } from 'react';
import { FiChevronDown, FiImage, FiPlus, FiRefreshCw, FiX } from 'react-icons/fi';
import CompareModelPanel from '../components/CompareModelPanel';
import { Card, Chip, SectionHeader } from '../components/ui';
import { type Transform } from '../components/ZoomPanImage';
import {
  ApiError,
  getDatasetModels,
  getDatasetSlides,
  listDatasets,
  type DatasetSlide,
  type DatasetSlidesResponse,
  type DatasetSummary,
  type ModelInfo,
} from '../lib/api';

const MAX_MODELS = 4;
const IDENTITY_TRANSFORM: Transform = { scale: 1, tx: 0, ty: 0 };

/**
 * Grid class for the comparison columns: 1–3 models sit in a single responsive
 * row; 4 models wrap into a 2×2 grid. Exported (pure) for unit testing.
 */
export function compareGridClass(count: number): string {
  if (count >= 4) return 'grid grid-cols-1 gap-6 lg:grid-cols-2';
  if (count === 3) return 'grid grid-cols-1 gap-6 lg:grid-cols-3';
  if (count === 2) return 'grid grid-cols-1 gap-6 lg:grid-cols-2';
  return 'grid grid-cols-1 gap-6';
}

/**
 * Model Comparison — pick a dataset, then one WSI, then up to four of that
 * dataset's models, and view every model's paper-style panels for that slide
 * side by side (optionally with pan/zoom mirrored across columns).
 */
export default function PantherComparePage() {
  // Step 1 — datasets.
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [datasetsLoading, setDatasetsLoading] = useState(true);
  const [datasetsError, setDatasetsError] = useState<string | null>(null);
  const [dataset, setDataset] = useState<string | null>(null);

  // Step 2 — slides (dataset-scoped).
  const [slidesResp, setSlidesResp] = useState<DatasetSlidesResponse | null>(null);
  const [slidesLoading, setSlidesLoading] = useState(false);
  const [slidesError, setSlidesError] = useState<string | null>(null);
  const [slideId, setSlideId] = useState<string | null>(null);

  // Step 3 — models (dataset-scoped) + the chosen slots.
  const [datasetModels, setDatasetModels] = useState<ModelInfo[]>([]);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ModelInfo[]>([]);
  // Which slot the picker is targeting: 'add' opens a new slot, a number swaps it.
  const [picker, setPicker] = useState<'add' | number | null>(null);

  // Step 5 — sync pan/zoom lifted here and mirrored to every panel.
  const [syncEnabled, setSyncEnabled] = useState(false);
  const [syncTransform, setSyncTransform] = useState<Transform>(IDENTITY_TRANSFORM);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await listDatasets();
        if (!cancelled) setDatasets(res);
      } catch (err) {
        if (!cancelled) {
          setDatasetsError(err instanceof ApiError ? err.message : 'Failed to load datasets.');
        }
      } finally {
        if (!cancelled) setDatasetsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Selecting a dataset resets everything downstream and loads its slides + models.
  useEffect(() => {
    if (!dataset) {
      setSlidesResp(null);
      setDatasetModels([]);
      return;
    }
    let cancelled = false;
    setSlideId(null);
    setSelected([]);
    setPicker(null);
    setSlidesResp(null);
    setDatasetModels([]);
    setSlidesLoading(true);
    setSlidesError(null);
    setModelsError(null);
    (async () => {
      try {
        const slides = await getDatasetSlides(dataset);
        if (!cancelled) setSlidesResp(slides);
      } catch (err) {
        if (!cancelled) {
          setSlidesError(err instanceof ApiError ? err.message : 'Failed to load slides.');
        }
      } finally {
        if (!cancelled) setSlidesLoading(false);
      }
      try {
        const models = await getDatasetModels(dataset);
        if (!cancelled) setDatasetModels(models);
      } catch (err) {
        if (!cancelled) {
          setModelsError(err instanceof ApiError ? err.message : 'Failed to load models.');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [dataset]);

  const selectedIds = new Set(selected.map((m) => m.id));

  const onPickModel = (model: ModelInfo) => {
    setSelected((prev) => {
      if (picker === 'add') {
        if (prev.length >= MAX_MODELS || prev.some((m) => m.id === model.id)) return prev;
        return [...prev, model];
      }
      if (typeof picker === 'number') {
        const next = [...prev];
        next[picker] = model;
        return next;
      }
      return prev;
    });
    setPicker(null);
  };

  const removeSlot = (index: number) => {
    setSelected((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-8">
      <header>
        <SectionHeader title="PANTHER" />
        <h1 className="mt-1 text-2xl font-bold tracking-tight text-ink">Model comparison</h1>
        <p className="mt-1.5 text-sm text-ink-muted">
          Render one slide through several models side by side — Section A ROI analysis, the
          per-slide similarity violin, the on-tissue embedding, and each model&apos;s prototype
          dictionary.
        </p>
      </header>

      {/* Step 1 — dataset selector. */}
      <Card className="p-4">
        <SectionHeader title="1 · Dataset" className="mb-3" />
        {datasetsLoading ? (
          <p className="text-sm text-ink-muted">Loading datasets…</p>
        ) : datasetsError ? (
          <ErrorNote>{datasetsError}</ErrorNote>
        ) : datasets.length === 0 ? (
          <p className="text-sm text-ink-faint">
            No datasets have a comparable single model yet — train one on the PANTHER page first.
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {datasets.map((d) => {
              const active = d.dataset_name === dataset;
              return (
                <button
                  key={d.dataset_name}
                  type="button"
                  onClick={() => setDataset(d.dataset_name)}
                  className={`inline-flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-sm font-semibold transition-colors ${
                    active
                      ? 'border-accent bg-accent-muted text-accent-text'
                      : 'border-border-strong bg-surface text-ink hover:bg-surface-subtle'
                  }`}
                >
                  <span className="font-mono">{d.dataset_name}</span>
                  <span className="text-[11px] font-normal text-ink-faint">
                    {d.model_count} model{d.model_count === 1 ? '' : 's'}
                    {d.slide_count != null ? ` · ${d.slide_count} slides` : ''}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </Card>

      {/* Step 2 — slide selector (gated on a dataset). */}
      <Card className={`p-4 ${dataset ? '' : 'pointer-events-none opacity-50'}`}>
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <SectionHeader title="2 · WSI" />
          {slidesResp ? (
            <span className="font-mono text-[11px] text-ink-faint">
              thumbnails: {slidesResp.thumbnails_found}/{slidesResp.slide_count}
            </span>
          ) : null}
        </div>
        {!dataset ? (
          <p className="text-sm text-ink-faint">Pick a dataset first.</p>
        ) : slidesLoading ? (
          <p className="text-sm text-ink-muted">Loading slides…</p>
        ) : slidesError ? (
          <ErrorNote>{slidesError}</ErrorNote>
        ) : slidesResp && slidesResp.slides.length > 0 ? (
          <>
            {slidesResp.note ? (
              <p className="mb-3 text-[11px] text-ink-faint">{slidesResp.note}</p>
            ) : null}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
              {slidesResp.slides.map((slide) => (
                <SlideTile
                  key={slide.slide_id}
                  slide={slide}
                  active={slide.slide_id === slideId}
                  onSelect={() => setSlideId(slide.slide_id)}
                />
              ))}
            </div>
          </>
        ) : (
          <p className="text-sm text-ink-faint">No slides found for this dataset.</p>
        )}
      </Card>

      {/* Step 3 — model slots (gated on a dataset). */}
      <Card className={`p-4 ${dataset ? '' : 'pointer-events-none opacity-50'}`}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <SectionHeader title="3 · Models" />
          <label className="flex items-center gap-2 text-xs font-semibold text-ink-muted">
            <input
              type="checkbox"
              checked={syncEnabled}
              onChange={(e) => {
                setSyncEnabled(e.target.checked);
                setSyncTransform(IDENTITY_TRANSFORM);
              }}
              className="h-3.5 w-3.5 accent-[rgb(var(--accent))]"
            />
            Sync zoom/pan across models
          </label>
        </div>

        {modelsError ? <ErrorNote>{modelsError}</ErrorNote> : null}

        <div className="flex flex-wrap items-center gap-2">
          {selected.map((m, i) => (
            <div
              key={`${m.id}-${i}`}
              className="inline-flex items-center gap-1.5 rounded-full border border-border-strong bg-surface-subtle py-1 pl-3 pr-1.5 text-xs"
            >
              <span className="max-w-[10rem] truncate font-semibold text-ink" title={m.display_name}>
                {m.display_name || m.base_name}
              </span>
              <button
                type="button"
                onClick={() => setPicker(picker === i ? null : i)}
                title="Swap this model"
                className="grid h-5 w-5 place-items-center rounded-full text-ink-faint hover:bg-surface hover:text-ink transition-colors"
              >
                <FiRefreshCw size={12} />
              </button>
              <button
                type="button"
                onClick={() => removeSlot(i)}
                title="Remove this model"
                className="grid h-5 w-5 place-items-center rounded-full text-ink-faint hover:bg-surface hover:text-[var(--s-failed-text)] transition-colors"
              >
                <FiX size={12} />
              </button>
            </div>
          ))}

          {selected.length < MAX_MODELS ? (
            <div className="relative">
              <button
                type="button"
                disabled={!dataset}
                onClick={() => setPicker(picker === 'add' ? null : 'add')}
                className="inline-flex items-center gap-1.5 rounded-full border border-dashed border-border-strong bg-surface px-3 py-1.5 text-xs font-semibold text-ink-muted hover:bg-surface-subtle hover:text-ink disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
              >
                <FiPlus size={13} />
                Add model
                <FiChevronDown size={12} />
              </button>
              {picker === 'add' ? (
                <ModelDropdown
                  models={datasetModels}
                  disabledIds={selectedIds}
                  onPick={onPickModel}
                  onClose={() => setPicker(null)}
                />
              ) : null}
            </div>
          ) : null}
        </div>

        {/* Swap dropdown anchored to the targeted slot. */}
        {typeof picker === 'number' ? (
          <div className="relative">
            <ModelDropdown
              models={datasetModels}
              disabledIds={new Set(selected.filter((_, i) => i !== picker).map((m) => m.id))}
              onPick={onPickModel}
              onClose={() => setPicker(null)}
            />
          </div>
        ) : null}

        <p className="mt-3 text-[11px] text-ink-faint">
          Up to {MAX_MODELS} models · {selected.length} selected.
        </p>
      </Card>

      {/* Step 4 — the comparison grid. */}
      {selected.length > 0 && slideId ? (
        <div className={compareGridClass(selected.length)}>
          {selected.map((m, i) => (
            <CompareModelPanel
              key={`${m.id}-${i}`}
              model={m}
              slideId={slideId}
              syncEnabled={syncEnabled}
              syncTransform={syncTransform}
              onSyncTransformChange={setSyncTransform}
            />
          ))}
        </div>
      ) : (
        <Card className="p-10 text-center">
          <p className="text-sm text-ink-faint">
            {selected.length === 0
              ? 'Add at least one model to start comparing.'
              : 'Pick a slide above to render the selected models.'}
          </p>
        </Card>
      )}
    </div>
  );
}

function SlideTile({
  slide,
  active,
  onSelect,
}: {
  slide: DatasetSlide;
  active: boolean;
  onSelect: () => void;
}) {
  const [imgOk, setImgOk] = useState(true);
  const disabled = !slide.has_wsi;
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onSelect}
      title={disabled ? `${slide.slide_id} — WSI not found on disk` : slide.slide_id}
      className={`group flex flex-col overflow-hidden rounded-lg border text-left transition-all ${
        active
          ? 'border-accent ring-2 ring-accent/40'
          : 'border-border hover:border-accent/40 hover:shadow-card'
      } ${disabled ? 'cursor-not-allowed opacity-40' : ''}`}
    >
      <div className="aspect-square w-full bg-surface-subtle">
        {slide.thumbnail_url && imgOk ? (
          <img
            src={slide.thumbnail_url}
            alt={slide.slide_id}
            loading="lazy"
            onError={() => setImgOk(false)}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="grid h-full w-full place-items-center text-ink-faint">
            <FiImage size={22} />
          </div>
        )}
      </div>
      <span className="truncate px-2 py-1.5 font-mono text-[11px] text-ink-muted" title={slide.slide_id}>
        {slide.slide_id}
      </span>
    </button>
  );
}

function ModelDropdown({
  models,
  disabledIds,
  onPick,
  onClose,
}: {
  models: ModelInfo[];
  disabledIds: Set<string>;
  onPick: (m: ModelInfo) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  return (
    <div
      ref={ref}
      className="absolute left-0 z-20 mt-2 max-h-80 w-72 overflow-auto rounded-lg border border-border bg-surface p-1.5 shadow-modal"
    >
      {models.length === 0 ? (
        <p className="px-3 py-4 text-center text-xs text-ink-faint">No models on this dataset.</p>
      ) : (
        <ul className="space-y-0.5">
          {models.map((m) => {
            const taken = disabledIds.has(m.id);
            return (
              <li key={m.id}>
                <button
                  type="button"
                  disabled={taken}
                  onClick={() => onPick(m)}
                  className="flex w-full items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-xs hover:bg-surface-subtle disabled:cursor-not-allowed disabled:opacity-40 transition-colors"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-semibold text-ink">
                      {m.display_name || m.base_name}
                    </span>
                    <span className="block truncate font-mono text-[10px] text-ink-faint">
                      n_proto={m.n_proto} · {m.mode} · {new Date(m.created_at).toLocaleDateString()}
                    </span>
                  </span>
                  {taken ? <Chip>selected</Chip> : null}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function ErrorNote({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-md border border-[var(--s-failed-border)] bg-[var(--s-failed-bg)] px-3 py-2 text-xs text-[var(--s-failed-text)]">
      {children}
    </p>
  );
}
