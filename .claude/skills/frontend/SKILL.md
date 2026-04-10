# Frontend Skill
React (Vite) + JS + Tailwind. Axios in src/api/client.js using VITE_API_URL.
Pages: InferencePage (dataset_path + num_clusters 2-20 → POST /api/v1/inference), JobsDashboard (polls /api/v1/jobs every 2s, @dnd-kit/sortable drag-and-drop on Queued rows only, Processing rows locked with icon, PUT /api/v1/jobs/reorder on drop), AnnotationsPage (target_id, target_type select slide|cluster, note textarea → POST).
Components: JobRow, StatusBadge (color per status), Toast, NavBar.
Rules: Tailwind only, all API via client.js, plain JS (no TS), handle error states.