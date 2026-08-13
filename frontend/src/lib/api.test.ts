import { describe, it, expect } from 'vitest';
import { slideThumbnailUrl } from './api';

describe('slideThumbnailUrl', () => {
  it('encodes the slide path into the query string', () => {
    const url = slideThumbnailUrl('/data/slides/A B/slide 1.svs');
    expect(url).toBe(
      '/api/slide-thumbnail?path=%2Fdata%2Fslides%2FA+B%2Fslide+1.svs'
    );
  });

  it('omits optional params when not provided', () => {
    const url = slideThumbnailUrl('/a.tif');
    expect(url).toBe('/api/slide-thumbnail?path=%2Fa.tif');
    expect(url).not.toContain('features_dir');
    expect(url).not.toContain('max_px');
  });

  it('includes and encodes features_dir when provided', () => {
    const url = slideThumbnailUrl('/a.tif', { featuresDir: '/feat/dir x' });
    expect(url).toContain('path=%2Fa.tif');
    expect(url).toContain('features_dir=%2Ffeat%2Fdir+x');
  });

  it('includes max_px when provided', () => {
    const url = slideThumbnailUrl('/a.tif', { maxPx: 64 });
    expect(url).toContain('max_px=64');
  });

  it('includes both optional params together', () => {
    const url = slideThumbnailUrl('/a.tif', { featuresDir: '/f', maxPx: 128 });
    expect(url).toContain('features_dir=%2Ff');
    expect(url).toContain('max_px=128');
  });
});
