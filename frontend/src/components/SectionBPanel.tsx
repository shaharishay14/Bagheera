import ZoomPanImage from './ZoomPanImage';
import { SectionHeader } from './ui';
import {
  resolveVizUrl,
  vizPlaceholderUrl,
  type ModelInfo,
} from '../lib/api';

/**
 * Section B of the per-fold Analysis view — validation-consistency charts that
 * show how the trained prototypes generalize to the fold's held-out slides:
 *
 *   ┌ Train-vs-val π_c grouped bars ─┐ ┌ Per-prototype val cosine violins ─┐
 *   └────────────────────────────────┘ └───────────────────────────────────┘
 *
 * `section_b` is **absent when the fold has no validation slides** — in that
 * case render a muted note rather than a broken image. Individual images may
 * also be absent (partial success) — each degrades to a labeled placeholder via
 * `resolveVizUrl`. The violin can get tall/wide with many prototypes, so it
 * lives in a `ZoomPanImage`; the usage bars get the same treatment for parity.
 */
export default function SectionBPanel({ model }: { model: ModelInfo }) {
  const section = model.viz_artifacts?.section_b;

  if (!section) {
    return (
      <section className="space-y-2">
        <SectionHeader title="Section B · Validation consistency" />
        <p className="text-xs text-ink-faint">No validation slides for this fold.</p>
      </section>
    );
  }

  const { n_val_slides, n_train_slides } = section;
  const counts: string[] = [];
  if (n_val_slides != null) {
    counts.push(`${n_val_slides} validation slide${n_val_slides === 1 ? '' : 's'}`);
  }
  if (n_train_slides != null) {
    counts.push(`${n_train_slides} train slide${n_train_slides === 1 ? '' : 's'} sampled`);
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <SectionHeader title="Section B · Validation consistency" />
        {counts.length > 0 ? (
          <span className="text-[11px] text-ink-muted">{counts.join(' · ')}</span>
        ) : null}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Figure caption="Prototype usage — train vs. validation π_c">
          <ZoomPanImage
            src={resolveVizUrl(section.usage, () =>
              vizPlaceholderUrl('mixture', {
                label: 'Train vs. val π_c',
                width: 480,
                height: 360,
              }),
            )}
            alt="Grouped bar chart comparing per-prototype π_c on training vs. validation slides"
            className="aspect-[4/3] rounded-lg border border-border"
          />
        </Figure>
        <Figure caption="Validation cosine similarity per prototype">
          <ZoomPanImage
            src={resolveVizUrl(section.violin, () =>
              vizPlaceholderUrl('mixture', {
                label: 'Val cosine distribution',
                width: 480,
                height: 360,
              }),
            )}
            alt="Per-prototype violin distribution of validation cosine similarities, with counts"
            className="aspect-[4/3] rounded-lg border border-border"
          />
        </Figure>
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
