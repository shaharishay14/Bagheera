/**
 * Drag-to-reorder helpers behind the Queue page. `moveBefore` computes the
 * optimistic order the UI shows; `sameOrder` decides whether that order is
 * different enough to POST to /api/queue/reorder.
 */
import { describe, expect, it } from 'vitest';
import { moveBefore, sameOrder } from './QueuePage';
import type { JobView } from '../lib/api';

function job(id: string): JobView {
  return {
    id,
    job_type: 'panther_train',
    status: 'queued',
    ref_table: 'model_groups',
    ref_id: 'g',
    queue_position: null,
    created_at: '2026-01-01T00:00:00Z',
    started_at: null,
    finished_at: null,
    error_message: null,
    title: id,
    subtitle: null,
  } as JobView;
}

const ids = (list: JobView[]) => list.map((j) => j.id);

describe('moveBefore', () => {
  const list = [job('a'), job('b'), job('c'), job('d')];

  it('moves a later job in front of an earlier one', () => {
    expect(ids(moveBefore(list, 'd', 'b'))).toEqual(['a', 'd', 'b', 'c']);
  });

  it('moves an earlier job down to the target position', () => {
    expect(ids(moveBefore(list, 'a', 'c'))).toEqual(['b', 'c', 'a', 'd']);
  });

  it('moves a job to the head of the queue', () => {
    expect(ids(moveBefore(list, 'c', 'a'))).toEqual(['c', 'a', 'b', 'd']);
  });

  it('is a no-op when a job is dropped on itself', () => {
    expect(moveBefore(list, 'b', 'b')).toBe(list);
  });

  it('is a no-op when the dragged id is unknown', () => {
    expect(moveBefore(list, 'ghost', 'b')).toBe(list);
  });

  it('is a no-op when the target id is unknown', () => {
    expect(moveBefore(list, 'a', 'ghost')).toBe(list);
  });

  it('never mutates the input list', () => {
    const before = ids(list);
    moveBefore(list, 'd', 'a');
    expect(ids(list)).toEqual(before);
  });

  it('preserves length and membership', () => {
    const next = moveBefore(list, 'd', 'b');
    expect(next).toHaveLength(list.length);
    expect(ids(next).slice().sort()).toEqual(ids(list).slice().sort());
  });

  it('handles a single-element queue', () => {
    const one = [job('a')];
    expect(moveBefore(one, 'a', 'a')).toBe(one);
  });
});

describe('sameOrder', () => {
  it('is true for identical sequences', () => {
    expect(sameOrder(['a', 'b', 'c'], ['a', 'b', 'c'])).toBe(true);
  });

  it('is false when two entries are swapped', () => {
    expect(sameOrder(['a', 'b', 'c'], ['a', 'c', 'b'])).toBe(false);
  });

  it('is false when the lengths differ', () => {
    expect(sameOrder(['a', 'b'], ['a', 'b', 'c'])).toBe(false);
  });

  it('is true for two empty queues', () => {
    expect(sameOrder([], [])).toBe(true);
  });

  it('compares position, not membership', () => {
    expect(sameOrder(['a', 'b'], ['b', 'a'])).toBe(false);
  });
});
