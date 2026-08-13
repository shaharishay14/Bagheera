import { useEffect, useState } from 'react';
import { SectionHeader, inputCls } from './ui';
import {
  ApiError,
  deletePrototypeLabel,
  listPrototypeLabels,
  resolveVizUrl,
  upsertPrototypeLabel,
  vizPlaceholderUrl,
  type ModelInfo,
  type SectionD,
} from '../lib/api';

type SaveState = 'idle' | 'saving' | 'saved' | 'error';

/**
 * Section D of the per-fold Analysis view — the PANTHER-paper prototype
 * "dictionary". A horizontally-scrollable row of per-prototype columns; each is
 * headed `C{index+1}` in the prototype's color (matching the assignment map),
 * stacks that prototype's `per_proto` example patches, and carries a label box
 * below wired to the prototype-label endpoints.
 *
 * Labels are loaded once for the whole model (a single `listPrototypeLabels`),
 * then each box upserts on blur — or deletes when cleared.
 */
export default function SectionDPanel({ model }: { model: ModelInfo }) {
  const section: SectionD | undefined = model.viz_artifacts?.section_d;

  // Per-prototype label state, keyed by prototype index.
  const [labels, setLabels] = useState<Record<number, string>>({});
  const [labelIds, setLabelIds] = useState<Record<number, string>>({});
  const [saveStates, setSaveStates] = useState<Record<number, SaveState>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    setLabels({});
    setLabelIds({});
    setSaveStates({});
    (async () => {
      try {
        const rows = await listPrototypeLabels(model.id);
        if (cancelled) return;
        const nextLabels: Record<number, string> = {};
        const nextIds: Record<number, string> = {};
        for (const r of rows) {
          nextLabels[r.prototype_index] = r.label;
          nextIds[r.prototype_index] = r.id;
        }
        setLabels(nextLabels);
        setLabelIds(nextIds);
      } catch (err) {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Failed to load labels.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [model.id]);

  const setSaveState = (index: number, state: SaveState) =>
    setSaveStates((prev) => ({ ...prev, [index]: state }));

  const onSave = async (index: number) => {
    const value = (labels[index] ?? '').trim();
    const existingId = labelIds[index];
    setSaveState(index, 'saving');
    try {
      if (!value) {
        // Clearing the box removes the label entirely.
        if (existingId) {
          await deletePrototypeLabel(existingId);
          setLabelIds((prev) => {
            const next = { ...prev };
            delete next[index];
            return next;
          });
        }
      } else {
        const saved = await upsertPrototypeLabel({
          model_id: model.id,
          prototype_index: index,
          label: value,
        });
        setLabelIds((prev) => ({ ...prev, [index]: saved.id }));
      }
      setSaveState(index, 'saved');
      setTimeout(() => setSaveState(index, 'idle'), 1200);
    } catch {
      setSaveState(index, 'error');
    }
  };

  const prototypes = section?.prototypes ?? [];
  const perProto = section?.per_proto ?? 0;

  return (
    <section>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <SectionHeader title="Section D · Prototype dictionary" />
        {prototypes.length > 0 ? (
          <span className="font-mono text-[11px] text-ink-faint">
            {prototypes.length} prototypes · {perProto}/proto
          </span>
        ) : null}
      </div>

      {loadError ? (
        <p className="mt-2 rounded-md border border-[var(--s-failed-border)] bg-[var(--s-failed-bg)] px-3 py-2 text-xs text-[var(--s-failed-text)]">
          {loadError}
        </p>
      ) : null}

      {prototypes.length === 0 ? (
        <p className="mt-2 text-[11px] text-ink-faint">
          The prototype dictionary has not been rendered yet — it appears once the viz job completes.
        </p>
      ) : (
        <div className="mt-3 overflow-x-auto pb-2">
          <div className="flex gap-3">
            {prototypes.map((proto) => (
              <PrototypeColumn
                key={proto.index}
                index={proto.index}
                color={proto.color}
                patches={proto.patches}
                perProto={perProto}
                label={labels[proto.index] ?? ''}
                saveState={saveStates[proto.index] ?? 'idle'}
                disabled={loading}
                onChange={(v) => setLabels((prev) => ({ ...prev, [proto.index]: v }))}
                onBlur={() => onSave(proto.index)}
              />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function PrototypeColumn({
  index,
  color,
  patches,
  perProto,
  label,
  saveState,
  disabled,
  onChange,
  onBlur,
}: {
  index: number;
  color: string;
  patches: string[];
  perProto: number;
  label: string;
  saveState: SaveState;
  disabled: boolean;
  onChange: (value: string) => void;
  onBlur: () => void;
}) {
  // Render exactly `perProto` slots so every column lines up; missing patches
  // degrade to labeled placeholders.
  const slots = Array.from({ length: Math.max(perProto, 1) }, (_, i) => patches[i] ?? null);
  const textColor = readableTextColor(color);

  return (
    <div
      className="flex w-40 shrink-0 flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-card"
      style={{ borderTopColor: color, borderTopWidth: 3 }}
    >
      <div
        className="flex items-center justify-center px-2 py-1.5 text-xs font-bold tracking-wide"
        style={{ backgroundColor: color, color: textColor }}
        title={`Prototype C${index + 1}`}
      >
        C{index + 1}
      </div>

      <div className="flex flex-col gap-1.5 p-1.5">
        {slots.map((path, i) => (
          <img
            key={i}
            src={resolveVizUrl(path, () =>
              vizPlaceholderUrl('patches', { label: `C${index + 1}`, width: 144, height: 144 }),
            )}
            alt={`Prototype C${index + 1} patch ${i + 1}`}
            className="aspect-square w-full rounded border border-border bg-surface-subtle object-cover"
          />
        ))}
      </div>

      <div className="mt-auto border-t border-border bg-surface-subtle p-1.5">
        <div className="mb-1 flex items-center justify-between text-[10px] font-semibold uppercase tracking-widest text-ink-faint">
          <span>Label</span>
          {saveState === 'saving' ? (
            <span className="normal-case tracking-normal text-ink-faint">saving…</span>
          ) : saveState === 'saved' ? (
            <span className="normal-case tracking-normal text-[var(--s-success-text)]">saved ✓</span>
          ) : saveState === 'error' ? (
            <span className="normal-case tracking-normal text-[var(--s-failed-text)]">error</span>
          ) : null}
        </div>
        <input
          type="text"
          value={label}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          onBlur={onBlur}
          placeholder="e.g., fat"
          className={inputCls(saveState === 'error') + ' px-2 py-1 text-xs'}
        />
      </div>
    </div>
  );
}

/** Pick black/white text for a `#rrggbb` background using relative luminance. */
function readableTextColor(hex: string): string {
  const m = /^#?([0-9a-fA-F]{6})$/.exec(hex.trim());
  if (!m) return '#ffffff';
  const n = parseInt(m[1], 16);
  const r = (n >> 16) & 0xff;
  const g = (n >> 8) & 0xff;
  const b = n & 0xff;
  // Perceived luminance (sRGB-ish). Bright backgrounds get dark text.
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.6 ? '#1a1a1a' : '#ffffff';
}
