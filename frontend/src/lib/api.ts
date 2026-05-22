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
  // 207 Multi-Status is a partial-success signal for K-fold runs — surface body to caller.
  if (!res.ok && res.status !== 207) {
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
export type ModelStatus = 'pending' | 'running' | 'ready' | 'failed';

export interface FoldCounts {
  train: number;
  val: number;
  test: number;
}

export interface SplitInfo {
  id: string;
  created_at: string;
  dataset_name: string;
  split_name: string;
  abs_path: string;
  source_csv: string;
  k: number;
  seed: number;
  total_rows: number;
  per_fold_counts: FoldCounts[];
}

export interface ModelInfo {
  id: string;
  created_at: string;
  base_name: string;
  model_name: string;
  group_id: string;
  fold_index: number;
  fold_k: number;
  dataset_name: string;
  features_dir: string;
  split_id: string;
  split_name: string;
  mode: PantherMode;
  in_dim: number;
  n_proto_patches: number;
  n_proto: number;
  n_init: number;
  seed: number;
  num_workers: number;
  status: ModelStatus;
  prototypes_dir: string;
  prototype_files: string[];
}

export interface FoldOutcome {
  fold_index: number;
  model_id: string;
  model_name: string;
  status: ModelStatus;
  prototypes_dir: string;
  prototype_files: string[];
  return_code: number | null;
  stderr_tail: string;
}

export interface KFoldRunSummary {
  total: number;
  succeeded: number;
  failed: number;
}

export interface PantherKFoldRunResponse {
  group_id: string;
  split_id: string;
  split_name: string;
  k: number;
  models: FoldOutcome[];
  summary: KFoldRunSummary;
}

export interface PantherKFoldRunPayload {
  model_name: string;
  features_dir: string;
  dataset_name: string;
  // Either reference an existing split:
  split_name?: string;
  // Or create one inline (requires source_csv + k + split_seed):
  source_csv?: string;
  k?: number;
  split_seed?: number;
  // PANTHER hyperparameters (seed = --seed, independent of split_seed):
  mode: PantherMode;
  in_dim: number;
  n_proto_patches: number;
  n_proto: number;
  n_init: number;
  seed: number;
  num_workers: number;
}

export function startPantherRun(payload: PantherKFoldRunPayload): Promise<PantherKFoldRunResponse> {
  return request('/api/panther/run', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function listSplits(datasetName?: string): Promise<SplitInfo[]> {
  const qs = datasetName ? `?dataset_name=${encodeURIComponent(datasetName)}` : '';
  return request(`/api/panther/splits${qs}`);
}

export function createSplit(payload: {
  dataset_name: string;
  source_csv: string;
  k: number;
  seed: number;
}): Promise<SplitInfo> {
  return request('/api/panther/splits', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function listModels(opts?: { groupId?: string; datasetName?: string }): Promise<ModelInfo[]> {
  const params = new URLSearchParams();
  if (opts?.groupId) params.set('group_id', opts.groupId);
  if (opts?.datasetName) params.set('dataset_name', opts.datasetName);
  const qs = params.toString();
  return request(`/api/panther/models${qs ? `?${qs}` : ''}`);
}

export function getCsvRowCount(path: string): Promise<{ rows: number }> {
  const params = new URLSearchParams({ path });
  return request(`/api/fs/csv-count?${params.toString()}`);
}
