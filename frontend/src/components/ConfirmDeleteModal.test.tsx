/**
 * The destructive-action gate. Every path that can lose data goes through this
 * modal, so the busy-lock and the 409 error surface matter as much as the copy.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ConfirmDeleteModal from './ConfirmDeleteModal';

afterEach(cleanup);

function setup(overrides: Partial<React.ComponentProps<typeof ConfirmDeleteModal>> = {}) {
  const onCancel = vi.fn();
  const onConfirm = vi.fn();
  render(
    <ConfirmDeleteModal
      open
      title="Delete model group"
      name="Breast cohort"
      onCancel={onCancel}
      onConfirm={onConfirm}
      {...overrides}
    >
      This removes all folds and their artifacts.
    </ConfirmDeleteModal>,
  );
  return { onCancel, onConfirm };
}

describe('ConfirmDeleteModal', () => {
  it('renders nothing while closed', () => {
    setup({ open: false });
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('renders a labelled modal dialog with the target name and warning', () => {
    setup();
    const dialog = screen.getByRole('dialog', { name: 'Delete model group' });
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(screen.getByText('Breast cohort')).toBeTruthy();
    expect(screen.getByText('This removes all folds and their artifacts.')).toBeTruthy();
  });

  it('confirms on the destructive button', async () => {
    const { onConfirm, onCancel } = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onCancel).not.toHaveBeenCalled();
  });

  it('cancels on the Cancel button', async () => {
    const { onCancel, onConfirm } = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('cancels on Escape', () => {
    const { onCancel } = setup();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('cancels on a backdrop click', () => {
    const { onCancel } = setup();
    fireEvent.mouseDown(screen.getByRole('presentation'));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('does not cancel when the click starts inside the dialog', () => {
    const { onCancel } = setup();
    fireEvent.mouseDown(screen.getByRole('dialog'));
    expect(onCancel).not.toHaveBeenCalled();
  });

  it('uses a custom confirm label when given', () => {
    setup({ confirmLabel: 'Delete forever' });
    expect(screen.getByRole('button', { name: 'Delete forever' })).toBeTruthy();
  });

  it('shows a blocking error such as a 409 from the server', () => {
    setup({ error: 'Cannot delete: one or more fold models are still running.' });
    expect(
      screen.getByText('Cannot delete: one or more fold models are still running.'),
    ).toBeTruthy();
  });

  it('hides the error region when there is no error', () => {
    setup();
    expect(screen.queryByText(/Cannot delete/)).toBeNull();
  });

  describe('while busy', () => {
    it('shows progress copy on the confirm button', () => {
      setup({ busy: true });
      expect(screen.getByRole('button', { name: 'Deleting…' })).toBeTruthy();
    });

    it('disables both buttons', () => {
      setup({ busy: true });
      expect(screen.getByRole('button', { name: 'Cancel' }).hasAttribute('disabled')).toBe(true);
      expect(screen.getByRole('button', { name: 'Deleting…' }).hasAttribute('disabled')).toBe(true);
    });

    it('ignores Escape so an in-flight delete is not abandoned', () => {
      const { onCancel } = setup({ busy: true });
      fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
      expect(onCancel).not.toHaveBeenCalled();
    });

    it('ignores backdrop clicks', () => {
      const { onCancel } = setup({ busy: true });
      fireEvent.mouseDown(screen.getByRole('presentation'));
      expect(onCancel).not.toHaveBeenCalled();
    });
  });

  it('moves focus into the dialog when it opens', () => {
    setup();
    expect(document.activeElement).toBe(screen.getByRole('dialog'));
  });

  it('ignores unrelated keys', () => {
    const { onCancel, onConfirm } = setup();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Enter' });
    expect(onCancel).not.toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
