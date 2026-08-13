/**
 * The FE↔BE contract in `lib/api.ts`: the shared `request` wrapper's error
 * handling, URL construction, and the viz-path resolution every image goes
 * through. `fetch` is stubbed — no network, no backend.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  cancelJob,
  createInferences,
  createSingleSplit,
  getQueue,
  getRoots,
  listDirectory,
  listJobs,
  listModelGroups,
  lookupInference,
  reorderQueue,
  resolveVizUrl,
  vizFileUrl,
  vizPlaceholderUrl,
} from './api';

const fetchMock = vi.fn();

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: 'Status Text',
    json: async () => body,
  } as unknown as Response;
}

function errorResponse(status: number, body: unknown, statusText = 'Bad Request') {
  return {
    ok: false,
    status,
    statusText,
    json: async () => body,
  } as unknown as Response;
}

/** URL of the single fetch the call under test made. */
function calledUrl(): string {
  return fetchMock.mock.calls[0][0] as string;
}

function calledInit(): RequestInit {
  return (fetchMock.mock.calls[0][1] ?? {}) as RequestInit;
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// --- request wrapper ------------------------------------------------------

describe('request wrapper', () => {
  it('sends JSON content-type by default', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ roots: [] }));
    await getRoots();
    expect((calledInit().headers as Record<string, string>)['Content-Type']).toBe(
      'application/json',
    );
  });

  it('returns the parsed body on success', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ roots: ['/data'] }));
    await expect(getRoots()).resolves.toEqual({ roots: ['/data'] });
  });

  it('throws ApiError carrying the HTTP status', async () => {
    fetchMock.mockResolvedValue(errorResponse(403, { detail: 'Path is outside the allowed roots.' }));
    await expect(getRoots()).rejects.toBeInstanceOf(ApiError);
    fetchMock.mockResolvedValue(errorResponse(403, { detail: 'nope' }));
    await expect(getRoots()).rejects.toMatchObject({ status: 403 });
  });

  it("surfaces FastAPI's detail string as the message", async () => {
    fetchMock.mockResolvedValue(errorResponse(400, { detail: 'source_csv must be an existing file.' }));
    await expect(getRoots()).rejects.toThrow('source_csv must be an existing file.');
  });

  it('stringifies a structured validation detail', async () => {
    const detail = [{ loc: ['body', 'k'], msg: 'must be >= 2' }];
    fetchMock.mockResolvedValue(errorResponse(422, { detail }));
    await expect(getRoots()).rejects.toThrow(JSON.stringify(detail));
  });

  it('falls back to statusText when the body has no detail', async () => {
    fetchMock.mockResolvedValue(errorResponse(500, {}, 'Internal Server Error'));
    await expect(getRoots()).rejects.toThrow('Internal Server Error');
  });

  it('falls back to statusText when the body is not JSON', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 502,
      statusText: 'Bad Gateway',
      json: async () => {
        throw new SyntaxError('Unexpected token <');
      },
    } as unknown as Response);
    await expect(getRoots()).rejects.toThrow('Bad Gateway');
  });

  it('treats 207 Multi-Status as success so partial results reach the caller', async () => {
    const body = { batch_id: null, inferences: [{ status: 'rejected' }, { status: 'queued' }] };
    fetchMock.mockResolvedValue({
      ok: false,
      status: 207,
      statusText: 'Multi-Status',
      json: async () => body,
    } as unknown as Response);
    await expect(
      createInferences({ model_id: 'm', wsi_paths: ['/a', '/b'] }),
    ).resolves.toEqual(body);
  });
});

// --- request construction -------------------------------------------------

describe('request construction', () => {
  it('omits optional query params that were not provided', async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));
    await listJobs();
    expect(calledUrl()).toBe('/api/jobs');
  });

  it('serializes every provided job filter', async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));
    await listJobs({ status: 'queued', refTable: 'models', refId: 'm-1', limit: 25 });
    const url = calledUrl();
    expect(url).toContain('status=queued');
    expect(url).toContain('ref_table=models');
    expect(url).toContain('ref_id=m-1');
    expect(url).toContain('limit=25');
  });

  it('encodes a path with spaces into the query string', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ path: '/', entries: [], is_root: true, parent: null }));
    await listDirectory({ path: '/data/my slides' });
    expect(calledUrl()).toContain('path=%2Fdata%2Fmy+slides');
  });

  it('POSTs a JSON body for split creation', async () => {
    fetchMock.mockResolvedValue(jsonResponse({}));
    await createSingleSplit({ dataset_name: 'brca', source_csv: '/data/c.csv', seed: 1 });
    const init = calledInit();
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({
      dataset_name: 'brca',
      source_csv: '/data/c.csv',
      kind: 'single',
      seed: 1,
    });
  });

  it('createSingleSplit sends kind=single with no k', async () => {
    // One model is trained on the whole cohort, so the split needs no size.
    fetchMock.mockResolvedValue(jsonResponse({}));
    await createSingleSplit({ dataset_name: 'brca', source_csv: '/data/c.csv', seed: 1 });
    const body = JSON.parse(calledInit().body as string);
    expect(body.kind).toBe('single');
    expect(body.k).toBeUndefined();
  });

  it('POSTs the ordered id list when reordering the queue', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ running: null, waiting: [], recent: [] }));
    await reorderQueue(['b', 'a']);
    expect(calledUrl()).toBe('/api/queue/reorder');
    expect(JSON.parse(calledInit().body as string)).toEqual({ ordered_job_ids: ['b', 'a'] });
  });

  it('POSTs with no body when canceling a job', async () => {
    fetchMock.mockResolvedValue(jsonResponse({}));
    await cancelJob('job-1');
    expect(calledUrl()).toBe('/api/jobs/job-1/cancel');
    expect(calledInit().method).toBe('POST');
  });

  it('hits the queue endpoint without query params', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ running: null, waiting: [], recent: [] }));
    await getQueue();
    expect(calledUrl()).toBe('/api/queue');
  });

  it('serializes the model-group browser filters', async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));
    await listModelGroups({ favoriteOnly: true, datasetName: 'brca', q: 'run', sort: 'name' });
    const url = calledUrl();
    expect(url).toContain('favorite_only=true');
    expect(url).toContain('dataset_name=brca');
    expect(url).toContain('q=run');
    expect(url).toContain('sort=name');
  });

  it('turns a 404 cache lookup into null rather than an error', async () => {
    fetchMock.mockResolvedValue(errorResponse(404, { detail: 'No cached inference.' }));
    await expect(lookupInference('m-1', '/data/slide.svs')).resolves.toBeNull();
  });

  it('still propagates non-404 lookup failures', async () => {
    fetchMock.mockResolvedValue(errorResponse(400, { detail: 'bad path' }));
    await expect(lookupInference('m-1', '/x')).rejects.toBeInstanceOf(ApiError);
  });
});

// --- viz URL helpers ------------------------------------------------------

describe('vizPlaceholderUrl', () => {
  it('builds a bare placeholder URL when no options are given', () => {
    expect(vizPlaceholderUrl('heatmap')).toBe('/api/viz/placeholder/heatmap');
  });

  it('appends the label, width and height when supplied', () => {
    const url = vizPlaceholderUrl('umap', { label: 'Fold 1', width: 800, height: 600 });
    expect(url).toContain('label=Fold+1');
    expect(url).toContain('width=800');
    expect(url).toContain('height=600');
  });

  it('encodes a label containing reserved characters', () => {
    expect(vizPlaceholderUrl('topk', { label: 'a&b=c' })).toContain('label=a%26b%3Dc');
  });
});

describe('vizFileUrl', () => {
  it('prefixes a disk path with the viz route', () => {
    expect(vizFileUrl('/viz_cache/m1/umap.png')).toBe('/api/viz//viz_cache/m1/umap.png');
  });

  it('encodes each segment while preserving the separators', () => {
    expect(vizFileUrl('m 1/fold 0/umap.png')).toBe('/api/viz/m%201/fold%200/umap.png');
  });
});

describe('resolveVizUrl', () => {
  const fallback = () => '/api/viz/placeholder/heatmap';

  it('falls back when the stored path is null', () => {
    expect(resolveVizUrl(null, fallback)).toBe('/api/viz/placeholder/heatmap');
  });

  it('falls back when the stored path is undefined', () => {
    expect(resolveVizUrl(undefined, fallback)).toBe('/api/viz/placeholder/heatmap');
  });

  it('falls back on an empty string rather than building /api/viz/', () => {
    expect(resolveVizUrl('', fallback)).toBe('/api/viz/placeholder/heatmap');
  });

  it('passes an already-routed /api/viz/ URL through untouched', () => {
    expect(resolveVizUrl('/api/viz/placeholder/umap?label=x', fallback)).toBe(
      '/api/viz/placeholder/umap?label=x',
    );
  });

  it.each(['http://cdn.example/x.png', 'https://cdn.example/x.png'])(
    'passes the absolute URL %s through untouched',
    (url) => {
      expect(resolveVizUrl(url, fallback)).toBe(url);
    },
  );

  it('wraps a bare disk path with vizFileUrl', () => {
    expect(resolveVizUrl('/viz_cache/m1/umap.png', fallback)).toBe(
      vizFileUrl('/viz_cache/m1/umap.png'),
    );
  });

  it('only calls the fallback when there is nothing to resolve', () => {
    const spy = vi.fn(fallback);
    resolveVizUrl('/viz_cache/a.png', spy);
    expect(spy).not.toHaveBeenCalled();
    resolveVizUrl(null, spy);
    expect(spy).toHaveBeenCalledTimes(1);
  });
});
