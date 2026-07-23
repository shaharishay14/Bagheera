import { SectionHeader } from './ui';
import { resolveVizUrl, vizPlaceholderUrl } from '../lib/api';

/**
 * Per-slide prototype-similarity violin (Section B, scoped to one slide). Used
 * on the Compare page where every field comes from a slide's render-slide
 * manifest rather than the model's global viz artifacts. Degrades to a labeled
 * placeholder via `resolveVizUrl` while the render is pending / partial.
 */
export default function ViolinPanel({ violin }: { violin?: string }) {
  return (
    <section className="space-y-3">
      <SectionHeader title="Section B · Per-slide prototype similarity" />
      <figure>
        <img
          src={resolveVizUrl(violin, () =>
            vizPlaceholderUrl('mixture', { label: 'Violin', width: 640, height: 260 }),
          )}
          alt="Per-prototype cosine-similarity distribution for this slide"
          className="w-full rounded-lg border border-border bg-surface-subtle"
        />
        <figcaption className="mt-1.5 text-center text-[11px] text-ink-faint">
          Per-slide prototype similarity (violin)
        </figcaption>
      </figure>
    </section>
  );
}
