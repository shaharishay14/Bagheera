import { describe, it, expect } from 'vitest';
import { normalizedClick } from './ZoomPanImage';

const rect = { left: 100, top: 50 };
const imgW = 400;
const imgH = 300;

describe('normalizedClick', () => {
  it('maps a click at the identity transform to its natural fraction', () => {
    // Click 100px into the image horizontally (200px in viewport - 100 left).
    const { fx, fy } = normalizedClick(rect, { scale: 1, tx: 0, ty: 0 }, imgW, imgH, 200, 200);
    expect(fx).toBeCloseTo(100 / imgW); // 0.25
    expect(fy).toBeCloseTo(150 / imgH); // 0.5
  });

  it('centers map to (0.5, 0.5) at identity', () => {
    const { fx, fy } = normalizedClick(
      rect,
      { scale: 1, tx: 0, ty: 0 },
      imgW,
      imgH,
      rect.left + imgW / 2,
      rect.top + imgH / 2,
    );
    expect(fx).toBeCloseTo(0.5);
    expect(fy).toBeCloseTo(0.5);
  });

  it('inverts pan and zoom to recover natural coords', () => {
    // Content point at natural (fx=0.25, fy=0.5) → (100, 150) at scale 1.
    // Under scale 2 + translate (tx=-50, ty=-30), screen = 100 + tx + cx*scale.
    const tf = { scale: 2, tx: -50, ty: -30 };
    const cx = 0.25 * imgW; // 100
    const cy = 0.5 * imgH; // 150
    const clientX = rect.left + tf.tx + cx * tf.scale; // 100 - 50 + 200 = 250
    const clientY = rect.top + tf.ty + cy * tf.scale; // 50 - 30 + 300 = 320
    const { fx, fy } = normalizedClick(rect, tf, imgW, imgH, clientX, clientY);
    expect(fx).toBeCloseTo(0.25);
    expect(fy).toBeCloseTo(0.5);
  });

  it('clamps a click past the left/top edge to 0', () => {
    const { fx, fy } = normalizedClick(rect, { scale: 1, tx: 0, ty: 0 }, imgW, imgH, 0, 0);
    expect(fx).toBe(0);
    expect(fy).toBe(0);
  });

  it('clamps a click past the right/bottom edge to 1', () => {
    const { fx, fy } = normalizedClick(rect, { scale: 1, tx: 0, ty: 0 }, imgW, imgH, 9999, 9999);
    expect(fx).toBe(1);
    expect(fy).toBe(1);
  });
});
