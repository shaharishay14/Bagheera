import { useEffect, useState } from 'react';
import { FiCrosshair, FiRefreshCw } from 'react-icons/fi';
import ZoomPanImage, { type Transform } from './ZoomPanImage';
import { SectionHeader } from './ui';
import {
  ApiError,
  repickRoi,
  resolveVizUrl,
  selectRoi,
  vizPlaceholderUrl,
  type ModelInfo,
  type SectionA,
  type SelectRoiResult,
} from '../lib/api';

/** Map an ROI-action error to the same inline copy used across repick/select. */
function roiErrorMessage(err: unknown, verb: 'repick' | 'select'): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return `Render Section A first, then you can ${verb} an ROI.`;
    if (err.status === 422) return 'No tissue window available to pick an ROI from.';
    return err.message;
  }
  return verb === 'repick' ? 'Failed to repick ROI.' : 'Failed to select an ROI.';
}

/**
 * Section A of the per-fold Analysis view — mirrors the PANTHER paper's
 * per-slide figure panel for ONE representative slide:
 *
 *   ┌ Whole Slide Image ─┐ ┌ Prototypical Assignment Map ─┐
 *   └────────────────────┘ └──────────────────────────────┘
 *   ┌ ROIs with Prototype Distribution ───────────────────┐
 *   │  [ROI H&E]  [ROI prototypes]                          │
 *   │  [────────── π_c bar chart ──────────]   [Repick ROI] │
 *   └──────────────────────────────────────────────────────┘
 *
 * Every image degrades to a labeled placeholder via `resolveVizUrl` so the
 * layout stays coherent during partial-success / pre-render states.
 */
export default function SectionAPanel({
  model,
  slideId,
  section: sectionOverride,
  imageTransform,
  onImageTransformChange,
}: {
  model: ModelInfo;
  slideId?: string;
  /**
   * Explicit Section-A source. When set (Compare page, an arbitrary slide's
   * render-slide manifest) it seeds the panel instead of `model.viz_artifacts`.
   * Its Repick/Select still operate on `slideId`.
   */
  section?: SectionA;
  /** Controlled pan/zoom for the row-1 images — used to sync across panels. */
  imageTransform?: Transform;
  onImageTransformChange?: (t: Transform) => void;
}) {
  // Local mirror so a repick swaps images without a full group reload. Reseed
  // whenever the model (or its rendered Section A) changes underneath us.
  const [section, setSection] = useState<SectionA | undefined>(
    sectionOverride ?? model.viz_artifacts?.section_a,
  );
  const [repicking, setRepicking] = useState(false);
  // One-shot "select" mode: armed → next click on the assignment map picks the ROI.
  const [armed, setArmed] = useState(false);
  const [selecting, setSelecting] = useState(false);
  // Shared inline error region for both repick and select (one action at a time).
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    setSection(sectionOverride ?? model.viz_artifacts?.section_a);
    setActionError(null);
    setArmed(false);
  }, [model.id, model.viz_artifacts?.section_a, sectionOverride]);

  const rendered = Boolean(section);
  const busy = repicking || selecting;

  const onRepick = async () => {
    setArmed(false);
    setRepicking(true);
    setActionError(null);
    try {
      const updated = await repickRoi(model.id);
      setSection(updated.viz_artifacts?.section_a);
    } catch (err) {
      setActionError(roiErrorMessage(err, 'repick'));
    } finally {
      setRepicking(false);
    }
  };

  // Fired when the user clicks a point on the assignment map while armed.
  // fx,fy ∈ [0,1] over the natural image. One-shot: disarm immediately.
  const onSelectPoint = async (fx: number, fy: number) => {
    setArmed(false);
    setSelecting(true);
    setActionError(null);
    try {
      const res = await selectRoi(model.id, { slide_id: slideId ?? null, fx, fy });
      if (slideId) {
        // Compare slide → per-slide artifacts; swap just the ROI-relevant fields.
        const { artifacts } = res as SelectRoiResult;
        setSection((prev) =>
          prev
            ? {
                ...prev,
                roi_raw: artifacts.roi_raw,
                roi_colored: artifacts.roi_colored,
                roi_bbox: artifacts.roi_bbox,
                roi_index: artifacts.roi_index,
              }
            : prev,
        );
      } else {
        // Preview slide → updated ModelInfo (mirrors onRepick).
        const updated = res as ModelInfo;
        setSection(updated.viz_artifacts?.section_a);
      }
    } catch (err) {
      setActionError(roiErrorMessage(err, 'select'));
    } finally {
      setSelecting(false);
    }
  };

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <SectionHeader title="Section A · Per-slide prototype analysis" />
        {section?.slide_id ? (
          <span className="font-mono text-[11px] text-ink-muted">
            slide <span className="text-ink">{section.slide_id}</span>
          </span>
        ) : null}
      </div>

      {!rendered ? (
        <p className="text-[11px] text-ink-faint">
          Section A has not been rendered yet — placeholders shown until the viz job completes.
        </p>
      ) : null}

      {/* Row 1 — whole slide + assignment map, side by side. */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Figure caption="Whole Slide Image">
          <ZoomPanImage
            src={resolveVizUrl(section?.thumbnail, () =>
              vizPlaceholderUrl('heatmap', { label: 'Whole slide', width: 480, height: 360 }),
            )}
            alt="Whole-slide H&E thumbnail"
            className="aspect-[4/3] rounded-lg border border-border"
            transform={imageTransform}
            onTransformChange={onImageTransformChange}
          />
        </Figure>
        <Figure caption="Prototypical Assignment Map">
          <ZoomPanImage
            src={resolveVizUrl(section?.assignment_map, () =>
              vizPlaceholderUrl('heatmap', { label: 'Assignment map', width: 480, height: 360 }),
            )}
            alt="Hi-res prototype assignment overlay"
            className={`aspect-[4/3] rounded-lg border ${armed ? 'border-accent ring-2 ring-accent/40' : 'border-border'}`}
            armed={armed}
            onImageClick={onSelectPoint}
            transform={imageTransform}
            onTransformChange={onImageTransformChange}
          />
        </Figure>
      </div>

      {/* Row 2 — ROI panel with the π_c distribution + repick control. */}
      <div className="rounded-lg border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-baseline gap-2">
            <h5 className="text-xs font-semibold text-ink">ROIs with Prototype Distribution</h5>
            {section?.roi_index != null ? (
              <span className="font-mono text-[10px] text-ink-faint">window #{section.roi_index}</span>
            ) : null}
            {section?.slide_id ? (
              <span className="font-mono text-[10px] text-ink-faint">
                · from <span className="text-ink-muted">{section.slide_id}</span>
              </span>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                setActionError(null);
                setArmed((a) => !a);
              }}
              disabled={busy || !rendered}
              aria-pressed={armed}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                armed
                  ? 'border-accent bg-accent text-white hover:bg-accent-dark'
                  : 'border-border-strong bg-surface text-ink hover:bg-surface-subtle'
              }`}
              title="Click a point on the assignment map to place the ROI there"
            >
              <FiCrosshair size={12} className={selecting ? 'animate-spin' : ''} />
              {selecting ? 'Selecting…' : armed ? 'Cancel select' : 'Select'}
            </button>
            <button
              type="button"
              onClick={onRepick}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-full border border-border-strong bg-surface px-3 py-1.5 text-xs font-semibold text-ink hover:bg-surface-subtle disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
              title="Auto-pick a different region of interest"
            >
              <FiRefreshCw size={12} className={repicking ? 'animate-spin' : ''} />
              {repicking ? 'Repicking…' : 'Repick ROI'}
            </button>
          </div>
        </div>

        {armed ? (
          <p className="mt-2 rounded-md border border-accent/40 bg-accent-muted px-2.5 py-1.5 text-[11px] text-accent-dark">
            Click a point on the assignment map to place the ROI there.
          </p>
        ) : null}

        {actionError ? (
          <p className="mt-2 rounded-md border border-[var(--s-warn-border)] bg-[var(--s-warn-bg)] px-2.5 py-1.5 text-[11px] text-[var(--s-warn-text)]">
            {actionError}
          </p>
        ) : null}

        {section?.roi_bbox ? (
          <p className="mt-2 font-mono text-[10px] text-ink-faint">
            bbox [x {section.roi_bbox[0]}, y {section.roi_bbox[1]}, w {section.roi_bbox[2]}, h {section.roi_bbox[3]}]
          </p>
        ) : null}

        <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Figure caption="ROI · H&E">
            <ZoomPanImage
              src={resolveVizUrl(section?.roi_raw, () =>
                vizPlaceholderUrl('patches', { label: 'ROI (H&E)', width: 320, height: 320 }),
              )}
              alt="Raw H&E of the auto-picked ROI"
              className="aspect-square rounded-lg border border-border"
            />
          </Figure>
          <Figure caption="ROI · Prototype tiling">
            <ZoomPanImage
              src={resolveVizUrl(section?.roi_colored, () =>
                vizPlaceholderUrl('patches', { label: 'ROI (prototypes)', width: 320, height: 320 }),
              )}
              alt="ROI tiled as prototype-colored 256px patches"
              className="aspect-square rounded-lg border border-border"
            />
          </Figure>
        </div>

        {/* π_c distribution chart sits below the ROI pair (plain image). */}
        <figure className="mt-4">
          <img
            src={resolveVizUrl(section?.pi_c, () =>
              vizPlaceholderUrl('mixture', { label: 'π_c distribution', width: 640, height: 220 }),
            )}
            alt="GMM π_c bar chart, bars colored per prototype"
            className="w-full rounded-lg border border-border bg-surface-subtle"
          />
          <figcaption className="mt-1.5 text-center text-[11px] text-ink-faint">
            Prototype mixture weights (π_c)
          </figcaption>
        </figure>
      </div>
    </section>
  );
}

function Figure({ caption, children }: { caption: string; children: React.ReactNode }) {
  return (
    <figure>
      {children}
      <figcaption className="mt-1.5 text-center text-[11px] text-ink-faint">{caption}</figcaption>
    </figure>
  );
}
