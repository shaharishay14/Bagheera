import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ApiError,
  listModelGroups,
  type ModelGroupListItem,
} from '../lib/api';

type Sort = 'created_desc' | 'created_asc' | 'name';

export default function ModelsBrowserPage() {
  const [searchParams] = useSearchParams();
  const initialQ = searchParams.get('q') ?? '';

  const [groups, setGroups] = useState<ModelGroupListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [q, setQ] = useState(initialQ);
  const [datasetFilter, setDatasetFilter] = useState<string>('');
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [sort, setSort] = useState<Sort>('created_desc');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const res = await listModelGroups({
          favoriteOnly: favoritesOnly,
          datasetName: datasetFilter || undefined,
          q: q || undefined,
          sort,
        });
        if (!cancelled) setGroups(res);
      } catch (err) {
        if (!cancelled) {
          const msg = err instanceof ApiError ? err.message : 'Failed to load model groups.';
          setError(msg);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [q, datasetFilter, favoritesOnly, sort]);

  const datasets = useMemo(() => {
    const s = new Set<string>();
    for (const g of groups) s.add(g.dataset_name);
    return Array.from(s).sort();
  }, [groups]);

  return (
    <div>
      <div className="mb-6 flex items-baseline justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">Models</h2>
          <p className="text-sm text-slate-500">
            One card per training run. Click into a card to inspect each fold model.
          </p>
        </div>
        <Link
          to="/training/panther"
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800"
        >
          Train new
        </Link>
      </div>

      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
        <div className="flex-1 min-w-[220px]">
          <label className="block text-[11px] font-medium uppercase tracking-wide text-slate-500">
            Search
          </label>
          <input
            type="search"
            placeholder="Filter by name…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
          />
        </div>
        <div className="min-w-[180px]">
          <label className="block text-[11px] font-medium uppercase tracking-wide text-slate-500">
            Dataset
          </label>
          <select
            value={datasetFilter}
            onChange={(e) => setDatasetFilter(e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
          >
            <option value="">All datasets</option>
            {datasets.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>
        <div className="min-w-[160px]">
          <label className="block text-[11px] font-medium uppercase tracking-wide text-slate-500">
            Sort
          </label>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as Sort)}
            className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
          >
            <option value="created_desc">Newest first</option>
            <option value="created_asc">Oldest first</option>
            <option value="name">Name</option>
          </select>
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={favoritesOnly}
            onChange={(e) => setFavoritesOnly(e.target.checked)}
            className="h-4 w-4 rounded border-slate-300"
          />
          Favorites only
        </label>
      </div>

      {error ? (
        <div className="mb-4 rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
          {error}
        </div>
      ) : null}

      {loading ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : groups.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {groups.map((g) => (
            <GroupCard key={g.id} group={g} />
          ))}
        </div>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center">
      <p className="text-sm text-slate-600">No model groups yet.</p>
      <Link
        to="/training/panther"
        className="mt-3 inline-block rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800"
      >
        Train a PANTHER model to get started →
      </Link>
    </div>
  );
}

function GroupCard({ group }: { group: ModelGroupListItem }) {
  const s = group.summary;
  return (
    <Link
      to={`/models/${encodeURIComponent(group.id)}`}
      className="group flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition hover:border-slate-400 hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="line-clamp-2 text-base font-semibold text-slate-900 group-hover:text-slate-700">
          {group.display_name}
        </h3>
        <StatusPill summary={s} />
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 font-mono text-slate-700">
          {group.dataset_name}
        </span>
        <span className="text-slate-500">
          K={group.k} · n_proto={group.n_proto} · {group.mode}
        </span>
      </div>
      <div className="mt-1 flex items-center justify-between text-xs text-slate-500">
        <span>{new Date(group.created_at).toLocaleString()}</span>
        {s.favorited > 0 ? (
          <span className="inline-flex items-center gap-1 text-amber-600">
            <StarIcon filled /> {s.favorited}/{s.total} favorited
          </span>
        ) : null}
      </div>
    </Link>
  );
}

function StatusPill({ summary }: { summary: ModelGroupListItem['summary'] }) {
  const { total, ready, failed, running } = summary;
  let tone = 'bg-slate-100 text-slate-700 border-slate-200';
  let label = `${ready}/${total} ready`;
  if (running > 0) {
    tone = 'bg-blue-50 text-blue-800 border-blue-200 animate-pulse';
    label = `training… (${ready}/${total})`;
  } else if (failed > 0 && ready === 0) {
    tone = 'bg-rose-50 text-rose-800 border-rose-200';
    label = `${failed}/${total} failed`;
  } else if (failed > 0) {
    tone = 'bg-amber-50 text-amber-800 border-amber-200';
    label = `${ready}/${total} ready · ${failed} failed`;
  } else if (ready === total && total > 0) {
    tone = 'bg-emerald-50 text-emerald-800 border-emerald-200';
  }
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${tone}`}
    >
      {label}
    </span>
  );
}

function StarIcon({ filled = false }: { filled?: boolean }) {
  return (
    <svg
      width="11"
      height="11"
      viewBox="0 0 24 24"
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    </svg>
  );
}
