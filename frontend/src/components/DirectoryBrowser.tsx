import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ApiError, getRoots, listDirectory, type FsEntry } from '../lib/api';

type Mode = 'dir' | 'file';

interface Props {
  open: boolean;
  initialPath?: string;
  mode?: Mode;
  /** When mode='file', only files whose extension (lowercase, leading dot) matches one of these is shown. */
  extensions?: string[];
  onCancel: () => void;
  onSelect: (path: string) => void;
}

export default function DirectoryBrowser({
  open,
  initialPath,
  mode = 'dir',
  extensions,
  onCancel,
  onSelect,
}: Props) {
  const [roots, setRoots] = useState<string[]>([]);
  const [currentRoot, setCurrentRoot] = useState<string | null>(null);
  const [path, setPath] = useState<string | null>(null);
  const [parent, setParent] = useState<string | null>(null);
  const [entries, setEntries] = useState<FsEntry[]>([]);
  const [isRoot, setIsRoot] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [highlight, setHighlight] = useState(0);

  const previouslyFocused = useRef<HTMLElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const listRef = useRef<HTMLUListElement | null>(null);

  const allowedExts = useMemo(
    () => (extensions ?? []).map((e) => (e.startsWith('.') ? e.toLowerCase() : `.${e.toLowerCase()}`)),
    [extensions]
  );

  const filterEntries = useCallback(
    (raw: FsEntry[]): FsEntry[] => {
      if (mode === 'dir') return raw;
      if (allowedExts.length === 0) return raw;
      return raw.filter((entry) => {
        if (entry.is_dir) return true;
        const idx = entry.name.lastIndexOf('.');
        const ext = idx >= 0 ? entry.name.slice(idx).toLowerCase() : '';
        return allowedExts.includes(ext);
      });
    },
    [mode, allowedExts]
  );

  const navigate = useCallback(
    async (target?: string) => {
      setLoading(true);
      setError(null);
      try {
        const res = await listDirectory({ path: target, dirsOnly: mode === 'dir' });
        setPath(res.path);
        setParent(res.parent);
        setEntries(filterEntries(res.entries));
        setIsRoot(res.is_root);
        setHighlight(0);
      } catch (err) {
        const msg = err instanceof ApiError ? err.message : 'Failed to load directory';
        setError(msg);
      } finally {
        setLoading(false);
      }
    },
    [mode, filterEntries]
  );

  useEffect(() => {
    if (!open) return;
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    let cancelled = false;
    (async () => {
      try {
        const rootRes = await getRoots();
        if (cancelled) return;
        setRoots(rootRes.roots);
        // For file mode, if initialPath points at a file, navigate to its parent dir.
        let seed = initialPath || rootRes.roots[0];
        if (mode === 'file' && initialPath && /\.[^/]+$/.test(initialPath)) {
          const slash = initialPath.lastIndexOf('/');
          if (slash > 0) seed = initialPath.slice(0, slash);
        }
        setCurrentRoot(rootRes.roots.find((r) => seed?.startsWith(r)) ?? rootRes.roots[0] ?? null);
        await navigate(seed);
      } catch (err) {
        const msg = err instanceof ApiError ? err.message : 'Failed to load roots';
        setError(msg);
      }
    })();
    return () => {
      cancelled = true;
      previouslyFocused.current?.focus?.();
    };
  }, [open, initialPath, navigate, mode]);

  useEffect(() => {
    if (!open) return;
    dialogRef.current?.focus();
  }, [open]);

  const breadcrumbs = useMemo(() => {
    if (!path) return [] as { label: string; path: string }[];
    const segments = path.split('/').filter(Boolean);
    const items: { label: string; path: string }[] = [{ label: '/', path: '/' }];
    let acc = '';
    for (const seg of segments) {
      acc += '/' + seg;
      items.push({ label: seg, path: acc });
    }
    return items;
  }, [path]);

  const highlightedEntry = entries[highlight];
  const selectablePath: string | null =
    mode === 'dir'
      ? path
      : highlightedEntry && !highlightedEntry.is_dir
        ? highlightedEntry.path
        : null;

  const confirm = () => {
    if (selectablePath) onSelect(selectablePath);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onCancel();
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      // In file mode, Enter on a directory navigates into it; on a file, confirms.
      if (mode === 'file' && highlightedEntry?.is_dir) {
        void navigate(highlightedEntry.path);
      } else {
        confirm();
      }
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlight((h) => Math.min(entries.length - 1, h + 1));
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlight((h) => Math.max(0, h - 1));
      return;
    }
    if (e.key === 'ArrowRight') {
      e.preventDefault();
      if (highlightedEntry?.is_dir) void navigate(highlightedEntry.path);
    }
    if (e.key === 'ArrowLeft' && !isRoot && parent) {
      e.preventDefault();
      void navigate(parent);
    }
  };

  useEffect(() => {
    const el = listRef.current?.querySelectorAll('li')[highlight] as HTMLElement | undefined;
    el?.scrollIntoView({ block: 'nearest' });
  }, [highlight]);

  if (!open) return null;

  const title = mode === 'file' ? 'Choose a file' : 'Choose a directory';
  const buttonLabel = mode === 'file' ? 'Select this file' : 'Select this folder';

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        className="flex h-[600px] w-[720px] max-w-[95vw] flex-col overflow-hidden rounded-lg bg-white shadow-xl outline-none"
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <h2 className="text-sm font-semibold text-slate-700">{title}</h2>
          {roots.length > 1 ? (
            <select
              value={currentRoot ?? ''}
              onChange={(e) => {
                setCurrentRoot(e.target.value);
                void navigate(e.target.value);
              }}
              className="rounded border border-slate-300 px-2 py-1 text-xs"
            >
              {roots.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          ) : null}
        </div>

        <div className="flex items-center gap-2 border-b border-slate-200 bg-slate-50 px-5 py-2">
          <button
            type="button"
            onClick={() => parent && void navigate(parent)}
            disabled={isRoot || !parent}
            className="rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="Go to parent directory"
            title="Parent directory"
          >
            ↑
          </button>
          <nav className="flex flex-wrap items-center gap-1 text-xs text-slate-600">
            {breadcrumbs.map((crumb, i) => (
              <span key={crumb.path} className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => void navigate(crumb.path)}
                  className="rounded px-1 hover:bg-slate-200 hover:text-slate-900"
                >
                  {crumb.label}
                </button>
                {i < breadcrumbs.length - 1 ? <span className="text-slate-400">›</span> : null}
              </span>
            ))}
          </nav>
        </div>

        <div className="flex-1 overflow-y-auto px-2 py-2">
          {loading ? (
            <p className="px-4 py-6 text-sm text-slate-500">Loading…</p>
          ) : error ? (
            <p className="px-4 py-6 text-sm text-rose-600">{error}</p>
          ) : entries.length === 0 ? (
            <p className="px-4 py-6 text-sm text-slate-500">
              {mode === 'file'
                ? allowedExts.length
                  ? `No matching ${allowedExts.join('/')} files here.`
                  : 'No entries here.'
                : 'No subdirectories here.'}
            </p>
          ) : (
            <ul ref={listRef} role="listbox">
              {entries.map((entry, i) => (
                <li
                  key={entry.path}
                  role="option"
                  aria-selected={i === highlight}
                  onClick={() => setHighlight(i)}
                  onDoubleClick={() => {
                    if (entry.is_dir) void navigate(entry.path);
                    else if (mode === 'file') onSelect(entry.path);
                  }}
                  className={`flex cursor-pointer items-center gap-2 rounded px-3 py-2 text-sm ${
                    i === highlight ? 'bg-slate-200 text-slate-900' : 'text-slate-700 hover:bg-slate-100'
                  }`}
                >
                  {entry.is_dir ? <FolderIcon /> : <FileIcon />}
                  <span>{entry.name}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="border-t border-slate-200 bg-slate-50 px-5 py-3">
          <div className="text-xs text-slate-500">Selected</div>
          <div className="truncate font-mono text-sm text-slate-800">{selectablePath ?? '—'}</div>
          <div className="mt-3 flex justify-end gap-2">
            <button
              type="button"
              onClick={onCancel}
              className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={confirm}
              disabled={!selectablePath}
              className="rounded bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {buttonLabel}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}

function FolderIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-amber-600"
      aria-hidden="true"
    >
      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function FileIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-slate-500"
      aria-hidden="true"
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
    </svg>
  );
}
