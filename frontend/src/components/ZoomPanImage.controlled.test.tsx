import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import ZoomPanImage, { type Transform } from './ZoomPanImage';

afterEach(cleanup);

const IDENTITY: Transform = { scale: 1, tx: 0, ty: 0 };

describe('ZoomPanImage controlled vs uncontrolled transform', () => {
  it('reports through onTransformChange (and does NOT own state) when controlled', () => {
    const onChange = vi.fn();
    render(
      <ZoomPanImage src="/x.png" alt="x" transform={IDENTITY} onTransformChange={onChange} />,
    );

    fireEvent.click(screen.getByLabelText('Zoom in'));

    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as Transform;
    expect(next.scale).toBeGreaterThan(1);
    // Controlled: the parent drives the prop, so nothing flowed back here — the
    // internal zoom badge (rendered from local state) must stay absent.
    expect(screen.queryByText(/×$/)).toBeNull();
  });

  it('owns internal state (renders the zoom badge) when uncontrolled', () => {
    render(<ZoomPanImage src="/x.png" alt="x" />);

    // No badge at rest (scale 1).
    expect(screen.queryByText(/×$/)).toBeNull();

    fireEvent.click(screen.getByLabelText('Zoom in'));

    // Internal state updated → the scale badge appears (1.4× for BUTTON_STEP).
    expect(screen.getByText(/×$/).textContent).toBe('1.4×');
  });
});
