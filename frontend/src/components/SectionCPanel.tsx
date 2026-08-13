import ZoomPanImage from './ZoomPanImage';
import { SectionHeader } from './ui';
import {
  resolveVizUrl,
  vizPlaceholderUrl,
  type ModelInfo,
} from '../lib/api';

/**
 * Section C of the per-fold Analysis view — the dataset-wide UMAP pair for one
 * representative slide:
 *
 *   ┌ On-tissue 2D-embedding ─┐ ┌ Abstract UMAP scatter ─┐
 *   └─────────────────────────┘ └────────────────────────┘
 *
 * The on-tissue colormap rewards zooming, so it lives in a `ZoomPanImage`; the
 * abstract scatter is zoomable too for parity. Either image may be absent
 * (partial success) — each degrades to a labeled placeholder via
 * `resolveVizUrl`.
 *
 * Legacy fallback: models rendered before Section C existed only carry a flat
 * `umap_path`. When `section_c` is absent but `umap_path` is present, show that
 * single scatter so older folds don't lose their UMAP.
 */
export default function SectionCPanel({
  model,
  onTissue,
  slideId,
}: {
  model: ModelInfo;
  /**
   * Per-slide on-tissue colormap override (Compare page). The abstract scatter
   * stays dataset-global (`section_c.scatter` / `umap_path`). When absent, the
   * panel behaves exactly as on the model detail page.
   */
  onTissue?: string;
  /** Slide id for the caption when an `onTissue` override is supplied. */
  slideId?: string;
}) {
  const section = model.viz_artifacts?.section_c;
  // An explicit on-tissue override always uses the two-up layout, even if this
  // model has no rendered section_c of its own (arbitrary compare slide).
  const onTissueSrc = onTissue ?? section?.on_tissue;
  const legacyOnly = !section && onTissue === undefined && Boolean(model.umap_path);
  const captionSlide = slideId ?? section?.slide_id;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <SectionHeader title="Section C · Across the dataset" />
        {captionSlide ? (
          <span className="font-mono text-[11px] text-ink-muted">
            slide <span className="text-ink">{captionSlide}</span>
          </span>
        ) : null}
      </div>

      {legacyOnly ? (
        // Older render — only the flat scatter exists. Keep it visible.
        <Figure caption="Dataset UMAP (prototype-colored)">
          <ZoomPanImage
            src={resolveVizUrl(model.umap_path, () =>
              vizPlaceholderUrl('umap', { label: 'UMAP', width: 720, height: 480 }),
            )}
            alt="Dataset-wide abstract UMAP scatter, colored by prototype"
            className="aspect-[3/2] rounded-lg border border-border"
          />
        </Figure>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Figure caption="On-tissue 2D embedding">
            <ZoomPanImage
              src={resolveVizUrl(onTissueSrc, () =>
                vizPlaceholderUrl('heatmap', {
                  label: 'On-tissue embedding',
                  width: 480,
                  height: 480,
                }),
              )}
              alt="Per-slide 2D-embedding colormap painted on the tissue"
              className="aspect-square rounded-lg border border-border"
            />
          </Figure>
          <Figure caption="Abstract UMAP scatter (prototype-colored)">
            <ZoomPanImage
              src={resolveVizUrl(section?.scatter, () =>
                vizPlaceholderUrl('umap', { label: 'UMAP', width: 480, height: 480 }),
              )}
              alt="Dataset-wide abstract UMAP scatter, colored by prototype"
              className="aspect-square rounded-lg border border-border"
            />
          </Figure>
        </div>
      )}
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
