/**
 * The file/directory picker every path input goes through: extension filtering,
 * keyboard navigation, single vs. multi select, and the roots dropdown.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DirectoryBrowser from './DirectoryBrowser';
import { ApiError, type FsEntry } from '../lib/api';

const getRoots = vi.fn();
const listDirectory = vi.fn();

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api');
  return {
    ...actual,
    getRoots: (...a: unknown[]) => getRoots(...a),
    listDirectory: (...a: unknown[]) => listDirectory(...a),
  };
});

const dir = (name: string, path: string): FsEntry =>
  ({ name, path, is_dir: true, size: null, mtime: null }) as FsEntry;
const file = (name: string, path: string): FsEntry =>
  ({ name, path, is_dir: false, size: 10, mtime: null }) as FsEntry;

function listing(entries: FsEntry[], overrides: Record<string, unknown> = {}) {
  return {
    path: '/data',
    parent: null,
    is_root: true,
    entries,
    ...overrides,
  };
}

beforeEach(() => {
  getRoots.mockReset();
  listDirectory.mockReset();
  getRoots.mockResolvedValue({ roots: ['/data'] });
  listDirectory.mockResolvedValue(listing([]));
  // jsdom has no layout engine; the highlight effect calls this on every move.
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
});

describe('DirectoryBrowser — visibility', () => {
  it('renders nothing while closed', () => {
    render(<DirectoryBrowser open={false} onSelect={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(getRoots).not.toHaveBeenCalled();
  });

  it('loads roots and the initial listing when opened', async () => {
    render(<DirectoryBrowser open onSelect={vi.fn()} onCancel={vi.fn()} />);
    await waitFor(() => expect(getRoots).toHaveBeenCalled());
    await waitFor(() => expect(listDirectory).toHaveBeenCalledWith({ path: '/data', dirsOnly: true }));
  });

  it('titles itself by mode', async () => {
    const { unmount } = render(<DirectoryBrowser open onSelect={vi.fn()} onCancel={vi.fn()} />);
    expect(await screen.findByRole('dialog', { name: 'Choose a directory' })).toBeTruthy();
    unmount();

    render(<DirectoryBrowser open mode="file" onSelect={vi.fn()} onCancel={vi.fn()} />);
    expect(await screen.findByRole('dialog', { name: 'Choose a file' })).toBeTruthy();
  });

  it('titles itself "Choose files" in multi-select mode', async () => {
    render(<DirectoryBrowser open mode="file" onSelectMulti={vi.fn()} onCancel={vi.fn()} />);
    expect(await screen.findByRole('dialog', { name: 'Choose files' })).toBeTruthy();
  });

  it('requests directories only in dir mode', async () => {
    render(<DirectoryBrowser open mode="dir" onSelect={vi.fn()} onCancel={vi.fn()} />);
    await waitFor(() =>
      expect(listDirectory).toHaveBeenCalledWith(expect.objectContaining({ dirsOnly: true })),
    );
  });

  it('requests files too in file mode', async () => {
    render(<DirectoryBrowser open mode="file" onSelect={vi.fn()} onCancel={vi.fn()} />);
    await waitFor(() =>
      expect(listDirectory).toHaveBeenCalledWith(expect.objectContaining({ dirsOnly: false })),
    );
  });

  it('seeds from the parent folder when initialPath points at a file', async () => {
    render(
      <DirectoryBrowser
        open
        mode="file"
        initialPath="/data/cohort/labels.csv"
        onSelect={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    await waitFor(() =>
      expect(listDirectory).toHaveBeenCalledWith({ path: '/data/cohort', dirsOnly: false }),
    );
  });

  it('seeds directly from initialPath when it is a folder', async () => {
    render(
      <DirectoryBrowser open initialPath="/data/cohort" onSelect={vi.fn()} onCancel={vi.fn()} />,
    );
    await waitFor(() =>
      expect(listDirectory).toHaveBeenCalledWith({ path: '/data/cohort', dirsOnly: true }),
    );
  });
});

describe('DirectoryBrowser — errors', () => {
  it('shows the API error when roots cannot be read', async () => {
    getRoots.mockImplementation(() =>
      Promise.reject(new ApiError(500, 'No allowed roots configured.')),
    );
    render(<DirectoryBrowser open onSelect={vi.fn()} onCancel={vi.fn()} />);
    expect(await screen.findByText('No allowed roots configured.')).toBeTruthy();
  });

  it('shows the API error when a directory cannot be listed', async () => {
    listDirectory.mockImplementation(() =>
      Promise.reject(new ApiError(403, 'Path is outside the allowed roots.')),
    );
    render(<DirectoryBrowser open onSelect={vi.fn()} onCancel={vi.fn()} />);
    expect(await screen.findByText('Path is outside the allowed roots.')).toBeTruthy();
  });

  it('falls back to a generic message for a non-API failure', async () => {
    listDirectory.mockImplementation(() => Promise.reject(new TypeError('offline')));
    render(<DirectoryBrowser open onSelect={vi.fn()} onCancel={vi.fn()} />);
    expect(await screen.findByText('Failed to load directory')).toBeTruthy();
  });
});

describe('DirectoryBrowser — extension filtering', () => {
  it('hides files whose extension is not allowed', async () => {
    listDirectory.mockResolvedValue(
      listing([file('a.csv', '/data/a.csv'), file('b.txt', '/data/b.txt')]),
    );
    render(
      <DirectoryBrowser open mode="file" extensions={['.csv']} onSelect={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(await screen.findByText('a.csv')).toBeTruthy();
    expect(screen.queryByText('b.txt')).toBeNull();
  });

  it('always keeps directories visible so the user can keep navigating', async () => {
    listDirectory.mockResolvedValue(
      listing([dir('nested', '/data/nested'), file('b.txt', '/data/b.txt')]),
    );
    render(
      <DirectoryBrowser open mode="file" extensions={['.csv']} onSelect={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(await screen.findByText('nested')).toBeTruthy();
  });

  it('accepts extensions with or without a leading dot, case-insensitively', async () => {
    listDirectory.mockResolvedValue(
      listing([file('A.SVS', '/data/A.SVS'), file('b.tif', '/data/b.tif')]),
    );
    render(
      <DirectoryBrowser
        open
        mode="file"
        extensions={['svs', '.TIF']}
        onSelect={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(await screen.findByText('A.SVS')).toBeTruthy();
    expect(screen.getByText('b.tif')).toBeTruthy();
  });

  it('shows every file when no extension filter is given', async () => {
    listDirectory.mockResolvedValue(
      listing([file('a.csv', '/data/a.csv'), file('b.txt', '/data/b.txt')]),
    );
    render(<DirectoryBrowser open mode="file" onSelect={vi.fn()} onCancel={vi.fn()} />);
    expect(await screen.findByText('a.csv')).toBeTruthy();
    expect(screen.getByText('b.txt')).toBeTruthy();
  });

  it('hides an extensionless file when a filter is active', async () => {
    listDirectory.mockResolvedValue(listing([file('README', '/data/README')]));
    render(
      <DirectoryBrowser open mode="file" extensions={['.csv']} onSelect={vi.fn()} onCancel={vi.fn()} />,
    );
    await waitFor(() => expect(listDirectory).toHaveBeenCalled());
    expect(screen.queryByText('README')).toBeNull();
  });
});

describe('DirectoryBrowser — selecting', () => {
  it('returns the current directory in dir mode', async () => {
    const onSelect = vi.fn();
    listDirectory.mockResolvedValue(listing([dir('nested', '/data/nested')]));
    render(<DirectoryBrowser open onSelect={onSelect} onCancel={vi.fn()} />);

    await userEvent.click(await screen.findByRole('button', { name: 'Select this folder' }));
    expect(onSelect).toHaveBeenCalledWith('/data');
  });

  it('returns the highlighted file in file mode', async () => {
    const onSelect = vi.fn();
    listDirectory.mockResolvedValue(listing([file('a.csv', '/data/a.csv')]));
    render(<DirectoryBrowser open mode="file" onSelect={onSelect} onCancel={vi.fn()} />);

    await userEvent.click(await screen.findByRole('button', { name: 'Select this file' }));
    expect(onSelect).toHaveBeenCalledWith('/data/a.csv');
  });

  it('disables confirm in file mode while a directory is highlighted', async () => {
    listDirectory.mockResolvedValue(listing([dir('nested', '/data/nested')]));
    render(<DirectoryBrowser open mode="file" onSelect={vi.fn()} onCancel={vi.fn()} />);

    const confirm = await screen.findByRole('button', { name: 'Select this file' });
    expect(confirm.hasAttribute('disabled')).toBe(true);
  });

  it('counts the selection in the multi-select button label', async () => {
    const onSelectMulti = vi.fn();
    listDirectory.mockResolvedValue(
      listing([file('a.svs', '/data/a.svs'), file('b.svs', '/data/b.svs')]),
    );
    render(<DirectoryBrowser open mode="file" onSelectMulti={onSelectMulti} onCancel={vi.fn()} />);

    const dialog = await screen.findByRole('dialog');
    expect(screen.getByRole('button', { name: 'Select 0 files' })).toBeTruthy();

    fireEvent.keyDown(dialog, { key: ' ' });
    expect(await screen.findByRole('button', { name: 'Select 1 file' })).toBeTruthy();

    fireEvent.keyDown(dialog, { key: 'ArrowDown' });
    fireEvent.keyDown(dialog, { key: ' ' });
    expect(await screen.findByRole('button', { name: 'Select 2 files' })).toBeTruthy();
  });

  it('returns the multi-selection sorted', async () => {
    const onSelectMulti = vi.fn();
    listDirectory.mockResolvedValue(
      listing([file('b.svs', '/data/b.svs'), file('a.svs', '/data/a.svs')]),
    );
    render(<DirectoryBrowser open mode="file" onSelectMulti={onSelectMulti} onCancel={vi.fn()} />);

    const dialog = await screen.findByRole('dialog');
    fireEvent.keyDown(dialog, { key: ' ' });
    fireEvent.keyDown(dialog, { key: 'ArrowDown' });
    fireEvent.keyDown(dialog, { key: ' ' });
    await userEvent.click(screen.getByRole('button', { name: 'Select 2 files' }));

    expect(onSelectMulti).toHaveBeenCalledWith(['/data/a.svs', '/data/b.svs']);
  });

  it('space toggles a file off again', async () => {
    listDirectory.mockResolvedValue(listing([file('a.svs', '/data/a.svs')]));
    render(<DirectoryBrowser open mode="file" onSelectMulti={vi.fn()} onCancel={vi.fn()} />);

    const dialog = await screen.findByRole('dialog');
    fireEvent.keyDown(dialog, { key: ' ' });
    expect(await screen.findByRole('button', { name: 'Select 1 file' })).toBeTruthy();
    fireEvent.keyDown(dialog, { key: ' ' });
    expect(await screen.findByRole('button', { name: 'Select 0 files' })).toBeTruthy();
  });

  it('disables the multi confirm until something is picked', async () => {
    listDirectory.mockResolvedValue(listing([file('a.svs', '/data/a.svs')]));
    render(<DirectoryBrowser open mode="file" onSelectMulti={vi.fn()} onCancel={vi.fn()} />);
    const confirm = await screen.findByRole('button', { name: 'Select 0 files' });
    expect(confirm.hasAttribute('disabled')).toBe(true);
  });
});

describe('DirectoryBrowser — keyboard navigation', () => {
  it('cancels on Escape', async () => {
    const onCancel = vi.fn();
    render(<DirectoryBrowser open onSelect={vi.fn()} onCancel={onCancel} />);
    fireEvent.keyDown(await screen.findByRole('dialog'), { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('cancels on a backdrop click', async () => {
    const onCancel = vi.fn();
    render(<DirectoryBrowser open onSelect={vi.fn()} onCancel={onCancel} />);
    fireEvent.mouseDown(await screen.findByRole('presentation'));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('descends into the highlighted directory on ArrowRight', async () => {
    listDirectory.mockResolvedValue(listing([dir('nested', '/data/nested')]));
    render(<DirectoryBrowser open onSelect={vi.fn()} onCancel={vi.fn()} />);

    fireEvent.keyDown(await screen.findByRole('dialog'), { key: 'ArrowRight' });
    await waitFor(() =>
      expect(listDirectory).toHaveBeenCalledWith({ path: '/data/nested', dirsOnly: true }),
    );
  });

  it('descends into the highlighted directory on Enter in file mode', async () => {
    listDirectory.mockResolvedValue(listing([dir('nested', '/data/nested')]));
    render(<DirectoryBrowser open mode="file" onSelect={vi.fn()} onCancel={vi.fn()} />);

    fireEvent.keyDown(await screen.findByRole('dialog'), { key: 'Enter' });
    await waitFor(() =>
      expect(listDirectory).toHaveBeenCalledWith({ path: '/data/nested', dirsOnly: false }),
    );
  });

  it('goes up to the parent on ArrowLeft when not at a root', async () => {
    listDirectory.mockResolvedValue(
      listing([], { path: '/data/nested', parent: '/data', is_root: false }),
    );
    render(<DirectoryBrowser open onSelect={vi.fn()} onCancel={vi.fn()} />);
    await waitFor(() => expect(listDirectory).toHaveBeenCalledTimes(1));

    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'ArrowLeft' });
    await waitFor(() =>
      expect(listDirectory).toHaveBeenCalledWith({ path: '/data', dirsOnly: true }),
    );
  });

  it('disables the parent button at a root', async () => {
    render(<DirectoryBrowser open onSelect={vi.fn()} onCancel={vi.fn()} />);
    const up = await screen.findByRole('button', { name: 'Go to parent directory' });
    await waitFor(() => expect(up.hasAttribute('disabled')).toBe(true));
  });

  it('confirms on Enter in dir mode', async () => {
    const onSelect = vi.fn();
    render(<DirectoryBrowser open onSelect={onSelect} onCancel={vi.fn()} />);
    await waitFor(() => expect(listDirectory).toHaveBeenCalled());

    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Enter' });
    expect(onSelect).toHaveBeenCalledWith('/data');
  });

  it('clamps the highlight at the top of the list', async () => {
    const onSelect = vi.fn();
    listDirectory.mockResolvedValue(
      listing([file('a.svs', '/data/a.svs'), file('b.svs', '/data/b.svs')]),
    );
    render(<DirectoryBrowser open mode="file" onSelect={onSelect} onCancel={vi.fn()} />);
    const dialog = await screen.findByRole('dialog');

    fireEvent.keyDown(dialog, { key: 'ArrowUp' });
    fireEvent.keyDown(dialog, { key: 'ArrowUp' });
    fireEvent.keyDown(dialog, { key: 'Enter' });
    expect(onSelect).toHaveBeenCalledWith('/data/a.svs');
  });

  it('clamps the highlight at the bottom of the list', async () => {
    const onSelect = vi.fn();
    listDirectory.mockResolvedValue(
      listing([file('a.svs', '/data/a.svs'), file('b.svs', '/data/b.svs')]),
    );
    render(<DirectoryBrowser open mode="file" onSelect={onSelect} onCancel={vi.fn()} />);
    const dialog = await screen.findByRole('dialog');

    fireEvent.keyDown(dialog, { key: 'ArrowDown' });
    fireEvent.keyDown(dialog, { key: 'ArrowDown' });
    fireEvent.keyDown(dialog, { key: 'ArrowDown' });
    fireEvent.keyDown(dialog, { key: 'Enter' });
    expect(onSelect).toHaveBeenCalledWith('/data/b.svs');
  });
});

describe('DirectoryBrowser — roots', () => {
  it('hides the roots dropdown when only one root is configured', async () => {
    render(<DirectoryBrowser open onSelect={vi.fn()} onCancel={vi.fn()} />);
    await waitFor(() => expect(listDirectory).toHaveBeenCalled());
    expect(screen.queryByRole('combobox')).toBeNull();
  });

  it('offers a dropdown and navigates when several roots exist', async () => {
    getRoots.mockResolvedValue({ roots: ['/data', '/scratch'] });
    render(<DirectoryBrowser open onSelect={vi.fn()} onCancel={vi.fn()} />);

    const select = await screen.findByRole('combobox');
    await userEvent.selectOptions(select, '/scratch');
    await waitFor(() =>
      expect(listDirectory).toHaveBeenCalledWith({ path: '/scratch', dirsOnly: true }),
    );
  });
});
