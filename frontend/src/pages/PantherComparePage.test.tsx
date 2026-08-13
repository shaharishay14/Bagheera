import { describe, it, expect } from 'vitest';
import { compareGridClass } from './PantherComparePage';

describe('compareGridClass', () => {
  it('lays 1 model in a single column', () => {
    const cls = compareGridClass(1);
    expect(cls).toContain('grid-cols-1');
    expect(cls).not.toContain('lg:grid-cols-');
  });

  it('lays 2 models in a 2-wide row', () => {
    expect(compareGridClass(2)).toContain('lg:grid-cols-2');
  });

  it('lays 3 models in a 3-wide row', () => {
    expect(compareGridClass(3)).toContain('lg:grid-cols-3');
  });

  it('wraps 4 models into a 2×2 grid', () => {
    const cls = compareGridClass(4);
    expect(cls).toContain('lg:grid-cols-2');
    expect(cls).not.toContain('lg:grid-cols-3');
    expect(cls).not.toContain('lg:grid-cols-4');
  });

  it('caps at the 2×2 grid for any overflow count', () => {
    expect(compareGridClass(5)).toContain('lg:grid-cols-2');
  });
});
