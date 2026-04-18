# Frontend Skill
React (Vite) + JS + Tailwind. Axios in src/api/client.js using VITE_API_URL.

## Pages
- InferencePage: dataset_path + num_clusters (2–32) → POST /api/v1/inference. Advanced PANTHER parameters in a <details> block: encoder select (uni|ctranspath|resnet50), em_iter number input (1–10), tau range slider (0.01–10, live font-mono readout), out_type select.
- JobsDashboard: polls /api/v1/jobs every 2s, @dnd-kit/sortable drag-and-drop on Queued rows only, Processing/Done rows locked with SVG padlock icon, PUT /api/v1/jobs/reorder on drop. JobRow shows encoder + num_clusters as secondary line; prio N is hidden.
- AnnotationsPage: two-column (md: breakpoint). Left: POST form. Right: live feed fetched from GET /api/v1/annotations with target_id/target_type filter bar and per-card SVG delete button (DELETE endpoint).
- ComparePage: two side-by-side job selector panels (Done jobs only filtered client-side), each with a metrics strip (C, encoder, tau, em_iter, out_type, duration) and cluster grid (grid-cols-2 for C≤8, grid-cols-4 for C>8). VS divider between panels. Below: annotation form pre-filled with "{left_job_id} vs {right_job_id}" as target_id.

## Components
- JobRow: SVG drag handle (three horizontal lines) or SVG padlock. No prio N text. Three-line body: job id (8 chars, font-mono), dataset path, encoder·clusters.
- StatusBadge: Queued=panther-400 tones, Processing=amber, Done=emerald, Error=accent. rounded-md.
- Toast: white card with left border by kind (accent/emerald/panther-400), z-50, auto-dismiss with hover-pause, close × button.
- NavBar: bg-panther-900 brand bar with logo img, four NavLinks (Inference/Jobs/Annotations/Compare). Active: text-white border-b-2 border-accent. Inactive: text-panther-200 hover:text-white.

## Design system tokens (tailwind.config.js)
Colors: panther.{950,900,800,700,600,400,200,50}, accent.{DEFAULT=#C8102E,hover=#A50D25,light=#FDEAED}.
Fonts: display=Playfair Display, body=DM Sans, mono=JetBrains Mono (Google Fonts loaded in index.html).
Component conventions: card=bg-white border border-panther-400/20 rounded-xl shadow-sm, primary button=bg-accent hover:bg-accent-hover text-white font-body font-medium px-5 py-2.5 rounded-lg transition-colors, input=border border-panther-400/30 rounded-lg px-3 py-2 font-mono text-sm focus:ring-2 focus:ring-panther-400/40.

## API modules
src/api/client.js (axios), inference.js (submitInference — all 6 fields), jobs.js (listJobs, getJobStatus, reorderJobs, getVisualization), annotations.js (createAnnotation, listAnnotations, deleteAnnotation).

## Rules
Tailwind only, all API via client.js, plain JS (no TS), handle error states with Toast.
