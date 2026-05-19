export type PatchEncoder = 'uni_v1' | 'uni_v2' | 'phikon' | 'phikon_v2';

export interface FsEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size: number | null;
  mtime: string | null;
}

export interface FsListResponse {
  path: string;
  parent: string | null;
  entries: FsEntry[];
  is_root: boolean;
}

export interface FsRootsResponse {
  roots: string[];
}

export interface TridentRunResponse {
  id: string;
  created_at: string;
  dataset_name: string;
  wsi_dir: string;
  patch_encoder: PatchEncoder;
  mag: number;
  patch_size: number;
  command: string;
  status: 'pending' | 'running' | 'succeeded' | 'failed';
  stdout: string;
  stderr: string;
  output_dir: string;
  return_code: number | null;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {
      // ignore parse errors; fall back to statusText
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export function getRoots(): Promise<FsRootsResponse> {
  return request('/api/fs/roots');
}

export function listDirectory(opts: {
  path?: string;
  dirsOnly?: boolean;
  showHidden?: boolean;
}): Promise<FsListResponse> {
  const params = new URLSearchParams();
  if (opts.path) params.set('path', opts.path);
  if (opts.dirsOnly) params.set('filter', 'dirs_only');
  if (opts.showHidden) params.set('show_hidden', 'true');
  const qs = params.toString();
  return request(`/api/fs/list${qs ? `?${qs}` : ''}`);
}

export function startTridentRun(payload: {
  dataset_name: string;
  wsi_dir: string;
  patch_encoder: PatchEncoder;
}): Promise<TridentRunResponse> {
  return request('/api/trident/run', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

// --- PANTHER --------------------------------------------------------------

export type PantherMode = 'faiss' | 'kmeans';

export interface PantherRunPayload {
  dataset_name: string;
  features_dir: string;
  source_csv: string;
  train_pct: number;
  val_pct: number;
  test_pct: number;
  n_chunks: number;
  mode: PantherMode;
  in_dim: number;
  n_proto_patches: number;
  n_proto: number;
  n_init: number;
  seed: number;
  num_workers: number;
}

export interface SplitCounts {
  train: number;
  val: number;
  test: number;
  unused: number;
  total: number;
}

export interface PantherRunResponse {
  id: string;
  created_at: string;
  dataset_name: string;
  features_dir: string;
  source_csv: string;
  train_pct: number;
  val_pct: number;
  test_pct: number;
  n_chunks: number;
  mode: PantherMode;
  in_dim: number;
  n_proto_patches: number;
  n_proto: number;
  n_init: number;
  seed: number;
  num_workers: number;
  command: string;
  status: 'pending' | 'running' | 'succeeded' | 'failed';
  stdout: string;
  stderr: string;
  return_code: number | null;
  split_counts: SplitCounts;
}

export function startPantherRun(payload: PantherRunPayload): Promise<PantherRunResponse> {
  return request('/api/panther/run', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getCsvRowCount(path: string): Promise<{ rows: number }> {
  const params = new URLSearchParams({ path });
  return request(`/api/fs/csv-count?${params.toString()}`);
}
