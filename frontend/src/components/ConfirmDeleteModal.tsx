import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

interface Props {
  open: boolean;
  title: string;
  /** The thing being deleted, rendered prominently (e.g. the group name). */
  name: string;
  /** Body warning copy. */
  children?: React.ReactNode;
  /** Inline error (e.g. a 409 explaining why deletion was blocked). */
  error?: string | null;
  busy?: boolean;
  confirmLabel?: string;
  onCancel: () => void;
  onConfirm: () => void;
}

/**
 * A small accessible centered confirm-delete modal (portal + backdrop + Esc).
 * Used wherever a destructive action needs explicit confirmation. The
 * destructive "Delete" button uses the failed/red status tokens.
 */
export default function ConfirmDeleteModal({
  open,
  title,
  name,
  children,
  error,
  busy = false,
  confirmLabel = 'Delete',
  onCancel,
  onConfirm,
}: Props) {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    dialogRef.current?.focus();
    return () => {
      previouslyFocused.current?.focus?.();
    };
  }, [open]);

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-4 backdrop-blur-sm"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) onCancel();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        onKeyDown={(e) => {
          if (e.key === 'Escape' && !busy) onCancel();
        }}
        className="w-full max-w-md overflow-hidden rounded-2xl bg-surface shadow-modal outline-none"
      >
        <div className="border-b border-border px-5 py-3">
          <h2 className="text-sm font-semibold text-ink">{title}</h2>
        </div>

        <div className="space-y-3 px-5 py-4">
          <p className="text-sm text-ink">
            <span className="font-semibold">{name}</span>
          </p>
          <div className="text-sm text-ink-muted">{children}</div>

          {error ? (
            <div className="rounded-md border border-[var(--s-failed-border)] bg-[var(--s-failed-bg)] px-3 py-2 text-xs text-[var(--s-failed-text)]">
              {error}
            </div>
          ) : null}
        </div>

        <div className="flex justify-end gap-2 border-t border-border bg-surface-subtle px-5 py-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-full border border-border-strong bg-surface px-4 py-1.5 text-sm font-semibold text-ink hover:bg-surface-subtle disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="rounded-full border border-[var(--s-failed-border)] bg-[var(--s-failed-bg)] px-4 py-1.5 text-sm font-semibold text-[var(--s-failed-text)] hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-50 transition-all"
          >
            {busy ? 'Deleting…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
