import { useEffect, useMemo, useState } from 'react';
import {
  ApiError,
  createInferenceNote,
  createModelNote,
  deleteInferenceNote,
  deleteModelNote,
  listInferenceNotes,
  listModelNotes,
  updateInferenceNote,
  updateModelNote,
  type InferenceNoteInfo,
  type ModelNoteInfo,
} from '../lib/api';

type NoteTarget =
  | { kind: 'model'; modelId: string }
  | { kind: 'inference'; inferenceId: string };

interface NoteShape {
  id: string;
  body: string;
  updated_at: string;
}

interface Props {
  target?: NoteTarget;
  /** Back-compat: equivalent to `target={ kind: 'model', modelId }`. */
  modelId?: string;
}

export default function NotesThread({ target, modelId }: Props) {
  const resolved: NoteTarget = useMemo(() => {
    if (target) return target;
    if (modelId) return { kind: 'model', modelId };
    throw new Error('NotesThread needs either target or modelId');
  }, [target, modelId]);

  const api = useMemo(() => makeApi(resolved), [resolved]);

  const [notes, setNotes] = useState<NoteShape[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingBody, setEditingBody] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const res = await api.list();
        if (!cancelled) setNotes(res);
      } catch (err) {
        if (!cancelled) {
          const msg = err instanceof ApiError ? err.message : 'Failed to load notes.';
          setError(msg);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api]);

  const onAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!draft.trim()) return;
    setSubmitting(true);
    try {
      const created = await api.create(draft.trim());
      setNotes((prev) => [created, ...prev]);
      setDraft('');
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Failed to save note.';
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const onSaveEdit = async (id: string) => {
    if (!editingBody.trim()) return;
    try {
      const updated = await api.update(id, editingBody.trim());
      setNotes((prev) => prev.map((n) => (n.id === id ? updated : n)));
      setEditingId(null);
      setEditingBody('');
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Failed to update note.';
      setError(msg);
    }
  };

  const onDelete = async (id: string) => {
    if (!confirm('Delete this note?')) return;
    try {
      await api.remove(id);
      setNotes((prev) => prev.filter((n) => n.id !== id));
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Failed to delete note.';
      setError(msg);
    }
  };

  return (
    <div className="space-y-3">
      <form onSubmit={onAdd} className="space-y-2">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Add a note (Markdown supported)…"
          rows={3}
          className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
        />
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={submitting || !draft.trim()}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? 'Saving…' : 'Save note'}
          </button>
        </div>
      </form>

      {error ? (
        <p className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800">
          {error}
        </p>
      ) : null}

      {loading ? (
        <p className="text-xs text-slate-500">Loading notes…</p>
      ) : notes.length === 0 ? (
        <p className="text-xs text-slate-500">No notes yet.</p>
      ) : (
        <ul className="space-y-2">
          {notes.map((note) => (
            <li key={note.id} className="rounded-md border border-slate-200 bg-slate-50 p-3">
              {editingId === note.id ? (
                <div className="space-y-2">
                  <textarea
                    value={editingBody}
                    onChange={(e) => setEditingBody(e.target.value)}
                    rows={3}
                    className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
                  />
                  <div className="flex justify-end gap-2 text-xs">
                    <button
                      type="button"
                      onClick={() => {
                        setEditingId(null);
                        setEditingBody('');
                      }}
                      className="rounded-md border border-slate-300 bg-white px-2 py-1 text-slate-700 hover:bg-slate-100"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={() => onSaveEdit(note.id)}
                      className="rounded-md bg-slate-900 px-2 py-1 text-white hover:bg-slate-800"
                    >
                      Save
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <pre className="whitespace-pre-wrap font-sans text-sm text-slate-800">{note.body}</pre>
                  <div className="mt-2 flex items-center justify-between text-[11px] text-slate-500">
                    <span>{new Date(note.updated_at).toLocaleString()}</span>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setEditingId(note.id);
                          setEditingBody(note.body);
                        }}
                        className="hover:text-slate-900"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => onDelete(note.id)}
                        className="text-rose-600 hover:text-rose-800"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

interface NoteApi {
  list(): Promise<NoteShape[]>;
  create(body: string): Promise<NoteShape>;
  update(id: string, body: string): Promise<NoteShape>;
  remove(id: string): Promise<void>;
}

function makeApi(target: NoteTarget): NoteApi {
  if (target.kind === 'model') {
    const id = target.modelId;
    return {
      list: () => listModelNotes(id) as Promise<ModelNoteInfo[]>,
      create: (body) => createModelNote({ model_id: id, body }),
      update: (noteId, body) => updateModelNote(noteId, { body }),
      remove: (noteId) => deleteModelNote(noteId),
    };
  }
  const id = target.inferenceId;
  return {
    list: () => listInferenceNotes(id) as Promise<InferenceNoteInfo[]>,
    create: (body) => createInferenceNote({ inference_id: id, body }),
    update: (noteId, body) => updateInferenceNote(noteId, { body }),
    remove: (noteId) => deleteInferenceNote(noteId),
  };
}
