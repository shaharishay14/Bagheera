/**
 * The annotation thread, exercised against both targets it supports (model
 * notes and inference notes). The API module is mocked, so nothing reaches the
 * network — what's under test is the optimistic list updates and error surface.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import NotesThread from './NotesThread';
import { ApiError } from '../lib/api';

const listModelNotes = vi.fn();
const createModelNote = vi.fn();
const updateModelNote = vi.fn();
const deleteModelNote = vi.fn();
const listInferenceNotes = vi.fn();
const createInferenceNote = vi.fn();

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api');
  return {
    ...actual,
    listModelNotes: (...a: unknown[]) => listModelNotes(...a),
    createModelNote: (...a: unknown[]) => createModelNote(...a),
    updateModelNote: (...a: unknown[]) => updateModelNote(...a),
    deleteModelNote: (...a: unknown[]) => deleteModelNote(...a),
    listInferenceNotes: (...a: unknown[]) => listInferenceNotes(...a),
    createInferenceNote: (...a: unknown[]) => createInferenceNote(...a),
    updateInferenceNote: vi.fn(),
    deleteInferenceNote: vi.fn(),
  };
});

const note = (id: string, body: string) => ({
  id,
  body,
  model_id: 'm-1',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
});

beforeEach(() => {
  [
    listModelNotes,
    createModelNote,
    updateModelNote,
    deleteModelNote,
    listInferenceNotes,
    createInferenceNote,
  ].forEach((m) => m.mockReset());
  listModelNotes.mockResolvedValue([]);
  listInferenceNotes.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('NotesThread — loading', () => {
  it('shows a loading line before the notes arrive', () => {
    listModelNotes.mockReturnValue(new Promise(() => {}));
    render(<NotesThread modelId="m-1" />);
    expect(screen.getByText('Loading notes…')).toBeTruthy();
  });

  it('shows the empty state when there are no notes', async () => {
    render(<NotesThread modelId="m-1" />);
    expect(await screen.findByText('No notes yet.')).toBeTruthy();
  });

  it('renders the notes it loaded', async () => {
    listModelNotes.mockResolvedValue([note('n-1', 'first'), note('n-2', 'second')]);
    render(<NotesThread modelId="m-1" />);
    expect(await screen.findByText('first')).toBeTruthy();
    expect(screen.getByText('second')).toBeTruthy();
  });

  it('surfaces an API error from the initial load', async () => {
    listModelNotes.mockRejectedValue(new ApiError(404, 'Model not found.'));
    render(<NotesThread modelId="m-1" />);
    expect(await screen.findByText('Model not found.')).toBeTruthy();
  });

  it('falls back to a generic message for a non-API failure', async () => {
    listModelNotes.mockRejectedValue(new TypeError('offline'));
    render(<NotesThread modelId="m-1" />);
    expect(await screen.findByText('Failed to load notes.')).toBeTruthy();
  });
});

describe('NotesThread — targets', () => {
  it('reads model notes for the back-compat modelId prop', async () => {
    render(<NotesThread modelId="m-42" />);
    await waitFor(() => expect(listModelNotes).toHaveBeenCalledWith('m-42'));
  });

  it('reads model notes for an explicit model target', async () => {
    render(<NotesThread target={{ kind: 'model', modelId: 'm-7' }} />);
    await waitFor(() => expect(listModelNotes).toHaveBeenCalledWith('m-7'));
  });

  it('reads inference notes for an inference target', async () => {
    render(<NotesThread target={{ kind: 'inference', inferenceId: 'i-9' }} />);
    await waitFor(() => expect(listInferenceNotes).toHaveBeenCalledWith('i-9'));
    expect(listModelNotes).not.toHaveBeenCalled();
  });

  it('posts inference notes to the inference endpoint', async () => {
    createInferenceNote.mockResolvedValue(note('n-1', 'observed necrosis'));
    render(<NotesThread target={{ kind: 'inference', inferenceId: 'i-9' }} />);
    await screen.findByText('No notes yet.');

    await userEvent.type(screen.getByRole('textbox'), 'observed necrosis');
    await userEvent.click(screen.getByRole('button', { name: 'Save note' }));

    await waitFor(() =>
      expect(createInferenceNote).toHaveBeenCalledWith({
        inference_id: 'i-9',
        body: 'observed necrosis',
      }),
    );
  });
});

describe('NotesThread — adding', () => {
  it('disables the save button until the draft has content', async () => {
    render(<NotesThread modelId="m-1" />);
    await screen.findByText('No notes yet.');
    const save = screen.getByRole('button', { name: 'Save note' });
    expect(save.hasAttribute('disabled')).toBe(true);

    await userEvent.type(screen.getByRole('textbox'), 'x');
    expect(save.hasAttribute('disabled')).toBe(false);
  });

  it('keeps the save button disabled for whitespace-only drafts', async () => {
    render(<NotesThread modelId="m-1" />);
    await screen.findByText('No notes yet.');
    await userEvent.type(screen.getByRole('textbox'), '   ');
    expect(screen.getByRole('button', { name: 'Save note' }).hasAttribute('disabled')).toBe(true);
  });

  it('trims the body before posting', async () => {
    createModelNote.mockResolvedValue(note('n-1', 'trimmed'));
    render(<NotesThread modelId="m-1" />);
    await screen.findByText('No notes yet.');

    await userEvent.type(screen.getByRole('textbox'), '  trimmed  ');
    await userEvent.click(screen.getByRole('button', { name: 'Save note' }));

    await waitFor(() =>
      expect(createModelNote).toHaveBeenCalledWith({ model_id: 'm-1', body: 'trimmed' }),
    );
  });

  it('prepends the new note and clears the draft', async () => {
    listModelNotes.mockResolvedValue([note('n-old', 'older note')]);
    createModelNote.mockResolvedValue(note('n-new', 'newest note'));
    render(<NotesThread modelId="m-1" />);
    await screen.findByText('older note');

    await userEvent.type(screen.getByRole('textbox'), 'newest note');
    await userEvent.click(screen.getByRole('button', { name: 'Save note' }));

    await screen.findByText('newest note');
    const bodies = screen.getAllByRole('listitem').map((li) => li.textContent);
    expect(bodies[0]).toContain('newest note');
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('');
  });

  it('shows an error and keeps the list unchanged when the save fails', async () => {
    createModelNote.mockRejectedValue(new ApiError(404, 'Model not found.'));
    render(<NotesThread modelId="m-1" />);
    await screen.findByText('No notes yet.');

    await userEvent.type(screen.getByRole('textbox'), 'doomed');
    await userEvent.click(screen.getByRole('button', { name: 'Save note' }));

    expect(await screen.findByText('Model not found.')).toBeTruthy();
    expect(screen.getByText('No notes yet.')).toBeTruthy();
  });
});

describe('NotesThread — editing', () => {
  it('swaps the note into an edit box seeded with its body', async () => {
    listModelNotes.mockResolvedValue([note('n-1', 'original')]);
    render(<NotesThread modelId="m-1" />);
    await screen.findByText('original');

    await userEvent.click(screen.getByRole('button', { name: 'Edit' }));
    const editors = screen.getAllByRole('textbox') as HTMLTextAreaElement[];
    expect(editors.some((t) => t.value === 'original')).toBe(true);
  });

  it('saves the edit and re-renders the updated body', async () => {
    listModelNotes.mockResolvedValue([note('n-1', 'original')]);
    updateModelNote.mockResolvedValue(note('n-1', 'revised'));
    render(<NotesThread modelId="m-1" />);
    await screen.findByText('original');

    await userEvent.click(screen.getByRole('button', { name: 'Edit' }));
    const editor = (screen.getAllByRole('textbox') as HTMLTextAreaElement[]).find(
      (t) => t.value === 'original',
    )!;
    await userEvent.clear(editor);
    await userEvent.type(editor, 'revised');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('revised')).toBeTruthy();
    expect(updateModelNote).toHaveBeenCalledWith('n-1', { body: 'revised' });
  });

  it('discards the edit on Cancel', async () => {
    listModelNotes.mockResolvedValue([note('n-1', 'original')]);
    render(<NotesThread modelId="m-1" />);
    await screen.findByText('original');

    await userEvent.click(screen.getByRole('button', { name: 'Edit' }));
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(screen.getByText('original')).toBeTruthy();
    expect(updateModelNote).not.toHaveBeenCalled();
  });

  it('refuses to save an empty edit', async () => {
    listModelNotes.mockResolvedValue([note('n-1', 'original')]);
    render(<NotesThread modelId="m-1" />);
    await screen.findByText('original');

    await userEvent.click(screen.getByRole('button', { name: 'Edit' }));
    const editor = (screen.getAllByRole('textbox') as HTMLTextAreaElement[]).find(
      (t) => t.value === 'original',
    )!;
    await userEvent.clear(editor);
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(updateModelNote).not.toHaveBeenCalled();
  });
});

describe('NotesThread — deleting', () => {
  it('asks for confirmation and removes the note on yes', async () => {
    vi.stubGlobal('confirm', vi.fn(() => true));
    listModelNotes.mockResolvedValue([note('n-1', 'doomed')]);
    deleteModelNote.mockResolvedValue(undefined);
    render(<NotesThread modelId="m-1" />);
    await screen.findByText('doomed');

    await userEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(screen.queryByText('doomed')).toBeNull());
    expect(deleteModelNote).toHaveBeenCalledWith('n-1');
  });

  it('keeps the note when the confirmation is declined', async () => {
    vi.stubGlobal('confirm', vi.fn(() => false));
    listModelNotes.mockResolvedValue([note('n-1', 'kept')]);
    render(<NotesThread modelId="m-1" />);
    await screen.findByText('kept');

    await userEvent.click(screen.getByRole('button', { name: 'Delete' }));

    expect(screen.getByText('kept')).toBeTruthy();
    expect(deleteModelNote).not.toHaveBeenCalled();
  });

  it('surfaces a delete failure and keeps the note visible', async () => {
    vi.stubGlobal('confirm', vi.fn(() => true));
    listModelNotes.mockResolvedValue([note('n-1', 'stubborn')]);
    deleteModelNote.mockRejectedValue(new ApiError(404, 'Note not found.'));
    render(<NotesThread modelId="m-1" />);
    await screen.findByText('stubborn');

    await userEvent.click(screen.getByRole('button', { name: 'Delete' }));

    expect(await screen.findByText('Note not found.')).toBeTruthy();
    expect(screen.getByText('stubborn')).toBeTruthy();
  });

  it('only deletes the note whose button was clicked', async () => {
    vi.stubGlobal('confirm', vi.fn(() => true));
    listModelNotes.mockResolvedValue([note('n-1', 'keep me'), note('n-2', 'remove me')]);
    deleteModelNote.mockResolvedValue(undefined);
    render(<NotesThread modelId="m-1" />);
    await screen.findByText('remove me');

    const target = screen.getAllByRole('listitem').find((li) => li.textContent?.includes('remove me'))!;
    await userEvent.click(within(target).getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(screen.queryByText('remove me')).toBeNull());
    expect(screen.getByText('keep me')).toBeTruthy();
    expect(deleteModelNote).toHaveBeenCalledWith('n-2');
  });
});
