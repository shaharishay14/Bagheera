import { useEffect, useState } from 'react';
import {
  ApiError,
  listPrototypeLabels,
  upsertPrototypeLabel,
} from '../lib/api';
import { inputCls } from './ui';

interface Props {
  modelId: string;
  nProto: number;
}

type SaveState = 'idle' | 'saving' | 'saved' | 'error';

export default function PrototypeLabels({ modelId, nProto }: Props) {
  const [values, setValues] = useState<string[]>(() => Array(nProto).fill(''));
  const [savingStates, setSavingStates] = useState<SaveState[]>(() => Array(nProto).fill('idle'));
  const [errors, setErrors] = useState<(string | null)[]>(() => Array(nProto).fill(null));
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    setValues(Array(nProto).fill(''));
    setSavingStates(Array(nProto).fill('idle'));
    setErrors(Array(nProto).fill(null));
    (async () => {
      try {
        const rows = await listPrototypeLabels(modelId);
        if (cancelled) return;
        const next = Array(nProto).fill('');
        for (const r of rows) {
          if (r.prototype_index >= 0 && r.prototype_index < nProto) {
            next[r.prototype_index] = r.label;
          }
        }
        setValues(next);
      } catch (err) {
        if (!cancelled) {
          const msg = err instanceof ApiError ? err.message : 'Failed to load labels.';
          setLoadError(msg);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [modelId, nProto]);

  const onBlur = async (index: number) => {
    const value = values[index];
    setSavingStates((prev) => withReplaced(prev, index, 'saving'));
    setErrors((prev) => withReplaced(prev, index, null));
    try {
      await upsertPrototypeLabel({
        model_id: modelId,
        prototype_index: index,
        label: value,
      });
      setSavingStates((prev) => withReplaced(prev, index, 'saved'));
      // Fade the "saved" indicator after a moment.
      setTimeout(() => {
        setSavingStates((prev) => withReplaced(prev, index, 'idle'));
      }, 1200);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Failed to save.';
      setErrors((prev) => withReplaced(prev, index, msg));
      setSavingStates((prev) => withReplaced(prev, index, 'error'));
    }
  };

  if (loadError) {
    return (
      <p className="rounded-md border border-[var(--s-failed-border)] bg-[var(--s-failed-bg)] px-3 py-2 text-xs text-[var(--s-failed-text)]">
        {loadError}
      </p>
    );
  }
  if (loading) {
    return <p className="text-xs text-ink-muted">Loading labels…</p>;
  }
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {values.map((v, i) => {
        const state = savingStates[i];
        const err = errors[i];
        return (
          <label key={i} className="block">
            <div className="mb-1 flex items-center justify-between text-[11px] font-semibold uppercase tracking-widest text-ink-faint">
              <span>Prototype {i}</span>
              {state === 'saving' ? (
                <span className="text-ink-faint normal-case tracking-normal">saving…</span>
              ) : state === 'saved' ? (
                <span className="text-[var(--s-success-text)] normal-case tracking-normal">saved ✓</span>
              ) : state === 'error' ? (
                <span className="text-[var(--s-failed-text)] normal-case tracking-normal">error</span>
              ) : null}
            </div>
            <input
              type="text"
              value={v}
              onChange={(e) => setValues((prev) => withReplaced(prev, i, e.target.value))}
              onBlur={() => onBlur(i)}
              placeholder="e.g., fat, necrosis"
              className={inputCls(state === 'error') + ' font-mono text-xs'}
            />
            {err ? <p className="mt-1 text-[11px] text-[var(--s-failed-text)]">{err}</p> : null}
          </label>
        );
      })}
    </div>
  );
}

function withReplaced<T>(arr: T[], index: number, value: T): T[] {
  const next = arr.slice();
  next[index] = value;
  return next;
}
