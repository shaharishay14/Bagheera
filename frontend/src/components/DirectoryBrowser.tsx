import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ApiError, getRoots, listDirectory, type FsEntry } from '../lib/api';

type Mode = 'dir' | 'file';

interface BaseProps {
  open: boolean;
  initialPath?: string;
  mode?: Mode;
  /** When mode='file', only files whose extension (lowercase, leading dot) matches one of these is shown. */
  extensions?: string[];
  /**
   * Optional per-file thumbnail URL builder. When provided AND mode='file', each
   * FILE row renders a small `<img>` (its `src` is `thumbnailFor(entry.path)`)
   * that falls back to the file icon on load error. Purely decorative; omit for
   * unchanged (icon-only) behavior.
   */
  thumbnailFor?: (path: string) => string;
  onCancel: () => void;
}

interface SingleSelectProps extends BaseProps {
  onSelect: (path: string) => void;
  onSelectMulti?: never;
}

interface MultiSelectProps extends BaseProps {
  onSelectMulti: (paths: string[]) => void;
  onSelect?: never;
  mode?: 'file'; // multi only meaningful for files
}

type Props = SingleSelectProps | MultiSelectProps;

export default function DirectoryBrowser(props: Props) {
  const { open, initialPath, mode = 'dir', extensions, thumbnailFor, onCancel } = props;
  const multi = 'onSelectMulti' in props && typeof props.onSelectMulti === 'function';

  const [roots, setRoots] = useState<string[]>([]);
  const [currentRoot, setCurrentRoot] = useState<string | null>(null);
  const [path, setPath] = useState<string | null>(null);
  const [parent, setParent] = useState<string | null>(null);
  const [entries, setEntries] = useState<FsEntry[]>([]);
  const [isRoot, setIsRoot] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [highlight, setHighlight] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  // Paths whose thumbnail <img> failed to load — fall back to the file icon.
  const [thumbFailed, setThumbFailed] = useState<Set<string>>(() => new Set());

  const markThumbFailed = useCallback((p: string) => {
    setThumbFailed((prev) => {
      if (prev.has(p)) return prev;
      const next = new Set(prev);
      next.add(p);
      return next;
    });
  }, []);

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
    setSelected(new Set());
    let cancelled = false;
    (async () => {
      try {
        const rootRes = await getRoots();
        if (cancelled) return;
        setRoots(rootRes.roots);
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

  // Single-select target.
  const selectablePath: string | null =
    mode === 'dir'
      ? path
      : highlightedEntry && !highlightedEntry.is_dir
        ? highlightedEntry.path
        : null;

  const toggleSelected = (p: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(p)) next.delete(p);
      else next.add(p);
      return next;
    });
  };

  const confirm = () => {
    if (multi) {
      const paths = Array.from(selected).sort();
      if (paths.length > 0 && 'onSelectMulti' in props && props.onSelectMulti) {
        props.onSelectMulti(paths);
      }
    } else {
      if (selectablePath && 'onSelect' in props && props.onSelect) {
        props.onSelect(selectablePath);
      }
    }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onCancel();
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      if (mode === 'file' && highlightedEntry?.is_dir) {
        void navigate(highlightedEntry.path);
      } else if (multi && highlightedEntry && !highlightedEntry.is_dir) {
        toggleSelected(highlightedEntry.path);
      } else {
        confirm();
      }
      return;
    }
    if (e.key === ' ' && multi && highlightedEntry && !highlightedEntry.is_dir) {
      e.preventDefault();
      toggleSelected(highlightedEntry.path);
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

  const title = multi
    ? 'Choose files'
    : mode === 'file'
      ? 'Choose a file'
      : 'Choose a directory';
  const buttonLabel = multi
    ? `Select ${selected.size} file${selected.size === 1 ? '' : 's'}`
    : mode === 'file'
      ? 'Select this file'
      : 'Select this folder';
  const confirmDisabled = multi ? selected.size === 0 : !selectablePath;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 backdrop-blur-sm"
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
        className="flex h-[600px] w-[720px] max-w-[95vw] flex-col overflow-hidden rounded-2xl bg-surface shadow-modal outline-none"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <h2 className="text-sm font-semibold text-ink">{title}</h2>
          {roots.length > 1 ? (
            <select
              value={currentRoot ?? ''}
              onChange={(e) => {
                setCurrentRoot(e.target.value);
                void navigate(e.target.value);
              }}
              className="rounded border border-border bg-surface px-2 py-1 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-accent"
            >
              {roots.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          ) : null}
        </div>

        {/* Breadcrumb toolbar */}
        <div className="flex items-center gap-2 border-b border-border bg-surface-subtle px-5 py-2">
          <button
            type="button"
            onClick={() => parent && void navigate(parent)}
            disabled={isRoot || !parent}
            className="rounded border border-border bg-surface px-2 py-1 text-xs text-ink hover:bg-surface-subtle disabled:cursor-not-allowed disabled:opacity-40 transition-colors"
            aria-label="Go to parent directory"
            title="Parent directory"
          >
            ↑
          </button>
          <nav className="flex flex-wrap items-center gap-1 text-xs text-ink-muted">
            {breadcrumbs.map((crumb, i) => (
              <span key={crumb.path} className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => void navigate(crumb.path)}
                  className="rounded px-1 hover:bg-surface hover:text-ink transition-colors"
                >
                  {crumb.label}
                </button>
                {i < breadcrumbs.length - 1 ? (
                  <span className="text-ink-faint">›</span>
                ) : null}
              </span>
            ))}
          </nav>
        </div>

        {/* Entries list */}
        <div className="flex-1 overflow-y-auto px-2 py-2">
          {loading ? (
            <p className="px-4 py-6 text-sm text-ink-muted">Loading…</p>
          ) : error ? (
            <p className="px-4 py-6 text-sm text-[var(--s-failed-text)]">{error}</p>
          ) : entries.length === 0 ? (
            <p className="px-4 py-6 text-sm text-ink-muted">
              {mode === 'file'
                ? allowedExts.length
                  ? `No matching ${allowedExts.join('/')} files here.`
                  : 'No entries here.'
                : 'No subdirectories here.'}
            </p>
          ) : (
            <ul ref={listRef} role="listbox">
              {entries.map((entry, i) => {
                const isChecked = multi && !entry.is_dir && selected.has(entry.path);
                return (
                  <li
                    key={entry.path}
                    role="option"
                    aria-selected={i === highlight}
                    onClick={() => {
                      setHighlight(i);
                      if (multi && !entry.is_dir) toggleSelected(entry.path);
                    }}
                    onDoubleClick={() => {
                      if (entry.is_dir) void navigate(entry.path);
                      else if (!multi && mode === 'file' && 'onSelect' in props && props.onSelect) {
                        props.onSelect(entry.path);
                      }
                    }}
                    className={`flex cursor-pointer items-center gap-2 rounded px-3 py-2 text-sm transition-colors ${
                      i === highlight
                        ? 'bg-accent-muted text-ink'
                        : 'text-ink-muted hover:bg-surface-subtle hover:text-ink'
                    }`}
                  >
                    {multi && !entry.is_dir ? (
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => toggleSelected(entry.path)}
                        onClick={(e) => e.stopPropagation()}
                        className="h-4 w-4 rounded border-border accent-accent"
                      />
                    ) : null}
                    {entry.is_dir ? (
                      <FolderIcon />
                    ) : thumbnailFor && mode === 'file' && !thumbFailed.has(entry.path) ? (
                      <img
                        src={thumbnailFor(entry.path)}
                        alt=""
                        loading="lazy"
                        onError={() => markThumbFailed(entry.path)}
                        className="h-8 w-8 shrink-0 rounded border border-border object-cover"
                      />
                    ) : (
                      <FileIcon />
                    )}
                    <span>{entry.name}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Footer with confirm */}
        <div className="border-t border-border bg-surface-subtle px-5 py-3">
          <div className="text-[11px] font-semibold uppercase tracking-widest text-ink-faint">
            {multi ? 'Selected files' : 'Selected'}
          </div>
          <div className="mt-0.5 truncate font-mono text-sm text-ink">
            {multi
              ? selected.size === 0
                ? '-'
                : `${selected.size} file${selected.size === 1 ? '' : 's'}`
              : (selectablePath ?? '-')}
          </div>
          <div className="mt-3 flex justify-end gap-2">
            <button
              type="button"
              onClick={onCancel}
              className="rounded border border-border bg-surface px-3 py-1.5 text-sm text-ink hover:bg-surface-subtle transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={confirm}
              disabled={confirmDisabled}
              className="rounded-full bg-grad-accent px-4 py-1.5 text-sm font-semibold text-white shadow-glow hover:shadow-glow-lg hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none transition-all duration-150"
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
      className="shrink-0 text-amber-600"
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
      className="shrink-0 text-ink-faint"
      aria-hidden="true"
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
    </svg>
  );
}
