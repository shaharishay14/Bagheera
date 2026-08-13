/**
 * The encoder dropdown and its patch-size mapping. `patchSizeFor` mirrors the
 * backend's ENCODER_PATCH_SIZE table — a drift here silently produces feature
 * directories the server can't find.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import EncoderSelect, { patchSizeFor } from './EncoderSelect';
import type { PatchEncoder } from '../lib/api';

afterEach(cleanup);

const ENCODERS: PatchEncoder[] = ['uni_v1', 'uni_v2', 'phikon', 'phikon_v2'];

describe('EncoderSelect', () => {
  it('offers every supported encoder', () => {
    render(<EncoderSelect value="uni_v1" onChange={vi.fn()} />);
    const options = screen.getAllByRole('option').map((o) => o.textContent);
    expect(options).toEqual(ENCODERS);
  });

  it('reflects the controlled value', () => {
    render(<EncoderSelect value="phikon" onChange={vi.fn()} />);
    expect((screen.getByRole('combobox') as HTMLSelectElement).value).toBe('phikon');
  });

  it('reports the newly picked encoder', async () => {
    const onChange = vi.fn();
    render(<EncoderSelect value="uni_v1" onChange={onChange} />);
    await userEvent.selectOptions(screen.getByRole('combobox'), 'phikon_v2');
    expect(onChange).toHaveBeenCalledWith('phikon_v2');
  });

  it('does not own its state — the value only changes via the parent', async () => {
    render(<EncoderSelect value="uni_v1" onChange={vi.fn()} />);
    const select = screen.getByRole('combobox') as HTMLSelectElement;
    await userEvent.selectOptions(select, 'phikon');
    expect(select.value).toBe('uni_v1');
  });

  it('wires the id through for label association', () => {
    render(
      <>
        <label htmlFor="enc">Encoder</label>
        <EncoderSelect id="enc" value="uni_v1" onChange={vi.fn()} />
      </>,
    );
    expect(screen.getByLabelText('Encoder')).toBeTruthy();
  });

  it('renders monospaced, matching the other path/param inputs', () => {
    render(<EncoderSelect value="uni_v1" onChange={vi.fn()} />);
    expect(screen.getByRole('combobox').className).toContain('font-mono');
  });
});

describe('patchSizeFor', () => {
  it.each([
    ['uni_v1', 256],
    ['uni_v2', 256],
    ['phikon', 224],
    ['phikon_v2', 224],
  ] as const)('maps %s to %d px', (encoder, size) => {
    expect(patchSizeFor(encoder)).toBe(size);
  });

  it('covers every encoder the dropdown can produce', () => {
    for (const encoder of ENCODERS) {
      expect([224, 256]).toContain(patchSizeFor(encoder));
    }
  });
});
