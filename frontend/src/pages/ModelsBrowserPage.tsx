import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ApiError,
  listModelGroups,
  type ModelGroupListItem,
} from '../lib/api';
import { Chip, StatusPill } from '../components/ui';

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
    return () => { cancelled = true; };
  }, [q, datasetFilter, favoritesOnly, sort]);

  const datasets = useMemo(() => {
    const s = new Set<string>();
    for (const g of groups) s.add(g.dataset_name);
    return Array.from(s).sort();
  }, [groups]);

  const inputCls =
    'mt-1 block w-full rounded-md border border-border-strong bg-surface px-3 py-1.5 text-sm shadow-inner-sm focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent';

  return (
    <div>
      <div className="mb-6 flex items-baseline justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-ink">Models</h2>
          <p className="text-sm text-ink-muted">
            One card per training run. Click into a card to inspect each fold model.
          </p>
        </div>
        <Link
          to="/training/panther"
          className="rounded-full bg-grad-accent px-4 py-1.5 text-sm font-semibold text-white shadow-glow hover:shadow-glow-lg hover:brightness-105 transition-all duration-150"
        >
          Train new
        </Link>
      </div>

      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-lg border border-border bg-surface p-3 shadow-card">
        <div className="flex-1 min-w-[220px]">
          <label className="block text-[11px] font-semibold uppercase tracking-widest text-ink-faint">
            Search
          </label>
          <input
            type="search"
            placeholder="Filter by name…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className={inputCls}
          />
        </div>
        <div className="min-w-[180px]">
          <label className="block text-[11px] font-semibold uppercase tracking-widest text-ink-faint">
            Dataset
          </label>
          <select
            value={datasetFilter}
            onChange={(e) => setDatasetFilter(e.target.value)}
            className={inputCls}
          >
            <option value="">All datasets</option>
            {datasets.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </div>
        <div className="min-w-[160px]">
          <label className="block text-[11px] font-semibold uppercase tracking-widest text-ink-faint">
            Sort
          </label>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as Sort)}
            className={inputCls}
          >
            <option value="created_desc">Newest first</option>
            <option value="created_asc">Oldest first</option>
            <option value="name">Name</option>
          </select>
        </div>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            checked={favoritesOnly}
            onChange={(e) => setFavoritesOnly(e.target.checked)}
            className="h-4 w-4 rounded border-border-strong accent-accent"
          />
          Favorites only
        </label>
      </div>

      {error ? (
        <div className="mb-4 rounded-md border border-[var(--s-failed-border)] bg-[var(--s-failed-bg)] px-4 py-3 text-sm text-[var(--s-failed-text)]">
          {error}
        </div>
      ) : null}

      {loading ? (
        <p className="text-sm text-ink-muted">Loading…</p>
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
    <div className="rounded-lg border border-dashed border-border-strong bg-surface p-10 text-center">
      <p className="text-sm text-ink-muted">No model groups yet.</p>
      <Link
        to="/training/panther"
        className="mt-3 inline-block rounded-full bg-grad-accent px-4 py-1.5 text-sm font-semibold text-white shadow-glow hover:shadow-glow-lg hover:brightness-105 transition-all duration-150"
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
      className="group flex flex-col gap-2 rounded-lg border border-border bg-surface p-4 shadow-card transition-all duration-150 hover:border-border-strong hover:shadow-card-hover"
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="line-clamp-2 text-base font-semibold text-ink group-hover:text-accent">
          {group.display_name}
        </h3>
        <GroupStatusPill summary={s} />
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Chip mono>{group.dataset_name}</Chip>
        <span className="text-ink-muted">
          K={group.k} · n_proto={group.n_proto} · {group.mode}
        </span>
      </div>
      <div className="mt-1 flex items-center justify-between text-xs text-ink-faint">
        <span>{new Date(group.created_at).toLocaleString()}</span>
        {s.favorited > 0 ? (
          <span className="inline-flex items-center gap-1 text-[var(--s-warn-text)]">
            <StarIcon filled /> {s.favorited}/{s.total} favorited
          </span>
        ) : null}
      </div>
    </Link>
  );
}

function GroupStatusPill({ summary }: { summary: ModelGroupListItem['summary'] }) {
  const { total, ready, failed, running } = summary;
  let status: string;
  let label: string;

  if (running > 0) {
    status = 'running';
    label = `training… (${ready}/${total})`;
  } else if (failed > 0 && ready === 0) {
    status = 'failed';
    label = `${failed}/${total} failed`;
  } else if (failed > 0) {
    status = 'canceled'; // amber — mixed
    label = `${ready}/${total} ready · ${failed} failed`;
  } else if (ready === total && total > 0) {
    status = 'ready';
    label = `${ready}/${total} ready`;
  } else {
    status = 'queued';
    label = `${ready}/${total} ready`;
  }
  return <StatusPill status={status} label={label} />;
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
