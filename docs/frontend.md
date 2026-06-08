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
| `/training/panther` | `PantherTrainingPage` | Configure a split + hyperparameters, start K-fold training. |
| `/models` | `ModelsBrowserPage` | Browse training runs (one card per Model Group). |
| `/models/:groupId` | `GroupDetailPage` | Inspect each fold of a group. |
| `/models/:modelId/inference` | `InferencePage` | Run a fold model on new slides. |
| `/`, `/training`, `*` | → redirect to `/training/trident` | |

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
(`listSplits`, `getSplit`, `createSplit`), PANTHER (`startPantherKFoldRun`, `listModels`),
groups/models (`listModelGroups`, `getModelGroup`, `patchModelGroup`, `getModel`,
`patchModel`, `shuffleModelPreview`, `getModelTridentParams`), prototype labels, model
notes, inferences (`createInferences`, `lookupInference`, `listInferences`, `getInference`,
`rerunInference`, `getInferenceBatch`, `listInferenceExamplePatches`), inference notes,
and jobs (`listJobs`, `getJob`, `retryJob`).

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
The most stateful form. Flow:

1. User enters a **features directory**; a debounced effect calls `resolveFeaturesDir` to
   bind it to a `TridentRun` + dataset (shown as a chip). Everything downstream is gated
   on a successful resolve.
2. **Split section** — toggle between *Create new K-fold split* (browse a source CSV →
   `getCsvRowCount` shows row count → `createSplit`) and *Use existing split* (a dropdown
   loaded via `listSplits(dataset)`). Creating a split auto-switches to "existing" with it
   selected.
3. **PANTHER parameters** — mode, in_dim, n_proto, n_proto_patches, n_init, num_workers,
   seed, all as validated number inputs, with a per-fold command preview.
4. Submit → `startPantherKFoldRun` → navigate to `/models/{group_id}`. The button label
   reflects the effective K (`Train 5 Models`).

### `ModelsBrowserPage`
A filterable card grid of Model Groups. Controls: search (`q`), dataset filter, sort
(`created_desc|created_asc|name`), favorites-only. Each `GroupCard` shows the display name,
dataset chip, `K · n_proto · mode`, created time, and a **StatusPill** computed from the
group's fold summary (training… / N/total ready / failed / mixed). Empty state links to the
PANTHER page.

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
| **`DirectoryBrowser`** | Modal file/dir picker (rendered via portal). Backed by `/api/fs/*`. Supports `dir` vs `file` mode, extension filtering, multi-select (checkboxes), breadcrumb + root switcher, and full keyboard navigation (arrows, Enter, Space, Esc). Single- and multi-select variants are distinguished by `onSelect` vs `onSelectMulti`. |
| **`EncoderSelect`** | The patch-encoder `<select>` plus `patchSizeFor(encoder)` (UNI→256, Phikon→224), mirroring the backend. |
| **`TridentForm`** | TRIDENT launch form (see page above). |
| **`PantherForm`** | PANTHER training form (see page above). |
| **`JobStatusPoller`** | Polls `/api/jobs?ref_id=…` every 2 s, lists each job with a status badge + a "log" link (opens `JobLogViewer`), fires `onJobFinished` on terminal transitions, and stops once all jobs are terminal. |
| **`JobLogViewer`** | Modal (portal) showing a job's `log_tail`, re-fetching every 2 s while the job is in flight; shows `error_message` if present. |
| **`NotesThread`** | CRUD thread reused for both model notes and inference notes via a `target` discriminator (`{kind:'model'\|'inference', …}`). Add / edit / delete, optimistic local list updates. |
| **`PrototypeLabels`** | A grid of `n_proto` text inputs; loads existing labels, saves on blur (`upsertPrototypeLabel`) with per-field saving/saved/error indicators. |

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
