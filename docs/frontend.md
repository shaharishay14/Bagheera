# Bagheera — Frontend Reference

> A Vite + React + TypeScript + Tailwind single-page app that drives the Bagheera
> backend. It is a thin, dependency-light UI: no state-management or data-fetching
> library — just `fetch`, `useState`/`useEffect`, and polling.
>
> Read [structure.md](./structure.md) for the product flow and [backend.md](./backend.md)
> for the API it consumes. This document covers the frontend's stack, routing, the typed
> API client, every page and component, and the cross-cutting patterns (polling, the
> visualization fallback system, the directory browser).

---

## 1. Stack

| Concern | Choice |
| --- | --- |
| Build / dev server | Vite `5` (`@vitejs/plugin-react`) |
| UI library | React `18` (StrictMode) |
| Language | TypeScript `5.7` (strict) |
| Routing | `react-router-dom` `6` (`BrowserRouter`) |
| Styling | TailwindCSS `3.4` (utility classes only; no component lib) |
| HTTP | the platform `fetch` (no axios/react-query/SWR) |
| State | local component state only (no Redux/Zustand/Context store) |

**Dev server** (`vite.config.ts`): runs on port **5173** and proxies `/api/*` to
`http://localhost:8000`, so the browser makes same-origin calls and there's no CORS round
trip in dev. Build: `tsc -b && vite build`.

The whole app is small (~3 800 lines of TS/TSX). The design language is deliberately
plain: slate/neutral palette, rounded cards, status "pills", monospace for paths and
technical identifiers.

---

## 2. Routing & shell (`src/App.tsx`)

`App.tsx` is the shell: a top header with a nav (`Training → TRIDENT | PANTHER | Models`)
and the route table.

| Route | Page | Purpose |
| --- | --- | --- |
| `/training/trident` | `TridentTrainingPage` | Start a TRIDENT feature-extraction run. |
| `/training/panther` | `PantherTrainingPage` | Configure a single split + hyperparameters, train one standalone model. |
| `/training/panther/compare` | `PantherComparePage` | Render one WSI through up to 4 of a dataset's models, side by side. |
| `/models` | `ModelsBrowserPage` | Browse standalone models (flat cards) + legacy K-fold groups. |
| `/models/:modelId` | `ModelDetailPage` | Inspect one standalone model (analysis, labels, notes). |
| `/models/group/:groupId` | `GroupDetailPage` | Legacy: inspect each fold of a K-fold group. |
| `/models/:modelId/inference` | `InferencePage` | Run a model on new slides. |
| `/`, `/training`, `*` | → redirect to `/training/trident` | |

**Route collision note.** `/models/:modelId` (standalone) and the legacy group
detail page can't share a `:id` slot, so legacy groups live under an explicit
static `/models/group/:groupId`. React Router ranks the static `group` segment
above the dynamic `:modelId`, and `/models/:modelId/inference` above bare
`/models/:modelId`, so all three resolve unambiguously.

`main.tsx` mounts `<App/>` in StrictMode; `index.css` is just the three Tailwind layers
plus a full-height root.

---

## 3. The API client (`src/lib/api.ts`)

The single source of truth for the FE↔BE contract. It exports a TypeScript interface for
every response shape and a thin function per endpoint. Editing this file is how you keep
the UI in lockstep with the backend.

**Core helpers:**

- `request<T>(path, init?)` — wraps `fetch`, sets JSON headers, parses errors into an
  `ApiError(status, detail)`. **Treats HTTP `207` as success** (partial-success signal for
  batch inference / K-fold dispatch) and surfaces the body to the caller.
- `ApiError` — carries `status` + `message`; pages branch on it to render inline errors.

**Endpoint groups** (mirrors the backend): filesystem (`getRoots`, `listDirectory`,
`getCsvRowCount`), TRIDENT (`startTridentRun`, `resolveFeaturesDir`), splits
(`listSplits`, `getSplit`, `createSplit`, `createSingleSplit`), PANTHER
(`startPantherRun` for standalone single models, `startPantherKFoldRun` for legacy K-fold,
`listModels` with an optional `runKind` filter),
groups/models (`listModelGroups`, `getModelGroup`, `patchModelGroup`, `getModel`,
`patchModel`, `shuffleModelPreview`, `getModelTridentParams`), prototype labels, model
notes, inferences (`createInferences`, `lookupInference`, `listInferences`, `getInference`,
`rerunInference`, `getInferenceBatch`, `listInferenceExamplePatches`), inference notes,
datasets/compare (`listDatasets`, `getDatasetSlides`, `getDatasetModels`, `renderSlide`,
`getSlideViz` — the Model Comparison page's dataset→slide→models flow; `renderSlide` returns
either `{status:'ready', artifacts}` on a cache hit or `{status:'rendering', job_id}` to poll
`getSlideViz` on the 2 s cadence), and jobs (`listJobs`, `getJob`, `retryJob`).

Two functions intentionally bypass `request` because they need custom status handling:
`lookupInference` (treats `404` as "no cache hit" → returns `null`) and the `DELETE`
helpers (no body to parse).

### The visualization URL resolver (important pattern)

Stored viz path columns can hold different things depending on whether a real render has
happened. Three helpers normalize this:

- `vizPlaceholderUrl(kind, {label,width,height})` → `/api/viz/placeholder/{kind}?…`
  (server-synthesized SVG).
- `vizFileUrl(path)` → `/api/viz/{encoded path}` (real file).
- **`resolveVizUrl(path, fallback)`** — the one components actually call. If `path` is
  null/empty → `fallback()` (a placeholder); if it's already a `/api/viz/...` or `http(s)`
  URL → use as-is; otherwise wrap it with `vizFileUrl`. **This is why the UI looks
  complete before any real render exists** — every image gracefully degrades to a labeled
  placeholder.

---

## 4. Pages

### `TridentTrainingPage` → `TridentForm`
A form to launch feature extraction. The user types a dataset name (validated
`^[A-Za-z0-9_-]+$`), browses to a WSI directory, and picks an encoder. **Locked fields**
(task, job dir, magnification=20, patch size derived from encoder) are shown read-only so
the user sees exactly what will run. A live, copyable **command preview** mirrors the
backend's argv. Submit calls `startTridentRun` — which **blocks** until TRIDENT finishes —
then shows the run result or the failure's stderr.

### `PantherTrainingPage` → `PantherForm`
The most stateful form. Trains **one standalone model** on a single (100%-train) split.
Flow:

1. User enters a **features directory**; a **debounced** (~400 ms) effect calls
   `resolveFeaturesDir` to bind it to a `TridentRun` + dataset (shown as a chip). The stale
   resolve is kept in place while typing so the dataset-scoped split effect below doesn't
   thrash. Everything downstream is gated on a successful resolve.
2. **Split section** — toggle between *Create single split* (browse a source CSV →
   `getCsvRowCount` + `inspectCsv` notices → `createSingleSplit`, which posts `kind:"single"`
   with no `k`) and *Use existing split* (a dropdown loaded via `listSplits(dataset)`).
   Creating a split auto-switches to "existing" with it selected. The split list is keyed on
   the resolved **`dataset_name` string** (`splitScopeKey`), not the resolved object's
   identity — so re-resolving the same dataset never clears the user's chosen split.
3. **PANTHER parameters** — mode, in_dim (locked from the encoder), n_proto, n_proto_patches,
   n_init, num_workers, seed, all via `NumberInput` (local string buffer; clamps to
   `[min,max]` only on **blur** via `clampToRange`, so fields can be cleared / mid-edited).
   Command preview uses the single-fold split dir `…/{split}/k=0`.
4. Submit → `startPantherRun` (`POST /api/panther/single-runs`) → navigate to
   `/models/{model_id}`. Button label: `Train model`.

### `PantherComparePage`
Renders one WSI through several models side by side (`/training/panther/compare`). A strict
top-down gate: **① Dataset** (`listDatasets` — only datasets with ≥1 non-legacy single model;
selecting one resets everything below) → **② WSI** (`getDatasetSlides`, a lazy-thumbnail grid
with an icon fallback; `has_wsi=false` tiles are disabled; a subtle `thumbnails: N/total`
diagnostic surfaces the F3 mismatch) → **③ Models** ("Add model" dropdown over
`getDatasetModels`, max 4, each slot has **Swap** + **Remove**) → **④ Grid** of
`CompareModelPanel`s (1–3 models = one responsive row via `compareGridClass`, 4 = a 2×2 grid).
A **Sync zoom/pan** checkbox lifts one `Transform` in page state and feeds it to every panel so
pan/zoom mirror across columns; off, each panel is independent. `compareGridClass` is pure and
unit-tested.

### `ModelsBrowserPage`
A filterable card grid. Fetches **both** standalone models (`listModels({runKind:'single'})`,
rendered as flat `ModelCard`s linking to `/models/:modelId`) and legacy K-fold groups
(`listModelGroups`, rendered as `GroupCard`s with a *legacy K-fold* chip, linking to
`/models/group/:groupId`). Controls: search (`q`), dataset filter, sort
(`created_desc|created_asc|name`), favorites-only — applied server-side for groups and
client-side for standalone models. Empty state (both empty) links to the PANTHER page.

### `ModelDetailPage`
The inspection surface for one standalone model (`/models/:modelId`). Header: favorite star
+ inline-editable name (`patchModel`), a *single model* chip, dataset/status/n_proto/mode/
created metadata, split summary, and an **Inference →** link. Body reuses the paper-style
analysis panels (`SectionAPanel` — see its ROI controls below —, `SectionCPanel`,
`SectionDPanel`, and `SectionBPanel` only
when `viz_artifacts.section_b` exists — single models have no held-out slides, so it usually
degrades to a muted note), plus `PrototypeLabels`, a read-only params/paths dump, a
`NotesThread` (model target), and a `JobStatusPoller` (`refTable="models"`) that reloads the
model on job finish. An active-jobs banner and a failure-log link appear on the relevant
states.

### `GroupDetailPage`
The inspection surface for one group's K folds.

- **Header** — inline-editable group name (`patchModelGroup`), dataset/K/n_proto/mode/date
  metadata, split summary.
- **Active-jobs banner** — when any fold is `running`/`pending`, renders a
  `JobStatusPoller` for the group; `onJobFinished` reloads the group.
- **Fold rows** (`FoldRow`) — favorite star (`patchModel`), status + viz-status pills,
  three preview heatmap thumbnails (via `resolveVizUrl`), a shuffle button
  (`shuffleModelPreview`), a failure-log link, and three drawer tabs:
  - **Analysis** — preview heatmaps, the top-K grid, the UMAP, the `PrototypeLabels` editor,
    and a `JobStatusPoller` for viz jobs.
  - **Parameters** — read-only hyperparameter / path dump.
  - **Notes** — `NotesThread` for the model.
  - plus an **Inference →** link.
- **`FailureLogLink`** — looks up the most recent failed job for the right ref (training
  failure → the group's `panther_train`; viz failure → the model's `post_train_viz`) and
  opens it in `JobLogViewer`.

### `InferencePage`
Run a fold model on new slides. The richest page.

- **Boot** — parallel `getModel` + `getModelTridentParams` + `listInferences`. A
  `ParamsCard` shows the encoder/mag/patch-size/GPUs new slides will be processed with (or
  a warning if the model has no recorded TRIDENT run).
- **History** — collapsible list of prior inferences for this fold; clicking one opens its
  result.
- **Mode** — *Single slide* vs *Batch*. The `DirectoryBrowser` opens in `file` mode
  filtered to WSI extensions (single-select or multi-select per mode).
- **Cache pre-check** — on selection, each path is checked via `lookupInference`; the
  `SelectionList` marks each `✓ Cached` (with a per-path **Re-run** checkbox) or `○ Will be
  processed`, and a batch summary tallies `cached / will process / checking…`.
- **Run** (`onRun`) — splits selections into pure cache-hits (just display), rerun-toggled
  hits (`rerunInference` per path), and true misses (`createInferences` batch). Collects all
  resulting inference IDs into `trackingIds`.
- **Tracking** — an effect polls `getInference` for every tracked ID every 2 s until all are
  terminal.
- **Results** (`ResultsSection` → `SingleResultView`) — per slide: assignment heatmap,
  mixture plot, **example patches** (`ExamplePatchesGrid` → `listInferenceExamplePatches`,
  with a `Lightbox`), collapsible t-SNE, dataset-wide top-K + UMAP reference tiles, and a
  per-inference `NotesThread`. Batch mode adds a progress header and a per-slide selector.

---

## 5. Components

| Component | Responsibility |
| --- | --- |
| **`DirectoryBrowser`** | Modal file/dir picker (rendered via portal). Backed by `/api/fs/*`. Supports `dir` vs `file` mode, extension filtering, multi-select (checkboxes), breadcrumb + root switcher, and full keyboard navigation (arrows, Enter, Space, Esc). Single- and multi-select variants are distinguished by `onSelect` vs `onSelectMulti`. Optional `thumbnailFor(path) => url` prop: in `file` mode, each file row renders a small lazy `<img>` (that URL) in place of the file icon, falling back to the icon on load error — used by `InferencePage` with `slideThumbnailUrl` for WSI previews; omit for icon-only pickers (e.g. CSV). |
| **`EncoderSelect`** | The patch-encoder `<select>` plus `patchSizeFor(encoder)` (UNI→256, Phikon→224), mirroring the backend. |
| **`TridentForm`** | TRIDENT launch form (see page above). |
| **`PantherForm`** | PANTHER training form (see page above). |
| **`JobStatusPoller`** | Polls `/api/jobs?ref_id=…` every 2 s, lists each job with a status badge + a "log" link (opens `JobLogViewer`), fires `onJobFinished` on terminal transitions, and stops once all jobs are terminal. |
| **`JobLogViewer`** | Modal (portal) showing a job's `log_tail`, re-fetching every 2 s while the job is in flight; shows `error_message` if present. |
| **`NotesThread`** | CRUD thread reused for both model notes and inference notes via a `target` discriminator (`{kind:'model'\|'inference', …}`). Add / edit / delete, optimistic local list updates. |
| **`PrototypeLabels`** | A grid of `n_proto` text inputs; loads existing labels, saves on blur (`upsertPrototypeLabel`) with per-field saving/saved/error indicators. |
| **`ZoomPanImage`** | Hand-rolled zoom/pan image viewer (wheel-to-zoom, drag-to-pan, ± / reset buttons). Optional `armed` + `onImageClick(fx,fy)` props turn it into a point picker: while `armed`, the viewport shows a crosshair and a non-drag click reports normalized `[0,1]` coords over the natural image (a pan of >4 px is not treated as a select). Optional `transform` + `onTransformChange` make it **controlled**: when `transform` is passed the component renders from the prop and every internal `commit` reports the clamped transform upward (still clamping locally) instead of owning state — the Compare page lifts one `Transform` and feeds it to the matching image in every panel to mirror pan/zoom. When `transform` is absent it is uncontrolled exactly as before. The pure `normalizedClick(rect, tf, imgW, imgH, x, y)` helper is exported and unit-tested, as is the controlled/uncontrolled behavior. |
| **`SectionAPanel`** | The paper-style per-slide ROI panel. **Repick ROI** auto-picks a new window (`repickRoi`). **Select** arms a one-shot pick mode that passes `armed`/`onImageClick` to the assignment-map `ZoomPanImage`; a click calls `selectRoi(model.id, {slide_id, fx, fy})` and then auto-disarms — preview slide (`slide_id: null`, the default, `slideId` prop omitted) swaps `section` from the returned `ModelInfo`; a compare slide (`slideId` prop set) swaps just the `roi_*` fields from the returned `SlideVizArtifacts`. 409/422 render the same inline notice as repick. Optional `section` overrides the source (the Compare page feeds an arbitrary slide's render-slide manifest instead of `model.viz_artifacts?.section_a`); optional `imageTransform`/`onImageTransformChange` thread a controlled transform to the row-1 WSI + assignment-map images for cross-panel sync. |
| **`SectionCPanel`** | The dataset-wide UMAP pair. Optional `onTissue` overrides the per-slide on-tissue colormap (Compare page) while the abstract scatter stays dataset-global (`section_c.scatter` / `umap_path`); optional `slideId` sets the caption. Absent overrides → identical to the model-detail behavior (incl. the legacy flat-`umap_path` fallback). |
| **`ViolinPanel`** | Small per-slide Section-B violin (`resolveVizUrl` with a `mixture` placeholder fallback) captioned "Per-slide prototype similarity (violin)" — used by `CompareModelPanel` where the violin comes from a slide's render manifest. |
| **`CompareModelPanel`** | One column of the Compare grid. On a chosen `slideId` it POSTs `renderSlide(model.id, slideId)` and runs a small state machine: `ready` → use the returned manifest; `rendering` → show a rendering banner + `JobStatusPoller` (`refTable="models"`, `refId=model.id`) and poll `getSlideViz` every 2 s until `ready`; a matching failed job or a render error → inline error + **Retry**. Renders (top→bottom) a model header chip, `SectionAPanel` (manifest-fed + optional synced transform), `ViolinPanel`, `SectionCPanel` (per-slide `onTissue`), and the global `SectionDPanel`. |

---

## 6. Cross-cutting patterns

**Data fetching.** Every page/component follows the same shape: a `useEffect` with a
`cancelled` flag, `loading`/`error` state, and `ApiError`-aware messages. There is no
shared cache — navigating away and back re-fetches.

**Polling, not websockets.** Long-running work is observed by `setTimeout` poll loops at a
2 s cadence (jobs, tracked inferences, log viewers), each self-terminating when its target
reaches a terminal state. `JobStatusPoller` additionally reports terminal transitions
upward so parents can refresh.

**Graceful image degradation.** Pages never assume a render exists: `resolveVizUrl(path,
fallback)` swaps in a labeled SVG placeholder whenever a path column is null or not yet a
served URL. This keeps the UI coherent during `pending`/`rendering` states and against seed
data.

**Partial-success handling.** Batch inference and K-fold dispatch can return `207`; the API
client passes the body through rather than throwing, and the inference page renders
per-path `rejected`/`cached`/`queued` outcomes.

**Modals via portals.** `DirectoryBrowser`, `JobLogViewer`, and the patch `Lightbox` all
render into `document.body` with backdrop + Esc-to-close.

**Validation mirrors the backend.** Name patterns (`^[A-Za-z0-9_-]+$`), encoder→patch-size,
magnification, and command previews are duplicated client-side purely for instant feedback;
the backend re-validates everything authoritatively.

---

## 7. Conventions for extending the UI

- **New endpoint?** Add its types + function to `lib/api.ts` first; pages import from there
  and never call `fetch` directly (except the two documented exceptions).
- **New long-running flow?** Reuse `JobStatusPoller` / the 2 s poll pattern rather than
  inventing a new mechanism.
- **New visualization slot?** Store the path on the relevant row, render it through
  `resolveVizUrl` with an appropriate placeholder `kind`.
- **Styling** is Tailwind utilities inline; match the existing slate palette, rounded
  cards, uppercase-tracking section headers, and status-pill patterns rather than adding a
  component framework.
