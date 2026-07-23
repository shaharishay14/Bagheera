import { useState } from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { clampToRange, splitScopeKey, NumberInput } from './PantherForm';
import type { RunResolveResponse } from '../lib/api';

afterEach(cleanup);

describe('clampToRange', () => {
  it('rounds to the nearest integer', () => {
    expect(clampToRange(3.4)).toBe(3);
    expect(clampToRange(3.6)).toBe(4);
  });

  it('clamps below min and above max', () => {
    expect(clampToRange(1, 3)).toBe(3);
    expect(clampToRange(999, 0, 10)).toBe(10);
  });

  it('passes through in-range values', () => {
    expect(clampToRange(5, 0, 10)).toBe(5);
  });

  it('treats missing bounds as unbounded', () => {
    expect(clampToRange(-42)).toBe(-42);
  });
});

describe('splitScopeKey', () => {
  const make = (dataset: string): RunResolveResponse => ({
    trident_run_id: 'run-' + Math.random(),
    dataset_name: dataset,
    output_dir: '/out',
    patch_encoder: 'uni_v1',
    mag: 20,
    patch_size: 256,
    in_dim: 1024,
  });

  it('returns null when nothing is resolved', () => {
    expect(splitScopeKey(null)).toBeNull();
  });

  it('is STABLE across distinct resolved objects with the same dataset', () => {
    // Re-resolving returns a fresh object each time; the gate must not change,
    // so the dataset-scoped split effect never re-fires and the chosen split
    // is preserved when unrelated fields change.
    const a = make('tcga_brca');
    const b = make('tcga_brca');
    expect(a).not.toBe(b);
    expect(splitScopeKey(a)).toBe(splitScopeKey(b));
  });

  it('changes when the dataset actually changes', () => {
    expect(splitScopeKey(make('tcga_brca'))).not.toBe(splitScopeKey(make('tcga_luad')));
  });
});

/** Controlled harness so the NumberInput sees real prop updates on change. */
function Harness({ min, max }: { min?: number; max?: number }) {
  const [value, setValue] = useState(5);
  return (
    <div>
      <NumberInput label="Field" value={value} onChange={setValue} min={min} max={max} />
      <span data-testid="value">{value}</span>
    </div>
  );
}

describe('NumberInput blur-clamp', () => {
  it('can be cleared mid-edit without the caret fighting the user', () => {
    render(<Harness min={1} max={100} />);
    const input = screen.getByRole('spinbutton') as HTMLInputElement;
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: '' } });
    // Empty buffer is allowed while editing (does not snap back to a number).
    expect(input.value).toBe('');
  });

  it('clamps to the range only on blur', () => {
    render(<Harness min={1} max={100} />);
    const input = screen.getByRole('spinbutton') as HTMLInputElement;
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: '999' } });
    // Not clamped yet while typing.
    expect(input.value).toBe('999');
    fireEvent.blur(input);
    // Clamped to max on blur.
    expect(input.value).toBe('100');
    expect(screen.getByTestId('value').textContent).toBe('100');
  });

  it('resets an empty field to the last committed value on blur', () => {
    render(<Harness min={1} max={100} />);
    const input = screen.getByRole('spinbutton') as HTMLInputElement;
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: '' } });
    fireEvent.blur(input);
    expect(input.value).toBe('5');
  });

  it('rounds fractional input on blur', () => {
    const onChange = vi.fn();
    render(<NumberInput label="Frac" value={5} onChange={onChange} min={0} max={10} />);
    const input = screen.getByRole('spinbutton') as HTMLInputElement;
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: '7.6' } });
    fireEvent.blur(input);
    expect(onChange).toHaveBeenLastCalledWith(8);
  });
});
