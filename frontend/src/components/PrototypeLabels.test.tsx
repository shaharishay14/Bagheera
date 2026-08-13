/**
 * Per-prototype label editing: hydrate from the server, save on blur, and show
 * per-field save state without losing the other fields' edits.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import PrototypeLabels from './PrototypeLabels';
import { ApiError } from '../lib/api';

const listPrototypeLabels = vi.fn();
const upsertPrototypeLabel = vi.fn();

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api');
  return {
    ...actual,
    listPrototypeLabels: (...a: unknown[]) => listPrototypeLabels(...a),
    upsertPrototypeLabel: (...a: unknown[]) => upsertPrototypeLabel(...a),
  };
});

const label = (index: number, text: string) => ({
  id: `l-${index}`,
  model_id: 'm-1',
  prototype_index: index,
  label: text,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
});

const inputs = () => screen.getAllByRole('textbox') as HTMLInputElement[];

beforeEach(() => {
  listPrototypeLabels.mockReset();
  upsertPrototypeLabel.mockReset();
  listPrototypeLabels.mockResolvedValue([]);
  upsertPrototypeLabel.mockResolvedValue(label(0, ''));
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('PrototypeLabels — loading', () => {
  it('shows a loading line before the labels arrive', () => {
    let release!: (v: unknown) => void;
    listPrototypeLabels.mockReturnValue(new Promise((r) => (release = r)));
    render(<PrototypeLabels modelId="m-1" nProto={4} />);
    expect(screen.getByText('Loading labels…')).toBeTruthy();
    release([]);
  });

  it('renders one input per prototype', async () => {
    render(<PrototypeLabels modelId="m-1" nProto={4} />);
    await waitFor(() => expect(inputs()).toHaveLength(4));
    expect(screen.getByText('Prototype 0')).toBeTruthy();
    expect(screen.getByText('Prototype 3')).toBeTruthy();
  });

  it('hydrates each input from its stored label', async () => {
    listPrototypeLabels.mockResolvedValue([label(0, 'stroma'), label(2, 'necrosis')]);
    render(<PrototypeLabels modelId="m-1" nProto={4} />);
    await waitFor(() => expect(inputs()[0].value).toBe('stroma'));
    expect(inputs()[1].value).toBe('');
    expect(inputs()[2].value).toBe('necrosis');
  });

  it('ignores stored labels whose index is outside the prototype range', async () => {
    listPrototypeLabels.mockResolvedValue([label(0, 'kept'), label(9, 'dropped')]);
    render(<PrototypeLabels modelId="m-1" nProto={2} />);
    await waitFor(() => expect(inputs()).toHaveLength(2));
    expect(inputs().map((i) => i.value)).toEqual(['kept', '']);
  });

  it('shows the API error instead of the grid', async () => {
    listPrototypeLabels.mockImplementation(() =>
      Promise.reject(new ApiError(404, 'Model not found.')),
    );
    render(<PrototypeLabels modelId="m-1" nProto={4} />);
    expect(await screen.findByText('Model not found.')).toBeTruthy();
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('falls back to a generic message for a non-API failure', async () => {
    listPrototypeLabels.mockImplementation(() => Promise.reject(new TypeError('offline')));
    render(<PrototypeLabels modelId="m-1" nProto={4} />);
    expect(await screen.findByText('Failed to load labels.')).toBeTruthy();
  });

  it('reloads when the model changes', async () => {
    listPrototypeLabels.mockResolvedValue([label(0, 'first model')]);
    const { rerender } = render(<PrototypeLabels modelId="m-1" nProto={2} />);
    await waitFor(() => expect(inputs()[0].value).toBe('first model'));

    listPrototypeLabels.mockResolvedValue([label(0, 'second model')]);
    rerender(<PrototypeLabels modelId="m-2" nProto={2} />);
    await waitFor(() => expect(inputs()[0].value).toBe('second model'));
    expect(listPrototypeLabels).toHaveBeenLastCalledWith('m-2');
  });
});

describe('PrototypeLabels — saving', () => {
  it('upserts the edited prototype on blur', async () => {
    render(<PrototypeLabels modelId="m-1" nProto={3} />);
    await waitFor(() => expect(inputs()).toHaveLength(3));

    fireEvent.change(inputs()[1], { target: { value: 'fat' } });
    fireEvent.blur(inputs()[1]);

    await waitFor(() =>
      expect(upsertPrototypeLabel).toHaveBeenCalledWith({
        model_id: 'm-1',
        prototype_index: 1,
        label: 'fat',
      }),
    );
  });

  it('shows the saved indicator and clears it after the fade delay', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<PrototypeLabels modelId="m-1" nProto={1} />);
    await waitFor(() => expect(inputs()).toHaveLength(1));

    fireEvent.change(inputs()[0], { target: { value: 'fat' } });
    fireEvent.blur(inputs()[0]);
    expect(await screen.findByText('saved ✓')).toBeTruthy();

    await vi.advanceTimersByTimeAsync(1300);
    await waitFor(() => expect(screen.queryByText('saved ✓')).toBeNull());
  });

  it('reports a save failure inline and leaves the typed value alone', async () => {
    upsertPrototypeLabel.mockImplementation(() =>
      Promise.reject(new ApiError(400, 'prototype_index 8 >= n_proto=8.')),
    );
    render(<PrototypeLabels modelId="m-1" nProto={2} />);
    await waitFor(() => expect(inputs()).toHaveLength(2));

    fireEvent.change(inputs()[0], { target: { value: 'oops' } });
    fireEvent.blur(inputs()[0]);

    expect(await screen.findByText('prototype_index 8 >= n_proto=8.')).toBeTruthy();
    expect(screen.getByText('error')).toBeTruthy();
    expect(inputs()[0].value).toBe('oops');
  });

  it('marks only the failing field as errored', async () => {
    upsertPrototypeLabel.mockImplementation(() => Promise.reject(new ApiError(500, 'boom')));
    render(<PrototypeLabels modelId="m-1" nProto={2} />);
    await waitFor(() => expect(inputs()).toHaveLength(2));

    fireEvent.blur(inputs()[1]);
    await screen.findByText('boom');

    expect(inputs()[1].className).toContain('--s-failed-border');
    expect(inputs()[0].className).toContain('border-border-strong');
  });

  it('falls back to a generic save message for a non-API failure', async () => {
    upsertPrototypeLabel.mockImplementation(() => Promise.reject(new TypeError('offline')));
    render(<PrototypeLabels modelId="m-1" nProto={1} />);
    await waitFor(() => expect(inputs()).toHaveLength(1));

    fireEvent.blur(inputs()[0]);
    expect(await screen.findByText('Failed to save.')).toBeTruthy();
  });

  it('saves an emptied label so a prototype can be un-named', async () => {
    listPrototypeLabels.mockResolvedValue([label(0, 'stroma')]);
    render(<PrototypeLabels modelId="m-1" nProto={1} />);
    await waitFor(() => expect(inputs()[0].value).toBe('stroma'));

    fireEvent.change(inputs()[0], { target: { value: '' } });
    fireEvent.blur(inputs()[0]);

    await waitFor(() =>
      expect(upsertPrototypeLabel).toHaveBeenCalledWith({
        model_id: 'm-1',
        prototype_index: 0,
        label: '',
      }),
    );
  });

  it('keeps other fields untouched while one is edited', async () => {
    render(<PrototypeLabels modelId="m-1" nProto={3} />);
    await waitFor(() => expect(inputs()).toHaveLength(3));

    fireEvent.change(inputs()[0], { target: { value: 'a' } });
    fireEvent.change(inputs()[2], { target: { value: 'c' } });

    expect(inputs().map((i) => i.value)).toEqual(['a', '', 'c']);
  });
});
