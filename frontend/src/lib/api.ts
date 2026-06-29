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

// --- TRIDENT run lookup ---------------------------------------------------

export interface RunResolveResponse {
  trident_run_id: string;
  dataset_name: string;
  output_dir: string;
  patch_encoder: PatchEncoder;
  mag: number;
  patch_size: number;
  /** Feature dimension derived from the encoder (uni_v2→1536, uni_v1→1024,
   *  phikon/phikon_v2→768), or null when the encoder is unknown. */
  in_dim?: number | null;
}

export function resolveFeaturesDir(featuresDir: string): Promise<RunResolveResponse> {
  const qs = new URLSearchParams({ features_dir: featuresDir });
  return request(`/api/runs/resolve?${qs.toString()}`);
}

// --- Splits ---------------------------------------------------------------

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

export function listSplits(datasetName?: string): Promise<SplitInfo[]> {
  const qs = datasetName ? `?dataset_name=${encodeURIComponent(datasetName)}` : '';
  return request(`/api/splits${qs}`);
}

export function getSplit(splitId: string): Promise<SplitInfo> {
  return request(`/api/splits/${encodeURIComponent(splitId)}`);
}

export function createSplit(payload: {
  dataset_name: string;
  source_csv: string;
  k: number;
  seed: number;
}): Promise<SplitInfo> {
  return request('/api/splits', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

// --- PANTHER --------------------------------------------------------------

export type PantherMode = 'faiss' | 'kmeans';
export type ModelStatus = 'pending' | 'running' | 'ready' | 'failed';
export type VizStatus = 'pending' | 'rendering' | 'ready' | 'failed';

/**
 * Section A of the per-fold Analysis view — mirrors the PANTHER paper's
 * per-slide figure panel for ONE representative slide. Every sub-field is a
 * viz_cache path (resolve via `resolveVizUrl`) and may be absent if that
 * individual render failed (partial success) — degrade gracefully.
 */
export interface SectionA {
  /** The slide this panel was rendered for. */
  slide_id: string;
  /** Whole-slide H&E thumbnail (with scale bar). */
  thumbnail?: string;
  /** Hi-res prototype assignment overlay across the whole slide. */
  assignment_map?: string;
  /** GMM π_c bar chart, bars colored per prototype. */
  pi_c?: string;
  /** Raw H&E of the auto-picked ROI. */
  roi_raw?: string;
  /** Same ROI tiled as prototype-colored 256px patches. */
  roi_colored?: string;
  /** [x, y, w, h] of the picked ROI in slide coordinates. */
  roi_bbox?: [number, number, number, number];
  /** Monotonic index of the current ROI pick (changes on repick → cache-busts). */
  roi_index?: number;
}

/**
 * Section D of the per-fold Analysis view — the PANTHER-paper prototype
 * "dictionary": one column per prototype, each headed `C{index+1}` in the
 * prototype's color and showing `per_proto` example patches. Every prototype is
 * present; one with no mined patches carries an empty `patches` array (still
 * render its column). Each patch entry is a viz_cache path — resolve via
 * `resolveVizUrl` and degrade to a placeholder when missing.
 */
export interface SectionD {
  /** Number of example patches rendered per prototype column. */
  per_proto: number;
  prototypes: {
    /** Zero-based prototype index (column header shows `index + 1`). */
    index: number;
    /** Per-prototype color as `#rrggbb`, matching the assignment map. */
    color: string;
    /** Viz-cache paths for this prototype's example patches (may be empty). */
    patches: string[];
  }[];
}

export interface VizArtifacts {
  section_a?: SectionA;
  section_d?: SectionD;
}

export interface ModelInfo {
  id: string;
  created_at: string;
  base_name: string;
  model_name: string;
  display_name: string;
  group_id: string;
  fold_index: number;
  fold_k: number;
  dataset_name: string;
  features_dir: string;
  trident_run_id: string | null;
  split_id: string;
  split_name: string;
  split_dir_abs: string;
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
  is_favorite: boolean;
  viz_status: VizStatus;
  preview_slide_ids: string[] | null;
  preview_heatmap_paths: string[] | null;
  topk_grid_path: string | null;
  topk_per_proto: number;
  umap_path: string | null;
  /** Per-fold paper-style figure artifacts. Null until Section A is rendered. */
  viz_artifacts?: VizArtifacts | null;
}

export interface PantherKFoldRunPayload {
  model_name: string;
  features_dir: string;
  dataset_name: string;
  split_id: string;
  mode: PantherMode;
  in_dim: number;
  n_proto_patches: number;
  n_proto: number;
  n_init: number;
  seed: number;
  num_workers: number;
}

export interface PantherKFoldStartResponse {
  group_id: string;
  job_id: string;
  k: number;
  split_id: string;
  split_name: string;
  model_ids: string[];
}

export function startPantherKFoldRun(
  payload: PantherKFoldRunPayload
): Promise<PantherKFoldStartResponse> {
  return request('/api/panther/runs', {
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

// --- Model groups + individual model detail -------------------------------

export interface ModelGroupSummary {
  total: number;
  ready: number;
  failed: number;
  running: number;
  favorited: number;
}

export interface ModelGroupListItem {
  id: string;
  created_at: string;
  display_name: string;
  dataset_name: string;
  trident_run_id: string | null;
  k: number;
  split_id: string;
  split_name: string;
  mode: PantherMode;
  n_proto: number;
  summary: ModelGroupSummary;
}

export interface ModelGroupDetail {
  group: ModelGroupListItem;
  models: ModelInfo[];
  split: SplitInfo;
}

export interface TridentParamsResponse {
  trident_run_id: string | null;
  patch_encoder: PatchEncoder | null;
  mag: number | null;
  patch_size: number | null;
  gpus: string | null;
  expected_features_dir_name: string | null;
}

export interface ShufflePreviewResponse {
  model_id: string;
  preview_slide_ids: string[];
  job_id: string | null;
}

export function listModelGroups(opts?: {
  favoriteOnly?: boolean;
  datasetName?: string;
  q?: string;
  sort?: 'created_desc' | 'created_asc' | 'name';
}): Promise<ModelGroupListItem[]> {
  const params = new URLSearchParams();
  if (opts?.favoriteOnly) params.set('favorite_only', 'true');
  if (opts?.datasetName) params.set('dataset_name', opts.datasetName);
  if (opts?.q) params.set('q', opts.q);
  if (opts?.sort) params.set('sort', opts.sort);
  const qs = params.toString();
  return request(`/api/model-groups${qs ? `?${qs}` : ''}`);
}

export function getModelGroup(groupId: string): Promise<ModelGroupDetail> {
  return request(`/api/model-groups/${encodeURIComponent(groupId)}`);
}

export function patchModelGroup(
  groupId: string,
  payload: { display_name?: string }
): Promise<ModelGroupListItem> {
  return request(`/api/model-groups/${encodeURIComponent(groupId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export interface ModelGroupDeleteResult {
  group_id: string;
  models_deleted: number;
  inferences_deleted: number;
  inference_notes_deleted: number;
  inference_batches_deleted: number;
  prototype_labels_deleted: number;
  model_notes_deleted: number;
  panther_runs_deleted: number;
  dirs_removed: string[];
}

/**
 * Permanently delete a model group and every artifact it owns (fold models,
 * prototypes, viz, inference outputs, DB records). The backend returns a
 * summary on success; throws ApiError(404) if missing, or ApiError(409) when
 * the group has a running fold or an active/queued job (message explains why).
 */
export function deleteModelGroup(groupId: string): Promise<ModelGroupDeleteResult> {
  return request(`/api/model-groups/${encodeURIComponent(groupId)}`, {
    method: 'DELETE',
  });
}

export function getModel(modelId: string): Promise<ModelInfo> {
  return request(`/api/models/${encodeURIComponent(modelId)}`);
}

export function patchModel(
  modelId: string,
  payload: { is_favorite?: boolean; display_name?: string }
): Promise<ModelInfo> {
  return request(`/api/models/${encodeURIComponent(modelId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function shuffleModelPreview(modelId: string): Promise<ShufflePreviewResponse> {
  return request(`/api/models/${encodeURIComponent(modelId)}/shuffle-preview`, {
    method: 'POST',
  });
}

export function getModelTridentParams(modelId: string): Promise<TridentParamsResponse> {
  return request(`/api/models/${encodeURIComponent(modelId)}/trident-params`);
}

/**
 * Re-pick the Section A ROI for a model and return the updated ModelInfo. The
 * new pick lands under `viz_artifacts.section_a` with a fresh `roi_index`, so
 * the `roi_raw` / `roi_colored` filenames change and the browser cache-busts.
 *
 * Throws `ApiError` with:
 *   - 404 — the model does not exist
 *   - 409 — Section A has not been rendered yet (render it first)
 *   - 422 — no valid tissue window to pick an ROI from
 */
export function repickRoi(modelId: string): Promise<ModelInfo> {
  return request(`/api/models/${encodeURIComponent(modelId)}/repick-roi`, {
    method: 'POST',
  });
}

// --- Prototype labels -----------------------------------------------------

export interface PrototypeLabelInfo {
  id: string;
  model_id: string;
  prototype_index: number;
  label: string;
  created_at: string;
  updated_at: string;
}

export function listPrototypeLabels(modelId: string): Promise<PrototypeLabelInfo[]> {
  const qs = new URLSearchParams({ model_id: modelId });
  return request(`/api/prototype-labels?${qs.toString()}`);
}

export function upsertPrototypeLabel(payload: {
  model_id: string;
  prototype_index: number;
  label: string;
}): Promise<PrototypeLabelInfo> {
  return request('/api/prototype-labels', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function deletePrototypeLabel(labelId: string): Promise<void> {
  return fetch(`/api/prototype-labels/${encodeURIComponent(labelId)}`, {
    method: 'DELETE',
  }).then(() => undefined);
}

// --- Model notes ----------------------------------------------------------

export interface ModelNoteInfo {
  id: string;
  model_id: string;
  body: string;
  created_at: string;
  updated_at: string;
}

export function listModelNotes(modelId: string): Promise<ModelNoteInfo[]> {
  const qs = new URLSearchParams({ model_id: modelId });
  return request(`/api/model-notes?${qs.toString()}`);
}

export function createModelNote(payload: {
  model_id: string;
  body: string;
}): Promise<ModelNoteInfo> {
  return request('/api/model-notes', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateModelNote(
  noteId: string,
  payload: { body: string }
): Promise<ModelNoteInfo> {
  return request(`/api/model-notes/${encodeURIComponent(noteId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteModelNote(noteId: string): Promise<void> {
  return fetch(`/api/model-notes/${encodeURIComponent(noteId)}`, {
    method: 'DELETE',
  }).then(() => undefined);
}

// --- Inferences -----------------------------------------------------------

export type InferenceStatus =
  | 'queued'
  | 'running_trident'
  | 'running_viz'
  | 'ready'
  | 'failed';

export interface InferenceInfo {
  id: string;
  created_at: string;
  finished_at: string | null;
  model_id: string;
  batch_id: string | null;
  wsi_path: string;
  wsi_filename: string;
  wsi_mtime: number;
  wsi_size: number;
  wsi_hash: string;
  output_dir: string;
  features_h5_path: string | null;
  heatmap_path: string | null;
  mixture_plot_path: string | null;
  example_patches_dir: string | null;
  tsne_path: string | null;
  status: InferenceStatus;
  error_message: string | null;
}

export interface InferenceDispatchEntry {
  wsi_path: string;
  status: InferenceStatus | 'rejected';
  id: string | null;
  cached: boolean;
  message: string | null;
}

export interface InferenceCreateResponse {
  batch_id: string | null;
  inferences: InferenceDispatchEntry[];
}

export interface InferenceBatchInfo {
  id: string;
  created_at: string;
  model_id: string;
  user_label: string | null;
  total_count: number;
}

export interface InferenceRerunResponse {
  new_inference_id: string;
  job_id: string;
}

export function createInferences(payload: {
  model_id: string;
  wsi_paths: string[];
  batch_label?: string;
  rerun?: boolean;
}): Promise<InferenceCreateResponse> {
  return request('/api/inferences', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function lookupInference(
  modelId: string,
  wsiPath: string
): Promise<InferenceInfo | null> {
  // Treat 404 as "no cache hit" — that's the documented contract.
  const qs = new URLSearchParams({ model_id: modelId, wsi_path: wsiPath });
  const res = await fetch(`/api/inferences/lookup?${qs.toString()}`);
  if (res.status === 404) return null;
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

export function listInferences(opts?: {
  modelId?: string;
  batchId?: string;
  status?: InferenceStatus;
  limit?: number;
}): Promise<InferenceInfo[]> {
  const params = new URLSearchParams();
  if (opts?.modelId) params.set('model_id', opts.modelId);
  if (opts?.batchId) params.set('batch_id', opts.batchId);
  if (opts?.status) params.set('status', opts.status);
  if (opts?.limit != null) params.set('limit', String(opts.limit));
  const qs = params.toString();
  return request(`/api/inferences${qs ? `?${qs}` : ''}`);
}

export function getInference(inferenceId: string): Promise<InferenceInfo> {
  return request(`/api/inferences/${encodeURIComponent(inferenceId)}`);
}

export function rerunInference(inferenceId: string): Promise<InferenceRerunResponse> {
  return request(`/api/inferences/${encodeURIComponent(inferenceId)}/rerun`, {
    method: 'POST',
  });
}

export function getInferenceBatch(batchId: string): Promise<InferenceBatchInfo> {
  return request(`/api/inference-batches/${encodeURIComponent(batchId)}`);
}

export interface ExamplePatchGroup {
  prototype_index: number;
  label: string | null;
  urls: string[];
}

export interface ExamplePatchesResponse {
  inference_id: string;
  base_dir: string;
  groups: ExamplePatchGroup[];
}

export function listInferenceExamplePatches(
  inferenceId: string
): Promise<ExamplePatchesResponse> {
  return request(
    `/api/inferences/${encodeURIComponent(inferenceId)}/example-patches`
  );
}

// --- Inference notes ------------------------------------------------------

export interface InferenceNoteInfo {
  id: string;
  inference_id: string;
  body: string;
  created_at: string;
  updated_at: string;
}

export function listInferenceNotes(inferenceId: string): Promise<InferenceNoteInfo[]> {
  const qs = new URLSearchParams({ inference_id: inferenceId });
  return request(`/api/inference-notes?${qs.toString()}`);
}

export function createInferenceNote(payload: {
  inference_id: string;
  body: string;
}): Promise<InferenceNoteInfo> {
  return request('/api/inference-notes', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateInferenceNote(
  noteId: string,
  payload: { body: string }
): Promise<InferenceNoteInfo> {
  return request(`/api/inference-notes/${encodeURIComponent(noteId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteInferenceNote(noteId: string): Promise<void> {
  return fetch(`/api/inference-notes/${encodeURIComponent(noteId)}`, {
    method: 'DELETE',
  }).then(() => undefined);
}

// --- Viz helpers ----------------------------------------------------------

export type PlaceholderKind = 'heatmap' | 'mixture' | 'patches' | 'tsne' | 'topk' | 'umap';

export function vizPlaceholderUrl(
  kind: PlaceholderKind,
  opts?: { label?: string; width?: number; height?: number }
): string {
  const params = new URLSearchParams();
  if (opts?.label) params.set('label', opts.label);
  if (opts?.width) params.set('width', String(opts.width));
  if (opts?.height) params.set('height', String(opts.height));
  const qs = params.toString();
  return `/api/viz/placeholder/${encodeURIComponent(kind)}${qs ? `?${qs}` : ''}`;
}

export function vizFileUrl(path: string): string {
  // Backend's serve_viz accepts either absolute or relative paths.
  return `/api/viz/${path.split('/').map(encodeURIComponent).join('/')}`;
}

/**
 * Resolve any stored viz path string to a URL usable as an <img src=...>.
 *
 * Stored path columns can carry:
 *   - a fully-formed URL the server already exposes: `/api/viz/placeholder/...`
 *     (seed data) or `/api/viz/{file}` (PR 3's real renderer once it lands)
 *   - an absolute disk path (PR 3 might also write these — wrap with vizFileUrl)
 *   - null/undefined when the renderer hasn't produced anything yet — caller
 *     decides what to show in that case via `fallback`.
 */
export function resolveVizUrl(
  path: string | null | undefined,
  fallback: () => string
): string {
  if (!path) return fallback();
  if (path.startsWith('/api/viz/')) return path;
  if (path.startsWith('http://') || path.startsWith('https://')) return path;
  return vizFileUrl(path);
}

export function getCsvRowCount(path: string): Promise<{ rows: number }> {
  const params = new URLSearchParams({ path });
  return request(`/api/fs/csv-count?${params.toString()}`);
}

export interface CsvInspectResult {
  rows: number;
  columns: string[];
  has_slide_id: boolean;
  slide_id_column: string | null;
  tif_count: number;
  sample_ids: string[];
}

/**
 * Inspect a CSV's columns for split creation: whether a usable slide_id column
 * exists, and how many of its values still carry a `.tif` extension (which the
 * backend strips when the split is built).
 */
export function inspectCsv(path: string): Promise<CsvInspectResult> {
  const params = new URLSearchParams({ path });
  return request(`/api/fs/csv-inspect?${params.toString()}`);
}

// --- Jobs -----------------------------------------------------------------

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled';
export type JobType = 'panther_train' | 'post_train_viz' | 'inference';

export interface JobInfo {
  id: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  job_type: JobType;
  ref_table: string;
  ref_id: string;
  status: JobStatus;
  error_message: string | null;
  log_path: string | null;
  queue_position: number | null;
}

export interface JobDetail extends JobInfo {
  log_tail: string;
}

export function listJobs(opts?: {
  status?: JobStatus;
  jobType?: JobType;
  refTable?: string;
  refId?: string;
  limit?: number;
}): Promise<JobInfo[]> {
  const params = new URLSearchParams();
  if (opts?.status) params.set('status', opts.status);
  if (opts?.jobType) params.set('job_type', opts.jobType);
  if (opts?.refTable) params.set('ref_table', opts.refTable);
  if (opts?.refId) params.set('ref_id', opts.refId);
  if (opts?.limit != null) params.set('limit', String(opts.limit));
  const qs = params.toString();
  return request(`/api/jobs${qs ? `?${qs}` : ''}`);
}

export function getJob(jobId: string): Promise<JobDetail> {
  return request(`/api/jobs/${encodeURIComponent(jobId)}`);
}

export function retryJob(jobId: string): Promise<JobInfo> {
  return request(`/api/jobs/${encodeURIComponent(jobId)}/retry`, { method: 'POST' });
}

export function cancelJob(jobId: string): Promise<JobInfo> {
  return request(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' });
}

// --- Queue ----------------------------------------------------------------

export interface JobView {
  id: string;
  job_type: JobType;
  status: JobStatus;
  ref_table: string;
  ref_id: string;
  queue_position: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
  title: string;
  subtitle: string | null;
}

export interface QueueResponse {
  running: JobView | null;
  waiting: JobView[];
  recent: JobView[];
}

export function getQueue(): Promise<QueueResponse> {
  return request('/api/queue');
}

export function reorderQueue(orderedJobIds: string[]): Promise<QueueResponse> {
  return request('/api/queue/reorder', {
    method: 'POST',
    body: JSON.stringify({ ordered_job_ids: orderedJobIds }),
  });
}
