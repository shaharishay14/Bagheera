/**
 * The job-log modal: fetch on open, keep polling only while the job is live,
 * and close on Escape / backdrop without swallowing clicks inside the panel.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import JobLogViewer from './JobLogViewer';
import { ApiError, type JobDetail } from '../lib/api';

const getJob = vi.fn();

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api');
  return { ...actual, getJob: (...a: unknown[]) => getJob(...a) };
});

function detail(overrides: Partial<JobDetail> = {}): JobDetail {
  return {
    id: 'job-1',
    job_type: 'panther_train',
    status: 'running',
    ref_table: 'model_groups',
    ref_id: 'g-1',
    queue_position: null,
    created_at: '2026-01-01T00:00:00Z',
    started_at: '2026-01-01T00:00:01Z',
    finished_at: null,
    error_message: null,
    log_tail: 'fold 0 starting…',
    ...overrides,
  } as JobDetail;
}

/**
 * Lazy rejection. `mockRejectedValue` builds the rejected promise up front,
 * which registers as an unhandled rejection before the component consumes it.
 */
function rejectsWith(error: Error) {
  getJob.mockImplementation(() => Promise.reject(error));
}

// Block body on purpose: `mockReset()` returns the mock, and a hook that
// returns a function has that function invoked as its teardown.
beforeEach(() => {
  getJob.mockReset();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('JobLogViewer', () => {
  it('shows a loading line before the first response', async () => {
    // Held open deliberately, then released — a promise that never settles
    // keeps the jsdom environment alive past teardown.
    let release!: (value: JobDetail) => void;
    getJob.mockReturnValue(
      new Promise<JobDetail>((resolve) => {
        release = resolve;
      }),
    );

    render(<JobLogViewer jobId="job-1" onClose={vi.fn()} />);
    expect(screen.getByText('Loading log…')).toBeTruthy();

    await act(async () => {
      release(detail({ status: 'succeeded' }));
    });
    expect(screen.queryByText('Loading log…')).toBeNull();
  });

  it('fetches the requested job and renders its log tail', async () => {
    getJob.mockResolvedValue(detail());
    render(<JobLogViewer jobId="job-1" onClose={vi.fn()} />);
    expect(await screen.findByText('fold 0 starting…')).toBeTruthy();
    expect(getJob).toHaveBeenCalledWith('job-1');
  });

  it('renders the status pill and job type in the header', async () => {
    getJob.mockResolvedValue(detail({ status: 'failed', job_type: 'inference' }));
    render(<JobLogViewer jobId="job-1" onClose={vi.fn()} />);
    expect(await screen.findByText('failed')).toBeTruthy();
    expect(screen.getByText('inference · job-1')).toBeTruthy();
  });

  it('shows placeholder copy when the log is still empty', async () => {
    getJob.mockResolvedValue(detail({ log_tail: '' }));
    render(<JobLogViewer jobId="job-1" onClose={vi.fn()} />);
    expect(await screen.findByText('(no log output yet)')).toBeTruthy();
  });

  it('shows the error_message footer for a failed job', async () => {
    getJob.mockResolvedValue(
      detail({ status: 'failed', error_message: 'CUDA out of memory' }),
    );
    render(<JobLogViewer jobId="job-1" onClose={vi.fn()} />);
    expect(await screen.findByText('CUDA out of memory')).toBeTruthy();
  });

  it('omits the footer when there is no error message', async () => {
    getJob.mockResolvedValue(detail({ status: 'succeeded' }));
    render(<JobLogViewer jobId="job-1" onClose={vi.fn()} />);
    await screen.findByText('fold 0 starting…');
    expect(screen.queryByText(/error_message/)).toBeNull();
  });

  it.each(['queued', 'running'])('keeps polling while the job is %s', async (status) => {
    vi.useFakeTimers();
    getJob.mockResolvedValue(detail({ status: status as JobDetail['status'] }));
    render(<JobLogViewer jobId="job-1" onClose={vi.fn()} />);
    await act(async () => {});
    expect(getJob).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    expect(getJob).toHaveBeenCalledTimes(2);
  });

  it.each(['succeeded', 'failed', 'canceled'])(
    'stops polling once the job is %s',
    async (status) => {
      vi.useFakeTimers();
      getJob.mockResolvedValue(detail({ status: status as JobDetail['status'] }));
      render(<JobLogViewer jobId="job-1" onClose={vi.fn()} />);
      await act(async () => {});

      await act(async () => {
        vi.advanceTimersByTime(10_000);
      });
      expect(getJob).toHaveBeenCalledTimes(1);
    },
  );

  it('shows the API error and retries on a slower cadence', async () => {
    vi.useFakeTimers();
    rejectsWith(new ApiError(404, 'Job not found.'));
    render(<JobLogViewer jobId="job-1" onClose={vi.fn()} />);
    await act(async () => {});
    expect(screen.getByText('Job not found.')).toBeTruthy();

    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    expect(getJob).toHaveBeenCalledTimes(1); // retry is 4s, not 2s

    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    expect(getJob).toHaveBeenCalledTimes(2);
  });

  it('falls back to a generic message for a non-API failure', async () => {
    rejectsWith(new TypeError('offline'));
    render(<JobLogViewer jobId="job-1" onClose={vi.fn()} />);
    expect(await screen.findByText('Failed to load log.')).toBeTruthy();
  });

  it('closes on the Close button', async () => {
    getJob.mockResolvedValue(detail({ status: 'succeeded' }));
    const onClose = vi.fn();
    render(<JobLogViewer jobId="job-1" onClose={onClose} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Close ✕' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes on Escape', async () => {
    getJob.mockResolvedValue(detail({ status: 'succeeded' }));
    const onClose = vi.fn();
    render(<JobLogViewer jobId="job-1" onClose={onClose} />);
    await screen.findByText('fold 0 starting…');
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes on a backdrop click', async () => {
    getJob.mockResolvedValue(detail({ status: 'succeeded' }));
    const onClose = vi.fn();
    render(<JobLogViewer jobId="job-1" onClose={onClose} />);
    await screen.findByText('fold 0 starting…');
    fireEvent.click(screen.getByRole('presentation'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does not close when the panel itself is clicked', async () => {
    getJob.mockResolvedValue(detail({ status: 'succeeded' }));
    const onClose = vi.fn();
    render(<JobLogViewer jobId="job-1" onClose={onClose} />);
    fireEvent.click(await screen.findByRole('dialog', { name: 'Job log' }));
    expect(onClose).toHaveBeenCalledTimes(0);
  });

  it('stops polling and unbinds the key handler after unmount', async () => {
    vi.useFakeTimers();
    const onClose = vi.fn();
    getJob.mockResolvedValue(detail({ status: 'running' }));
    const { unmount } = render(<JobLogViewer jobId="job-1" onClose={onClose} />);
    await act(async () => {});
    unmount();

    await act(async () => {
      vi.advanceTimersByTime(10_000);
    });
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(getJob).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
  });
});
