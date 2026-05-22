import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ApiError, listModels, type ModelInfo } from '../lib/api';

interface Group {
  group_id: string;
  base_name: string;
  dataset_name: string;
  split_name: string;
  created_at: string;
  k: number;
  models: ModelInfo[];
  ready: number;
  failed: number;
}

function groupModels(models: ModelInfo[]): Group[] {
  const byId = new Map<string, ModelInfo[]>();
  for (const m of models) {
    const arr = byId.get(m.group_id) ?? [];
    arr.push(m);
    byId.set(m.group_id, arr);
  }
  const groups: Group[] = [];
  for (const [group_id, arr] of byId) {
    arr.sort((a, b) => a.fold_index - b.fold_index);
    const first = arr[0];
    groups.push({
      group_id,
      base_name: first.base_name,
      dataset_name: first.dataset_name,
      split_name: first.split_name,
      created_at: first.created_at,
      k: first.fold_k,
      models: arr,
      ready: arr.filter((m) => m.status === 'ready').length,
      failed: arr.filter((m) => m.status === 'failed').length,
    });
  }
  groups.sort((a, b) => b.created_at.localeCompare(a.created_at));
  return groups;
}

export default function ModelsBrowserPage() {
  const [params, setParams] = useSearchParams();
  const groupFilter = params.get('group') ?? '';
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(groupFilter ? [groupFilter] : []));

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const res = await listModels(groupFilter ? { groupId: groupFilter } : undefined);
        if (!cancelled) setModels(res);
      } catch (err) {
        if (!cancelled) {
          const msg = err instanceof ApiError ? err.message : 'Failed to load models.';
          setError(msg);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [groupFilter]);

  const groups = useMemo(() => groupModels(models), [models]);

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">Models</h2>
          <p className="text-sm text-slate-500">
            Each PANTHER form submission produces K models grouped by run ID. Click a row to expand.
          </p>
        </div>
        {groupFilter ? (
          <button
            type="button"
            onClick={() => setParams({})}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-100"
          >
            Clear group filter
          </button>
        ) : null}
      </div>

      {groupFilter ? (
        <div className="mb-4 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
          Showing only group <code className="font-mono">{groupFilter}</code>.
        </div>
      ) : null}

      {loading ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : error ? (
        <p className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{error}</p>
      ) : groups.length === 0 ? (
        <p className="rounded-md border border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-500">
          No trained models yet.{' '}
          <Link to="/training/panther" className="underline hover:no-underline">
            Start a PANTHER run →
          </Link>
        </p>
      ) : (
        <ul className="space-y-3">
          {groups.map((g) => {
            const open = expanded.has(g.group_id);
            return (
              <li key={g.group_id} className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
                <button
                  type="button"
                  onClick={() => toggle(g.group_id)}
                  className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left hover:bg-slate-50"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 text-sm">
                      <span className="font-mono font-semibold">{g.base_name}</span>
                      <span className="text-slate-400">·</span>
                      <span className="text-slate-600">K={g.k}</span>
                      <span className="text-slate-400">·</span>
                      <span className="text-emerald-700">{g.ready} ready</span>
                      {g.failed > 0 ? (
                        <>
                          <span className="text-slate-400">·</span>
                          <span className="text-rose-700">{g.failed} failed</span>
                        </>
                      ) : null}
                    </div>
                    <div className="mt-1 flex gap-3 text-xs text-slate-500">
                      <span>dataset {g.dataset_name}</span>
                      <span>split {g.split_name}</span>
                      <span>{new Date(g.created_at).toLocaleString()}</span>
                    </div>
                  </div>
                  <span className="text-slate-400">{open ? '▾' : '▸'}</span>
                </button>
                {open ? (
                  <div className="border-t border-slate-200 bg-slate-50">
                    <table className="w-full text-xs">
                      <thead className="text-slate-500">
                        <tr>
                          <th className="px-4 py-2 text-left font-medium">Fold</th>
                          <th className="px-4 py-2 text-left font-medium">Model name</th>
                          <th className="px-4 py-2 text-left font-medium">Status</th>
                          <th className="px-4 py-2 text-left font-medium">Prototypes</th>
                        </tr>
                      </thead>
                      <tbody>
                        {g.models.map((m) => (
                          <tr key={m.id} className="border-t border-slate-200">
                            <td className="px-4 py-2 font-mono">k={m.fold_index}</td>
                            <td className="px-4 py-2 font-mono break-all">{m.model_name}</td>
                            <td className="px-4 py-2">
                              <span
                                className={`inline-block rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${
                                  m.status === 'ready'
                                    ? 'bg-emerald-200 text-emerald-900'
                                    : m.status === 'failed'
                                      ? 'bg-rose-200 text-rose-900'
                                      : 'bg-slate-200 text-slate-700'
                                }`}
                              >
                                {m.status}
                              </span>
                            </td>
                            <td className="px-4 py-2 text-slate-600">
                              {m.prototype_files.length > 0
                                ? `${m.prototype_files.length} file(s)`
                                : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
