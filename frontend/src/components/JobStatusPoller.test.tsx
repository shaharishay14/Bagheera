/**
 * The polling contract every long-running page depends on: a 2s setTimeout
 * loop that stops when everything is terminal, reports transitions once, and
 * surfaces API errors inline instead of throwing.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import JobStatusPoller from './JobStatusPoller';
import { ApiError, type JobInfo } from '../lib/api';

const listJobs = vi.fn();
const getJob = vi.fn();

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api');
  return {
    ...actual,
    listJobs: (...args: unknown[]) => listJobs(...args),
    getJob: (...args: unknown[]) => getJob(...args),
  };
});

function job(overrides: Partial<JobInfo> = {}): JobInfo {
  return {
    id: 'job-1',
    job_type: 'panther_train',
    status: 'queued',
    ref_table: 'model_groups',
    ref_id: 'g-1',
    queue_position: 1,
    created_at: '2026-01-01T00:00:00Z',
    started_at: null,
    finished_at: null,
    error_message: null,
    ...overrides,
  } as JobInfo;
}

beforeEach(() => {
  listJobs.mockReset();
  getJob.mockReset();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('JobStatusPoller', () => {
  it('renders nothing while the job list is empty', async () => {
    listJobs.mockResolvedValue([]);
    const { container } = render(<JobStatusPoller refId="g-1" />);
    await waitFor(() => expect(listJobs).toHaveBeenCalled());
    expect(container.innerHTML).toBe('');
  });

  it('lists each job with its type and status pill', async () => {
    listJobs.mockResolvedValue([job({ job_type: 'post_train_viz', status: 'running' })]);
    render(<JobStatusPoller refId="g-1" />);
    expect(await screen.findByText('post_train_viz')).toBeTruthy();
    expect(screen.getByText('running')).toBeTruthy();
  });

  it('scopes the query to the ref it was given', async () => {
    listJobs.mockResolvedValue([]);
    render(<JobStatusPoller refId="m-7" refTable="models" />);
    await waitFor(() =>
      expect(listJobs).toHaveBeenCalledWith({ refId: 'm-7', refTable: 'models', limit: 50 }),
    );
  });

  it('stops polling once every job is terminal', async () => {
    vi.useFakeTimers();
    listJobs.mockResolvedValue([job({ status: 'succeeded' })]);
    render(<JobStatusPoller refId="g-1" />);
    await act(async () => {});
    expect(listJobs).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(10_000);
    });
    expect(listJobs).toHaveBeenCalledTimes(1);
  });

  it('keeps polling while a job is still in flight', async () => {
    vi.useFakeTimers();
    listJobs.mockResolvedValue([job({ status: 'running' })]);
    render(<JobStatusPoller refId="g-1" />);
    await act(async () => {});
    expect(listJobs).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    expect(listJobs).toHaveBeenCalledTimes(2);
  });

  it('honors a custom poll interval', async () => {
    vi.useFakeTimers();
    listJobs.mockResolvedValue([job({ status: 'running' })]);
    render(<JobStatusPoller refId="g-1" intervalMs={500} />);
    await act(async () => {});

    await act(async () => {
      vi.advanceTimersByTime(500);
    });
    expect(listJobs).toHaveBeenCalledTimes(2);
  });

  it('keeps polling terminal jobs when stopWhenIdle is off', async () => {
    vi.useFakeTimers();
    listJobs.mockResolvedValue([job({ status: 'succeeded' })]);
    render(<JobStatusPoller refId="g-1" stopWhenIdle={false} />);
    await act(async () => {});

    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    expect(listJobs).toHaveBeenCalledTimes(2);
  });

  it('notifies once when a job transitions to succeeded', async () => {
    vi.useFakeTimers();
    const onJobFinished = vi.fn();
    listJobs
      .mockResolvedValueOnce([job({ status: 'running' })])
      .mockResolvedValue([job({ status: 'succeeded' })]);

    render(<JobStatusPoller refId="g-1" onJobFinished={onJobFinished} />);
    await act(async () => {});
    expect(onJobFinished).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    expect(onJobFinished).toHaveBeenCalledTimes(1);
    expect(onJobFinished.mock.calls[0][0].status).toBe('succeeded');
  });

  it('notifies on a failure transition too', async () => {
    vi.useFakeTimers();
    const onJobFinished = vi.fn();
    listJobs
      .mockResolvedValueOnce([job({ status: 'running' })])
      .mockResolvedValue([job({ status: 'failed' })]);

    render(<JobStatusPoller refId="g-1" onJobFinished={onJobFinished} stopWhenIdle={false} />);
    await act(async () => {});
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    expect(onJobFinished).toHaveBeenCalledTimes(1);

    // A repeat poll at the same status must not re-notify.
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    expect(onJobFinished).toHaveBeenCalledTimes(1);
  });

  it('shows the API error message instead of the list', async () => {
    listJobs.mockRejectedValue(new ApiError(500, 'Database is locked.'));
    render(<JobStatusPoller refId="g-1" />);
    expect(await screen.findByText('Database is locked.')).toBeTruthy();
  });

  it('falls back to a generic message for a non-API failure', async () => {
    listJobs.mockRejectedValue(new TypeError('network down'));
    render(<JobStatusPoller refId="g-1" />);
    expect(await screen.findByText('Failed to poll jobs.')).toBeTruthy();
  });

  it('recovers and re-renders the list after a transient error', async () => {
    vi.useFakeTimers();
    listJobs
      .mockRejectedValueOnce(new ApiError(503, 'Service unavailable'))
      .mockResolvedValue([job({ status: 'succeeded' })]);

    render(<JobStatusPoller refId="g-1" />);
    await act(async () => {});
    expect(screen.getByText('Service unavailable')).toBeTruthy();

    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    expect(screen.queryByText('Service unavailable')).toBeNull();
    expect(screen.getByText('panther_train')).toBeTruthy();
  });

  it('stops polling after unmount', async () => {
    vi.useFakeTimers();
    listJobs.mockResolvedValue([job({ status: 'running' })]);
    const { unmount } = render(<JobStatusPoller refId="g-1" />);
    await act(async () => {});
    unmount();

    await act(async () => {
      vi.advanceTimersByTime(10_000);
    });
    expect(listJobs).toHaveBeenCalledTimes(1);
  });

  it('opens the log viewer for the clicked job', async () => {
    listJobs.mockResolvedValue([job({ status: 'failed' })]);
    getJob.mockResolvedValue({
      ...job({ status: 'failed' }),
      log_tail: 'traceback goes here',
    });

    render(<JobStatusPoller refId="g-1" />);
    await userEvent.click(await screen.findByRole('button', { name: 'log' }));

    expect(await screen.findByRole('dialog', { name: 'Job log' })).toBeTruthy();
    expect(await screen.findByText('traceback goes here')).toBeTruthy();
  });
});
