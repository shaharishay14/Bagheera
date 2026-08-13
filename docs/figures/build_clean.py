"""Build 'Detailed Design - Bagheera' — the clean, submission-ready document.

Formatting matches the originally submitted detailed design: 24 pt bold title,
13.5 pt bold section headings, default body text with bold lead-ins, bordered
tables, and figures.
"""
from __future__ import annotations

import os
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, Inches, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = "/Users/shaharishay/Projects/Bagheera"
OUT = os.path.join(REPO, "docs", "Detailed Design - Bagheera.docx")

doc = Document()

# Page setup matching the original (Letter, 1.25" side margins, 1" top)
sec = doc.sections[0]
sec.left_margin = Inches(1.25)
sec.right_margin = Inches(1.25)
sec.top_margin = Inches(1.0)
sec.bottom_margin = Inches(1.0)

CODE_GREY = RGBColor(0x44, 0x44, 0x44)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def para(*parts, space_after=6, space_before=0, align=None, style=None):
    """parts: str  OR  (text, 'b'|'i'|'bi'|'c'|'u') tuples."""
    p = doc.add_paragraph(style=style)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.space_before = Pt(space_before)
    if align:
        p.alignment = align
    for part in parts:
        if isinstance(part, tuple):
            text, fmt = part
        else:
            text, fmt = part, ""
        r = p.add_run(text)
        if "b" in fmt:
            r.bold = True
        if "i" in fmt:
            r.italic = True
        if "u" in fmt:
            r.underline = True
        if "c" in fmt:
            r.font.name = "Consolas"
            r.font.size = Pt(9.5)
            r.font.color.rgb = CODE_GREY
    return p


def title(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(24)
    return p


def h(text, *, before=14, after=6):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(13.5)
    return p


def bullet(lead, rest="", *, code=False):
    """A bulleted item with an optional bold lead-in."""
    p = doc.add_paragraph(style="List Paragraph")
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.left_indent = Inches(0.35)
    r = p.add_run("• ")
    if lead:
        r = p.add_run(lead)
        r.bold = True
    if rest:
        r = p.add_run(rest)
        if code:
            r.font.name = "Consolas"
            r.font.size = Pt(9.5)
    return p


def numbered(text):
    p = doc.add_paragraph(text, style="List Paragraph")
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.left_indent = Inches(0.35)
    return p


def code(lines, size=8.5):
    for line in lines:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.left_indent = Inches(0.25)
        r = p.add_run(line if line else " ")
        r.font.name = "Consolas"
        r.font.size = Pt(size)
        r.font.color.rgb = CODE_GREY
    doc.paragraphs[-1].paragraph_format.space_after = Pt(8)


def table(rows, *, widths=None, size=9, header=True):
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    t.style = "Table Grid"
    t.autofit = True
    for i, row in enumerate(rows):
        for j, cell_text in enumerate(row):
            cell = t.cell(i, j)
            cell.text = ""
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.space_before = Pt(2)
            r = p.add_run(str(cell_text))
            r.font.size = Pt(size)
            if header and i == 0:
                r.bold = True
    if widths:
        for j, w in enumerate(widths):
            for row in t.rows:
                row.cells[j].width = Inches(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)
    return t


FIGURES_DIR = os.path.join(REPO, "docs", "figures")


def figure(png, caption, width=6.4, *, placeholder=None):
    """Prefer a hand-authored figure in docs/figures/, else the generated one.

    If `placeholder` is given and neither file exists, emit a visible TO-BE-INSERTED
    box instead of failing the build.
    """
    authored = os.path.join(FIGURES_DIR, png)
    generated = os.path.join(HERE, png)
    src = authored if os.path.exists(authored) else generated
    if not os.path.exists(src):
        if placeholder is None:
            raise FileNotFoundError(src)
        ph = doc.add_paragraph()
        ph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        ph.paragraph_format.space_before = Pt(18)
        ph.paragraph_format.space_after = Pt(4)
        r = ph.add_run(placeholder)
        r.bold = True
        r.font.size = Pt(11)
        r.font.color.rgb = RGBColor(0xC0, 0x50, 0x20)
        ph2 = doc.add_paragraph()
        ph2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        ph2.paragraph_format.space_after = Pt(18)
        r2 = ph2.add_run("Drop the artwork at docs/figures/" + png
                         + " and rebuild. Build spec: docs/figures/FIGURE-1-SPEC.md")
        r2.italic = True
        r2.font.size = Pt(9)
        r2.font.color.rgb = RGBColor(0x8a, 0x81, 0x78)
    else:
        doc.add_picture(src, width=Inches(width))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(10)
    r = p.add_run(caption)
    r.italic = True
    r.font.size = Pt(9)




# ==========================================================================
# Cover
# ==========================================================================
title("Detailed Design - Bagheera")
para(("GUI System for Managing and Visualizing the PANTHER Model", "b"), space_after=10)

para(("Course:", "b"), " Final Project", space_after=2)
para(("Organizational Partner:", "b"), " Sheba Medical Center", space_after=2)
para(("Supervisors:", "b"), " Dr. Sharon Yalov Handzel", space_after=2)
para(("Project Team:", "b"), space_after=2)
para("Dolfin Varshev 315853101, Daniel Rubinstein 314621467, Shahar Ishay 322854308",
     space_after=12)

# ==========================================================================
h("1. Project Scope and Requirements", before=8)
# ==========================================================================
para("Bagheera is an interface layer that bridges the gap between advanced computational-pathology "
     "models and the people who need to use them. It provides a graphical user interface for the "
     "PANTHER model and for the TRIDENT feature-extraction pipeline that PANTHER depends on.")
para("PANTHER performs unsupervised slide representation learning. Given a cohort of whole-slide "
     "images it discovers a set of ", ("prototypes", "i"),
     " - recurring morphological patterns - clusters every tissue patch into one of them, and "
     "describes each slide as a mixture over those clusters. TRIDENT is the pipeline that prepares "
     "its input: it segments tissue, tiles each slide into patches, and encodes every patch into a "
     "feature vector.")
para("Both are command-line research tools. Running them today means editing shell invocations, "
     "tracking output directories by hand, and reading result arrays in a notebook. Bagheera turns "
     "that into a navigable visual workspace: every parameter of both pipelines is set in one place "
     "in the browser, every run is queued and observable, and the clustering the model produces is "
     "presented as a set of images a pathologist can read, name, and act on.")

para(("The system is built around four ideas:", "b"), space_before=6)
bullet("One configuration surface per pipeline. ",
       "Every TRIDENT parameter is set on a single form; every PANTHER hyperparameter is set on a "
       "single form. Neither requires a terminal, a config file, or knowledge of where the previous "
       "stage wrote its output.")
bullet("Unsupervised clustering as the product. ",
       "The prototypes PANTHER fits are the deliverable. Everything else in the system exists to "
       "produce them, inspect them, name them, or apply them.")
bullet("Heavy work is queued, never blocking. ",
       "Training, rendering and inference run asynchronously through a shared queue on a single "
       "GPU, so the interface stays responsive and a model failure is a status, not an outage.")
bullet("Analysis is visual and layered. ",
       "Four analysis panels per model, reproducing the figure layout of the PANTHER paper, plus "
       "side-by-side comparison of several models on the same tissue.")

h("1.1 Functional requirements", before=10, after=4)
para("Each requirement states what the system shall do, together with the acceptance criteria used "
     "to decide whether it does.")

table([
    ["#", "Requirement", "Acceptance criteria"],
    ["FR1", "The system shall extract patch-level features from a directory of whole-slide images, "
            "with every extraction parameter set on a single form and no command-line invocation "
            "by the user.",
     "The user selects a slide directory, a dataset name and a patch encoder; the system derives "
     "and displays every remaining parameter (task, magnification, patch size, output directory). "
     "It shall segment tissue, tile it at 20x into patches of the size the chosen encoder "
     "requires, and write one feature file per slide. The exact command shall be shown before "
     "submission and stored with the run."],
    ["FR2", "The system shall turn a source CSV into a validated training manifest that names "
            "every slide the model will be fitted on.",
     "The system shall detect the slide-identifier column, normalise the identifiers, and write "
     "the manifest in the layout the training pipeline reads, recording the source CSV, the row "
     "count, the detected column and a provenance seed. A CSV with no slide-identifier column "
     "shall be rejected before anything is written, and the source CSV shall never be modified."],
    ["FR3", "The system shall train a PANTHER model from the browser, with every hyperparameter "
            "set on a single form, without blocking the user interface.",
     "One form shall carry the feature source, the training manifest, and all seven PANTHER "
     "hyperparameters, "
     "with values that are properties of the data rather than choices (the feature width) derived "
     "automatically and locked. The request shall return before any GPU work begins, the run shall "
     "proceed asynchronously, and the user shall be able to watch its progress and read its log."],
    ["FR4", "The system shall cluster the tissue of a cohort into a user-specified number of "
            "morphological prototypes, and shall assign every extracted patch of every slide to "
            "exactly one prototype, without requiring any manual annotation or label.",
     "(a) The user shall specify the number of prototypes and the clustering backend (K-means, or "
     "FAISS on the GPU) before submission; both shall be recorded on the trained model. "
     "(b) Training input shall consist only of the feature files and the training manifest - no "
     "labels, no regions drawn by hand. "
     "(c) On completion the system shall persist the fitted prototype centres, and shall produce, "
     "for any slide of the cohort, a prototype assignment for each of its patches and a set of "
     "per-slide mixture weights over the prototypes that sum to one. "
     "(d) Each prototype shall carry a stable index, presented as C1..Cn, which every downstream "
     "view, colour and user-assigned label refers to. "
     "(e) Given the same features, manifest and seed, the fit shall be reproducible."],
    ["FR5", "The system shall serialise all heavy work through a single shared queue that the user "
            "can inspect and control.",
     "The queue shall show what is running, what is waiting and in what order, and recently "
     "finished work. The user shall be able to cancel a waiting job, change the waiting order by "
     "dragging, and re-run a finished or failed job. A running job shall not be cancellable."],
    ["FR6", "The system shall present the clustering of FR4 as a layered visual analysis that a "
            "pathologist can interpret without reading code or opening a file.",
     "For each trained model the system shall render (section 6): the prototype assignment map "
     "with mixture weights and a magnified region of interest; a per-prototype similarity "
     "distribution; a two-dimensional embedding shown both abstractly and painted onto the "
     "tissue; and a prototype dictionary of representative patches. Every image shall be zoomable "
     "and pannable."],
    ["FR7", "The system shall let the user steer the analysis rather than only consume it.",
     "The magnified region of interest shall be re-selectable, either by advancing to the next "
     "ranked candidate window or by clicking a point on the slide. Re-selection shall not re-run "
     "the encoder."],
    ["FR8", "The system shall allow the clustering produced by different models to be compared on "
            "the same tissue.",
     "The user shall be able to render one slide through up to four models side by side, and to "
     "lock zoom and pan across the columns so the same tissue is viewed at the same magnification "
     "in every panel."],
    ["FR9", "The system shall let a domain expert attach meaning to what the model found.",
     "The user shall be able to assign a biological name to each prototype, and to attach and edit "
     "free-text notes on a model and on an individual inference result. A prototype shall carry at "
     "most one name, and names shall persist across sessions."],
    ["FR10", "The system shall apply a trained model to slides that were not in its training "
             "cohort.",
     "The user shall be able to submit one or many new slides. The system shall extract their "
     "features using the same encoder configuration the model was trained against, assign their "
     "patches to that model's prototypes, and render the result. A slide already processed by that "
     "model shall be served from cache rather than recomputed, with an explicit per-slide override "
     "to force a re-run."],
], widths=[0.45, 2.15, 4.3], size=8)

h("1.2 Non-functional requirements", before=10, after=4)
para("Each non-functional requirement is stated as a metric with a threshold, so it can be "
     "re-verified on any deployment rather than argued about. The right-hand column records the "
     "value measured on the delivered system.")

table([
    ["#", "Requirement", "Metric and threshold", "Measured"],
    ["NFR1", "Data locality",
     "Outbound network connections initiated by the backend during normal operation: 0. Patient "
     "data leaving the host: none, under any code path.",
     "0. Model weights are fetched at build time or on first use and cached in a mounted volume; "
     "no run-time code path opens an external connection."],
    ["NFR2", "Startup without a GPU",
     "The API shall start and answer GET /api/health with 200 on a machine where torch, "
     "openslide, h5py, matplotlib and umap are not installed, in under 2 s.",
     "0.58 s (550 ms import + 27 ms startup and first request). Confirmed at run time that none "
     "of those five libraries were loaded into the process."],
    ["NFR3", "Fault isolation",
     "Worker-thread terminations caused by a job failure: 0. Time for the next queued job to start "
     "after a failure: <= 1 poll interval (2 s). API availability during a job failure: unaffected.",
     "0 terminations. Every handler runs inside a broad catch that records the traceback and "
     "continues the loop; verified during deployment across four missing-dependency failures and "
     "three upstream path assertions."],
    ["NFR4", "Path confinement",
     "Endpoints accepting a user-supplied path that resolve it through the single sandbox function "
     "before any filesystem operation: 100%. Traversal and symlink escape: 403.",
     "100% - 28 call sites across 8 routers and 3 services. No second code path opens a "
     "user-supplied file. Regression test: test_403_outside_roots."],
    ["NFR5", "Submission responsiveness",
     "Time for a training submission to return: < 1 s, independent of cohort size. Worst-case "
     "staleness of any progress indicator: <= 2 s.",
     "Met by construction: the request performs two inserts and returns, with no GPU work inside "
     "it. All progress surfaces poll on a 2 s cadence."],
    ["NFR6", "Durability across restart",
     "Completed work or user-entered data lost when containers are stopped and rebuilt: 0. Full "
     "backup shall be a file copy.",
     "0. The image holds no state; database, figures, job logs, manifests, inference outputs and "
     "cached weights all live on bind-mounted host directories. A job that was running at shutdown "
     "does not resume and must be re-run from the queue."],
    ["NFR7", "Reproducibility",
     "Given identical inputs, variation in the generated training manifest, the preview slide "
     "selection, and the region-of-interest ranking: 0.",
     "0. The manifest is a deterministic normalisation of the source CSV; preview selection is "
     "seeded by model "
     "identity; region ranking is deterministic. The exact command issued to each pipeline is "
     "stored with the run."],
    ["NFR8", "Deployment portability",
     "Manual steps to a working installation on a new GPU host: <= 3 (clone, edit one environment "
     "file, run the build). CUDA generations supported by the same repository: >= 2.",
     "3 steps. CUDA 12.1 and 11.8 are both supported by changing two build arguments; the PyTorch "
     "wheel index and the FAISS build are exposed the same way."],
    ["NFR9", "Testability",
     "Full automated suite runtime on a laptop with no GPU and no slides: < 10 s. Tests requiring "
     "a GPU, a real slide or a subprocess: 0.",
     "2.6 s for 78 tests (50 backend, 28 frontend). Each backend test gets its own temporary "
     "database; no test loads a machine-learning library."],
    ["NFR10", "Operability without a terminal",
     "User-facing use cases completable entirely in the browser: 100%. Long-running operations "
     "exposing a live log in the interface: 100%.",
     "100% of the twelve user-facing use cases; deployment (UC13) is an operator task and uses a "
     "shell. Every asynchronous job writes a log whose tail is reachable from every surface "
     "showing that job's status."],
    ["NFR11", "Interface responsiveness under analysis load",
     "Encoder passes executed when several panels are rendered for the same model and slide: 1. "
     "Region-of-interest re-selection shall execute with 0 encoder passes.",
     "1 pass, memoised in a 32-entry per-(model, slide) cache. Re-selection is synchronous and "
     "reuses cached coordinates and assignments."],
], widths=[0.45, 1.15, 2.45, 2.85], size=7.5)

doc.add_page_break()

# ==========================================================================
h("2. Logical Architecture and Modular Decomposition", before=0)
# ==========================================================================
para("The system is a client-server application decomposed into layers with a single direction of "
     "dependency. Nothing in a lower layer knows about a higher one.")

figure("fig1_architecture.png",
       "Figure 1 - Logical architecture and physical deployment. Arrows show dependency and data "
       "flow; each shaded region is a separate deployment unit.",
       placeholder="[ FIGURE 1 - TO BE INSERTED ]")

h("2.1 Core modules", before=8, after=4)
bullet("Client (view). ",
       "A Vite + React 18 + TypeScript single-page application styled with Tailwind. It holds no "
       "business logic: it renders server state, submits forms, and polls. Ten page components "
       "behind eleven routes.")
bullet("API layer (controller). ",
       "FastAPI. Fourteen routers, one per resource, each thin: validate the request, call a "
       "service, shape the response. Routers never touch the filesystem or a subprocess directly.")
bullet("Service layer (model). ",
       "Plain Python modules holding all business logic - the path sandbox, the manifest builder, "
       "the TRIDENT and PANTHER subprocess builders, the renderers, the caches, the deletion "
       "cascade. Services do not know that HTTP exists.")
bullet("Worker. ",
       "One background daemon thread that drains the job table and invokes registered handlers. "
       "The handlers are what shell out to the two research pipelines on the GPU.")
bullet("Persistence. ",
       "SQLite for structured metadata; the filesystem for everything heavy (whole-slide images, "
       "feature files, prototype files, rendered figures, job logs).")

h("2.2 Cohesion, coupling, and the interface contract", before=10, after=4)
bullet("High cohesion. ",
       "The API is responsible for routing, validation and persistence, and performs no heavy "
       "computation. The worker is dedicated to executing pipelines and rendering figures, and is "
       "entirely unaware of HTTP requests, sessions or responses.")
bullet("Loose coupling through the jobs table. ",
       "The API and the worker never call one another. The API inserts a row describing the work "
       "to be done; the worker reads it. A GPU failure therefore cannot make the interface "
       "unresponsive - it surfaces as a status and a readable log.")
bullet("A polymorphic job pointer. ",
       "A job row does not know what kind of object it operates on. It carries a (ref_table, "
       "ref_id) pair plus an optional JSON parameter blob. This lets four job types - training, "
       "post-training visualization, on-demand slide rendering, and inference - share one queue, "
       "one worker and one status interface without knowing about each other.")
bullet("A second contract on the client side. ",
       "The file lib/api.ts is the single source of truth for the frontend-backend contract: one "
       "TypeScript interface per response shape and one function per endpoint. Pages import from "
       "it and never call fetch directly, so changing an endpoint without changing this file is a "
       "compile error rather than a runtime surprise.")
h("2.3 REST API specification", before=10, after=4)
para("All endpoints are served under ", ("/api", "c"),
     ". Identifiers are UUID strings. Request and response bodies are Pydantic models, so the "
     "interactive OpenAPI specification at ", ("/docs", "c"),
     " is generated from the same definitions the server validates against. The table below groups "
     "the surface by resource; representative endpoints are shown rather than all 58.")

table([
    ["Router", "Representative endpoints", "Purpose"],
    ["fs",
     "GET /fs/roots · GET /fs/list · GET /fs/csv-count · GET /fs/csv-inspect",
     "Sandboxed directory browsing and CSV diagnostics. Every path passes the allow-list check."],
    ["trident, runs",
     "POST /trident/run · GET /trident/runs · GET /runs/resolve",
     "Launch feature extraction (synchronous), list past runs, and map a features directory back "
     "to the run that produced it."],
    ["splits",
     "POST /splits · GET /splits · GET /splits/{id}",
     "Create and list training manifests. One manifest names every slide of the cohort as "
     "training data. (The route and table retain the name 'splits' from an earlier partitioned "
     "training mode - see the naming note in section 7.2.)"],
    ["panther",
     "POST /panther/single-runs · POST /panther/runs · GET /panther/models",
     "Train one model on the whole dataset; returns model_id + job_id immediately."],
    ["models",
     "GET /models/{id} · PATCH /models/{id} · POST /models/{id}/repick-roi · "
     "POST /models/{id}/select-roi · POST /models/{id}/render-slide · "
     "GET /models/{id}/slide-viz · DELETE",
     "Inspect and edit a model, drive the region-of-interest controls, request an on-demand "
     "per-slide render for the comparison page, and cascade-delete a model with its artifacts."],
    ["datasets, thumbnails",
     "GET /datasets · GET /datasets/{name}/slides · GET /datasets/{name}/models · "
     "GET /slide-thumbnail",
     "Backing lookups for the Model Comparison page: which datasets have models, which slides "
     "exist, and a binary thumbnail per slide for the picker grid."],
    ["labels, notes",
     "GET/POST/DELETE /prototype-labels · GET/POST/PATCH/DELETE /model-notes",
     "Semantic labelling of prototypes and free-text notes on a model."],
    ["inference",
     "POST /inferences · GET /inferences/lookup · GET /inferences/{id}/example-patches · "
     "POST /inferences/{id}/rerun · GET/POST/PATCH/DELETE /inference-notes",
     "Single and batch inference dispatch with a cache pre-check, per-result example patches, "
     "and notes."],
    ["jobs, queue",
     "GET /jobs · GET /jobs/{id} · POST /jobs/{id}/cancel · POST /jobs/{id}/retry · "
     "GET /queue · POST /queue/reorder",
     "The queue surface: list and inspect jobs (including a tail of the live log), cancel a "
     "waiting job, re-run a terminal one, and atomically rewrite the waiting order."],
    ["viz",
     "GET /viz/{file_path} · GET /viz/placeholder/{kind}",
     "Serve a rendered image from one of the two output roots (403 outside them, 404 if missing), "
     "or synthesize a labelled SVG placeholder for a render that does not exist yet."],
], widths=[0.85, 2.5, 3.55], size=8.5)

para(("Status codes carry meaning. ", "b"),
     "403 means a path fell outside the allowed roots. 409 signals a lost race or an invalid state "
     "transition - cancelling a job the worker has already claimed, deleting a model with an "
     "active job, re-picking a region of interest before the panel has been rendered. 422 is a "
     "well-formed request the system cannot satisfy (a slide with no tissue window, a "
     "thumbnail the imaging library could not open). 207 is returned by batch dispatch when some "
     "paths validated and others did not, and the client renders the per-path outcome rather than "
     "treating the whole batch as failed.")

doc.add_page_break()

# ==========================================================================
h("3. Physical Deployment and Infrastructure", before=0)
# ==========================================================================
para("The system is deployed on-premise, inside the hospital's network, with no external internet "
     "access required at run time. It is delivered as two Docker containers orchestrated by a "
     "single Compose file, so the entire installation on a new GPU machine is: clone the "
     "repository, fill in an environment file, and run two commands.")

table([
    ["Container", "Contents", "Exposed"],
    ["frontend",
     "nginx serving the built single-page application, and reverse-proxying /api/* to the backend. "
     "Nothing else - no Node process at run time.",
     "Port 8080 on the host (configurable)."],
    ["backend",
     "A CUDA runtime base image with one shared Python virtual environment containing FastAPI, the "
     "worker, PyTorch, OpenSlide, a GPU build of FAISS, and pinned checkouts of the TRIDENT and "
     "PANTHER repositories baked into the image.",
     "Not published; reached only through the frontend proxy."],
], widths=[0.9, 4.4, 1.6], size=8.5)

para(("GPU access", "b"),
     " is granted through the NVIDIA Container Toolkit and a device reservation in the Compose "
     "file. The CUDA base image and the PyTorch wheel index are build arguments, so the same "
     "repository builds against either a CUDA 12.1 or a CUDA 11.8 driver by changing two lines in "
     "the environment file.")

para(("Storage layout. ", "b"),
     "The container image is disposable; all data and state live on bind-mounted host directories, "
     "split across two physical disks because the render and inference outputs grow much faster "
     "than the database:", space_before=6)

table([
    ["Host location", "Mounted at", "Holds"],
    ["WSI data directory (read-only)", "/data", "Whole-slide images and the manifest CSV. Mounted "
     "read-only so no code path can modify the source cohort."],
    ["Internal disk / db", "/state/db", "bagheera.db - the SQLite database."],
    ["Internal disk / hf_cache", "/state/hf_cache", "Downloaded encoder weights, so a restart does "
     "not re-download them."],
    ["External disk / viz_cache", "/state/viz_cache", "All rendered figures, plus one log file per "
     "job under job_logs/."],
    ["External disk / inference_outputs", "/state/inference_outputs",
     "Per-inference feature files and rendered figures."],
    ["External disk / datasets_splits", "the training pipeline's manifest directory",
     "The generated training manifests, mounted into the exact location the pipeline reads them "
     "from."],
    ["External disk / trident_processed", "/app/backend/trident_processed",
     "TRIDENT feature-extraction outputs for the initial dataset build."],
], widths=[1.85, 1.85, 3.2], size=8.5)

para(("Path configuration. ", "b"),
     "The allow-list that bounds the file browser names ",
     ("container", "i"),
     " paths, and includes both the read-only data mount and the TRIDENT output directory, since "
     "the training form must browse to the features the extraction stage produced. The "
     "host-versus-container path model is documented separately in ",
     ("docs/env-paths.md", "c"), ".")

doc.add_page_break()

# ==========================================================================
h("4. Data Architecture and Schema Design", before=0)
# ==========================================================================
para("The system enforces a strict separation between structured metadata and heavy computational "
     "data. Metadata - runs, manifests, models, labels, notes, jobs - lives in a relational "
     "database. "
     "Whole-slide images, HDF5 feature files, prototype files and rendered figures live on the "
     "filesystem, and the database stores only their paths. This keeps the database small enough "
     "that it is trivially backed up by copying one file.")

h("4.1 Relational database", before=8, after=4)
para("SQLite, accessed through SQLAlchemy 2.0 with typed models. Ten tables carry the system:")

table([
    ["Table", "One row per...", "Notable columns and constraints"],
    ["trident_runs", "one feature-extraction run",
     "dataset_name, wsi_dir, patch_encoder, mag, patch_size, the exact command executed, status, "
     "captured stdout/stderr, output_dir."],
    ["splits", "one training manifest written to disk",
     "split_name (unique), abs_path, source_csv, seed, total_rows. Named 'splits' for historical "
     "reasons (section 7.2)."],
    ["models", "one trained model",
     "The central row - one row per trained model. Naming (base_name, model_name unique, "
     "display_name), inputs "
     "(features_dir, training manifest, trident_run), PANTHER hyperparameters (mode, in_dim, "
     "n_proto, "
     "n_proto_patches, n_init, seed), outcome (status, prototypes_dir), and rendered artifacts "
     "(viz_status, viz_artifacts JSON)."],
    ["panther_runs", "one training subprocess attempt",
     "An execution log: the command, status, return code, stdout, stderr, start and finish times. "
     "Kept even when the model row is updated, so a failure is always inspectable."],
    ["prototype_labels", "one label on one prototype",
     "Unique on (model_id, prototype_index) - a prototype has at most one name."],
    ["model_notes", "one free-text note on a model", "body, created_at, updated_at."],
    ["inference_batches", "a group of inferences submitted together", "model_id, user_label, total_count."],
    ["inferences", "one (model, slide) run",
     "Slide identity (path, filename, mtime, size, sha256 hash), output paths, status. "
     "Unique on (model_id, wsi_hash) - this pair IS the cache key."],
    ["inference_notes", "one free-text note on an inference result", "body, created_at, updated_at."],
    ["jobs", "one asynchronous unit of work",
     "job_type, the polymorphic (ref_table, ref_id) pointer, status, queue_position, log_path, "
     "error_message, and an optional params JSON blob."],
], widths=[1.15, 1.85, 3.9], size=8.5)

para(("Schema lifecycle - a deliberate constraint. ", "b"),
     "There is no migration framework. The schema is created by ",
     ("Base.metadata.create_all()", "c"),
     " at startup, and after a structural change the developer deletes the database file and lets "
     "it recreate. This is acceptable because the database holds derived bookkeeping, not primary "
     "clinical data. For the cases where an existing deployment's data had to survive - adding "
     "columns such as ",
     ("queue_position", "c"), ", ", ("viz_artifacts", "c"), " and ", ("params", "c"),
     " - the convention is a guarded ", ("ALTER TABLE ... ADD COLUMN", "c"),
     " executed inside the startup routine. Four such guards exist today, each documented in the "
     "database reference. This gives the benefit of additive migrations without the weight of a "
     "framework.", space_before=6)

para(("One note for anyone reading the schema directly. ", "b"),
     "The physical schema also contains a model-grouping table and three constant-valued columns "
     "on ", ("models", "c"),
     " carried over from an earlier cross-validation training mode. The current training path "
     "writes fixed values to them and no feature reads them as variables. They are not part of "
     "the design described here and are scheduled for removal; they are noted only so the table "
     "list above can be reconciled against a dump of the live database.", space_before=6)

para(("Concurrency. ", "b"),
     "The database is shared between the HTTP request threads and the worker thread. It runs in "
     "write-ahead-logging mode with a five-second busy timeout, which is what keeps many "
     "concurrent pollers and one occasional writer from producing 'database is locked' errors.")

h("4.2 Filesystem layout", before=10, after=4)
code([
    "${VIZ_CACHE_ROOT}/",
    "  job_logs/{job_id}.log                one append-only log per asynchronous job",
    "  slide_thumbs/{key}.jpg               generated slide-picker thumbnails (content-keyed)",
    "  {model_id}/",
    "    section_a/ section_c/ section_d/   the analysis panels",
    "    violin/                            per-slide prototype-similarity plot",
    "    umap.png                           dataset-wide embedding scatter",
    "    compare/{slide_id}/                on-demand per-slide render + manifest.json",
    "",
    "${INFERENCE_ROOT}/",
    "  {model_id}/{inference_id}/",
    "    custom_list.csv                    the single-slide manifest handed to TRIDENT",
    "    trident_output/.../{slide}.h5      the extracted features",
    "    heatmap_{slide}.png  mixture_{slide}.png  tsne_{slide}.png",
    "    example_patches_{slide}/prototype_{NN}/patch_{NN}.png",
])
para("Rendered artifacts are addressed by absolute path in the database and served through a single "
     "endpoint that re-checks the path against both output roots on every request. Both roots grow "
     "without bound; pruning is a manual operation today and is listed as known work in section 12.")

doc.add_page_break()


doc.add_page_break()

# ==========================================================================
h("5. Pipeline Integration and Parameter Control", before=0)
# ==========================================================================
para("Bagheera drives two upstream research pipelines from the Mahmood Lab. Neither was modified; "
     "both are invoked as subprocesses through thin bash wrappers, so the exact upstream "
     "invocation stays visible and auditable. The value the system adds is that every parameter of "
     "each pipeline is set in ", ("one place", "i"),
     ", validated before submission, derived where it is derivable, and recorded with the run.")

table([
    ["Pipeline", "Role", "Invocation"],
    ["TRIDENT", "Segments tissue, tiles each whole-slide image into patches, and encodes every "
                "patch into a feature vector. Produces one HDF5 file per slide.",
     "bash run_trident.sh -> run_batch_of_slides.py"],
    ["PANTHER", "Fits an unsupervised mixture model over the patch features of a cohort, producing "
                "prototypes and per-slide mixture weights.",
     "bash run_panther.sh -> python -m training.main_prototype, with cwd and "
     "CUDA_VISIBLE_DEVICES set by the caller"],
], widths=[0.8, 3.8, 2.3], size=8.5)

h("5.1 TRIDENT - one configuration surface for feature extraction", before=10, after=4)
para("The extraction form asks the user for three things and derives everything else. Derived "
     "values are displayed as locked, read-only fields rather than hidden, so the user can see "
     "exactly what will run without being able to produce an inconsistent combination.")

table([
    ["Parameter", "Set by", "Value and rule"],
    ["Dataset name", "User", "Free text validated against ^[A-Za-z0-9_-]+$. Re-validated "
     "server-side before it is interpolated into any command."],
    ["WSI directory", "User", "Chosen with the sandboxed directory browser; must resolve inside "
     "the configured allow-list."],
    ["Patch encoder", "User", "One of uni_v1, uni_v2, phikon, phikon_v2."],
    ["Task", "Derived - locked", "Always 'all' (segmentation, tiling and encoding in one pass)."],
    ["Magnification", "Derived - locked", "20x."],
    ["Patch size", "Derived from encoder - locked", "256 px for uni_v1 / uni_v2, 224 px for "
     "phikon / phikon_v2. It is a property of the encoder, not a choice."],
    ["Job directory", "Derived - locked", "./trident_processed/{dataset_name}."],
    ["Output directory", "Derived - locked",
     "{job_dir}/{mag}x_{patch_size}px_0px_overlap/features_{encoder}. Computed by the same "
     "function the server uses, so the client preview and the server agree by construction."],
], widths=[1.3, 1.5, 4.1], size=8.5)

para(("Command preview. ", "b"),
     "The form renders a live, copyable preview of the exact argument vector that will be "
     "executed, mirroring the server's own builder. On submission the command is stored on the "
     "run row alongside its status, return code, and captured output, so any dataset can be traced "
     "back to the invocation that produced it.")

h("5.2 PANTHER - one hyperparameter surface for training", before=10, after=4)
para("The training form binds a feature directory to the extraction run that produced it, selects "
     "or creates a training manifest, and carries every PANTHER hyperparameter. Nothing about the "
     "run is "
     "configured anywhere else.")
para(("Every hyperparameter from ", "b"), ("mode", "c"), (" downward is user-adjustable on this "
     "form; the values shown are the defaults the form opens with. ", "b"),
     ("in_dim", "c"),
     " is the one exception: it is derived from the encoder and locked, because it is a fixed "
     "property of the extracted features rather than a choice.", space_before=4)

table([
    ["Parameter", "Default", "Meaning and rule"],
    ["Features directory", "-", "Typed or browsed; a debounced lookup resolves it back to its "
     "TRIDENT run and dataset. Everything below is gated on that resolution succeeding."],
    ["Model name", "-", "Validated against the model-name pattern; a random suffix is appended "
     "server-side so names never collide."],
    ["Training manifest", "-", "Either built from a source CSV or chosen from those already "
     "created for that dataset. Building one selects it automatically."],
    ["mode", "faiss  (adjustable)", "Clustering backend: 'faiss' (GPU) or 'kmeans' "
     "(scikit-learn)."],
    ["in_dim", "derived - locked", "Feature width. Auto-filled from the resolved encoder "
     "(uni_v1 1024, uni_v2 1536, phikon / phikon_v2 768) and locked, because it is a fixed "
     "property of the features rather than a tunable. The server overrides whatever the client "
     "sends with the value implied by the encoder, so a stale form cannot train at the wrong "
     "dimension."],
    ["n_proto", "16  (adjustable)", "Number of prototypes to fit - the cluster count of FR4. "
     "The single most consequential setting: it decides how finely the tissue is partitioned."],
    ["n_proto_patches", "1 000 000  (adjustable)", "Patches sampled to fit the prototypes. Trades "
     "fitting time against how much of the cohort the fit sees."],
    ["n_init", "5  (adjustable)", "Clustering initialisations; more reduces the chance of a poor "
     "local optimum at the cost of time."],
    ["num_workers", "10  (adjustable)", "Data-loading workers."],
    ["seed", "1  (adjustable)", "PANTHER's own seed, independent of the manifest's provenance "
     "seed, so a cohort can be held fixed while the fit is repeated."],
], widths=[1.25, 0.95, 4.7], size=8.5)

para(("Input handling. ", "b"),
     "Numeric fields keep a local text buffer and clamp to their range only on blur, so a field "
     "can be cleared or edited mid-value without the cursor fighting the user. As with extraction, "
     "the form renders a live command preview built from the same rules the server applies.")

h("5.3 The clustering PANTHER produces", before=10, after=4)
para("Training fits an unsupervised mixture model over the patch feature vectors named by the "
     "training manifest. It requires no labels and no annotated regions. Its outputs are:")
bullet("Prototype centres. ",
       "n_proto vectors in feature space, each representing a recurring tissue morphology, "
       "persisted as a prototype file next to the run.")
bullet("Per-patch assignments. ",
       "Every extracted patch of every slide is assigned to the prototype it most resembles, so "
       "the tissue of a slide is partitioned into clusters with known spatial coordinates.")
bullet("Per-slide mixture weights. ",
       "For each slide, the proportion of its tissue attributable to each prototype. The weights "
       "sum to one, which is what makes a slide comparable to another slide as a distribution "
       "rather than as an image.")
bullet("A stable prototype index. ",
       "Prototypes are addressed as C1..Cn. Every colour, every panel, and every user-assigned "
       "label in the system refers to that index, so a name given to C3 means the same thing in "
       "the assignment map, the dictionary and the mixture chart.")
para("These three artifacts - centres, assignments and weights - are the input to everything in "
     "section 6.")

doc.add_page_break()

# ==========================================================================
h("6. Visualization and Model Analysis", before=0)
# ==========================================================================
para("Clustering output is only useful if it can be read. The analysis layer renders a trained "
     "model as three panels plus a per-slide similarity plot, mirroring the figure layout of the "
     "PANTHER paper, together with a set of interactive controls and a comparison view. All rendering happens once, asynchronously, "
     "after training succeeds; the results are stored as image files with their paths recorded on "
     "the model, so opening a model later is a page load rather than a computation.")

para(("A cost decision that shapes the whole layer. ", "b"),
     "Producing the per-patch assignments for one slide means running the encoder over that "
     "slide's features. Rendering four panels naively would run it four times. Instead a single "
     "pass is computed and memoised per (model, slide) pair in a 32-entry cache, and every panel "
     "for that slide is painted from it (NFR11).")

h("6.1 Section A - prototype assignment on the slide", before=10, after=4)
para("The lead panel answers 'what did the model find, and where'. It is rendered for one "
     "deterministically chosen slide of the cohort.")
table([
    ["Element", "What it shows"],
    ["Whole-slide thumbnail", "The H&E slide downscaled to a longest side of 2048 px, with a "
     "physical scale bar derived from the slide's embedded microns-per-pixel. If the slide carries "
     "no resolution metadata the thumbnail renders without the bar rather than failing."],
    ["Prototype assignment map", "Every extracted patch painted in its prototype's colour and "
     "composited over the slide, at a high enough resolution to stay sharp when zoomed. Patches "
     "are tiled on the true level-0 patch pitch, so the colouring is contiguous rather than a "
     "checkerboard, and each patch carries a thin border in the style of the paper figure."],
    ["Mixture-weight chart", "One bar per prototype, labelled C1..Cn and coloured with the same "
     "map as the assignment image, showing the proportion of tissue each prototype accounts for."],
    ["Region of interest", "A magnified 16x16-patch window of the slide, shown twice: the raw H&E "
     "crop with a scale bar, and the same window tiled with each patch tinted by its prototype. "
     "This is the view that makes a cluster interpretable as a morphology."],
], widths=[1.5, 5.4], size=8.5)

h("6.2 Prototype similarity within a slide", before=10, after=4)
# ==========================================================================
para("Section A shows which prototype each patch was assigned to, but not how confidently. This "
     "panel answers that: for each prototype, a violin plot of the cosine similarity between every "
     "patch assigned to it and that prototype's fitted centre, coloured with the same map as the "
     "assignment image and annotated with the patch count per prototype.")
para("A tight, high distribution means the prototype describes a coherent, well-separated "
     "morphology. A broad or low one means the cluster is absorbing patches that do not really "
     "resemble its centre - a signal that the prototype count may be too low, or that the cluster "
     "is capturing an artifact rather than a tissue pattern. Read alongside the mixture-weight "
     "chart, it separates a prototype that is genuinely common from one that is merely a "
     "catch-all.")

h("6.3 Section C - the embedding, abstract and on the tissue", before=10, after=4)
para("Two views of the same structure, side by side.")
bullet("Abstract scatter. ",
       "A dataset-wide two-dimensional embedding of sampled patch features, showing how the "
       "clusters sit relative to one another in feature space. Sampling is capped so the cost "
       "stays bounded on large cohorts.")
bullet("On-tissue map. ",
       "For a single slide, a two-dimensional embedding is fitted and each patch is coloured by a "
       "bivariate colour map - one embedding axis driving one hue, the second driving another, "
       "with a legend rendered into the corner. Those colours are painted back onto the slide at "
       "each patch's true position. Where the assignment map shows discrete cluster membership, "
       "this shows continuous similarity, so gradual morphological transitions become visible "
       "where a hard assignment would hide them.")

h("6.4 Section D - the prototype dictionary", before=10, after=4)
para("One column per prototype, C1 through Cn, each headed in that prototype's colour and "
     "containing its most representative patches - the patches across the whole cohort whose "
     "features sit closest to that prototype's centre. This is the panel that answers 'what does "
     "C4 actually look like', and it is where the user types the biological name for the cluster. "
     "Every prototype gets a column even if no patch was assigned to it, so a dead cluster is "
     "visible rather than silently missing.")
para("The label box under each column writes directly to the stored prototype label, so naming a "
     "cluster here immediately renames it everywhere it appears.")

h("6.5 Interactive controls", before=10, after=4)
bullet("Zoom and pan. ",
       "Every rendered image is wrapped in a viewer supporting wheel zoom, drag pan, and explicit "
       "zoom and reset controls. No external image library is used.")
bullet("Region-of-interest re-selection. ",
       "The default region is chosen automatically (section 7.3). 'Re-pick' advances to the next "
       "ranked candidate window; 'Select' arms the assignment map as a point picker, so a click "
       "anywhere on the slide re-renders the region around that point. Both are synchronous and "
       "reuse cached assignments, so neither re-runs the encoder.")
bullet("Prototype labelling. ",
       "Names are saved on blur with per-field save state, and are visible in every panel.")
bullet("Graceful degradation. ",
       "No image is assumed to exist. Any path that is missing or not yet rendered resolves to a "
       "labelled placeholder, so a model that is halfway through rendering shows a coherent page.")

h("6.6 Model comparison", before=10, after=4)
para("Different hyperparameters produce different clusterings of the same tissue, and the only "
     "honest way to judge them is to look at the same slide through each. The comparison view is a "
     "strict top-down gate - choose a dataset, then a slide from a thumbnail grid, then up to four "
     "models - and renders a column per model containing that slide's assignment panel, its "
     "per-slide similarity violin, its on-tissue embedding, and its prototype dictionary. One to "
     "three models lay out as a row; four wrap into a two-by-two grid.")
para(("Synchronised navigation. ", "b"),
     "A toggle lifts a single zoom-and-pan transform into the page and feeds it to the matching "
     "image in every column, so panning to a region of interest in one panel moves every other "
     "panel to the same region at the same magnification. Without it, comparing two clusterings at "
     "the same location is manual and error-prone.")
para(("Cost. ", "b"),
     "Per-slide renders are computed on demand through the same single worker and queue as "
     "everything else, cached on disk by (model, slide), and served directly on a second visit. "
     "The dataset-wide panels - the prototype dictionary and the abstract scatter - are rendered "
     "once at training time and are not recomputed per slide.")

h("6.7 Inference visualizations", before=10, after=4)
para("Applying a trained model to a new slide produces its own render set: the prototype "
     "assignment heatmap for that slide, its mixture-weight plot, a grid of example patches "
     "grouped by prototype (with a lightbox for full-size inspection and the user's prototype "
     "names attached), and a per-slide t-SNE projection. The dataset-wide dictionary and embedding "
     "from training are shown alongside as reference, so a new slide can be read against the "
     "cohort the model was fitted on.")
# ==========================================================================
h("7. Algorithm Descriptions", before=0)
# ==========================================================================
para("Four algorithms carry most of the system's non-obvious behaviour: the queue, the "
     "manifest builder, the "
     "generator, the region-of-interest selection, and the two caches.")

h("7.1 Queue management", before=8, after=4)
para(("Plain-English description.", "b"))
numbered("1. The jobs table is the queue. A new job is inserted with status 'queued' and a "
         "queue_position one greater than the current maximum, which yields first-in-first-out "
         "ordering by default.")
numbered("2. A single worker thread wakes every two seconds and selects the queued job with the "
         "lowest queue_position.")
numbered("3. It claims that job with a conditional update: set status to 'running' only where the "
         "status is still 'queued'. If zero rows change, a user cancelled the job in the "
         "meantime, so the worker moves on to the next one.")
numbered("4. On claiming, queue_position is cleared - the job has left the waiting line.")
numbered("5. The worker dispatches to the handler registered for the job's type and runs it to "
         "completion. Everything the handler prints is streamed to a per-job log file.")
numbered("6. On return, the job is marked 'succeeded'. On any exception, the traceback is written "
         "to the log and the job is marked 'failed' with the error message stored on the row. "
         "The loop continues either way; the worker never dies.")
numbered("7. A handler may enqueue further work. Training enqueues a visualization job on success, "
         "which re-enters the same queue at the tail.")
numbered("8. A user may cancel a waiting job (the same conditional update in reverse), drag to "
         "reorder the waiting jobs (an atomic rewrite of queue_position for the whole waiting "
         "set), or re-run a terminal job (which re-enters at the tail).")

para(("Pseudocode.", "b"), space_before=6)
code([
    "// The worker loop - one thread, one job at a time.",
    "function workerLoop(stopEvent):",
    "    while not stopEvent.isSet():",
    "        job = claimNextJob()",
    "        if job is null:",
    "            wait(POLL_INTERVAL = 2s); continue",
    "        runOneJob(job)",
    "",
    "function claimNextJob():",
    "    loop:",
    "        job = SELECT * FROM jobs WHERE status='queued'",
    "                ORDER BY queue_position, created_at LIMIT 1",
    "        if job is null: return null",
    "        // compare-and-swap: the database decides who wins the race",
    "        n = UPDATE jobs SET status='running', started_at=now(), queue_position=NULL",
    "              WHERE id=job.id AND status='queued'",
    "        if n == 1: return job",
    "        // n == 0 -> cancelled a moment ago; try the next one",
    "",
    "function runOneJob(job):",
    "    log = openLog(job.logPath)",
    "    try:",
    "        handler = HANDLERS[job.jobType]      // panther_train | post_train_viz",
    "        handler(db, job, log)                //   | render_slide | inference",
    "        job.status = 'succeeded'",
    "    catch anyError as e:                     // the worker must never crash",
    "        log.write(traceback())",
    "        job.status = 'failed'; job.errorMessage = truncate(e, 2000)",
    "    finally:",
    "        job.finishedAt = now(); log.close()",
    "",
    "// User-initiated transitions, both compare-and-swap.",
    "function cancel(jobId):",
    "    n = UPDATE jobs SET status='canceled', finished_at=now(), queue_position=NULL",
    "          WHERE id=jobId AND status='queued'",
    "    if n == 0: return HTTP 409   // the worker already started it",
    "",
    "function reorder(orderedIds):                // atomic, in one transaction",
    "    queued = SELECT * FROM jobs WHERE status='queued'",
    "    pos = 1",
    "    for id in orderedIds:  if id in queued: queued[id].position = pos++",
    "    for job in queued not yet assigned:      // keep their relative order at the back",
    "        job.position = pos++",
])

figure("fig2_sequence.png",
       "Figure 2 - Sequence: submitting a PANTHER training run. The HTTP request completes "
       "before any GPU work begins; the jobs table is the only channel between the API and the worker.")

para(("Why the work is run to completion inside the claiming thread. ", "b"),
     "An alternative is to fire each job asynchronously and have a second worker poll the operating "
     "system for completion. That design suits a machine that can run several jobs at once. With a "
     "single GPU it buys nothing and costs a great deal: process handles must be tracked across "
     "restarts, a crashed subprocess leaves a job permanently 'running', and the two workers race "
     "over the same rows. Running each job to completion inside the thread that claimed it removes "
     "all of that. The cost is stated plainly in section 14: a running job cannot be interrupted.")

para(("Complexity.", "b"), space_before=6)
bullet("Claiming a job: ", "one indexed SELECT plus one conditional UPDATE, so O(log n) in the "
       "number of queued rows. The retry loop iterates only when a cancellation wins a race, which "
       "is bounded by the number of cancellations, not by queue length.")
bullet("Reordering: ", "O(m) for m waiting jobs, in a single transaction.")
bullet("Building the queue view: ", "O(w + r) for w waiting jobs and r recent jobs, where r is "
       "capped at 20.")
bullet("Memory: ", "O(1) auxiliary. The queue holds job metadata only - identifiers, statuses, "
       "paths. Feature vectors and images are never loaded into the queue layer; the handler reads "
       "them, and they are released when the job ends.")

h("7.2 Training-manifest generation", before=10, after=4)
# ==========================================================================
para("Training needs a file that names the slides to fit on, in the exact layout and location the "
     "pipeline reads. Producing it from a user's source CSV is the job of this step.")

para(("A note on naming. ", "b"),
     "The HTTP resource, the database table and the on-disk directory are all named ",
     ("splits", "c"),
     ", and the training pipeline is invoked with a ", ("--split_dir", "c"),
     " argument. Those names date from an earlier mode that partitioned a cohort into training and "
     "held-out sets. The current system fits one model on the entire dataset, so nothing is "
     "partitioned and the artifact is, precisely, a ", ("training manifest", "i"),
     ". This document uses the accurate term throughout; the identifiers are recorded here so that "
     "the prose can be matched to the code and to the upstream pipeline's own argument names.")

para(("What the step does.", "b"), space_before=6)
bullet("Detects the slide-identifier column. ",
       "Matched case-insensitively against a known set of column names. If none is present the "
       "request is rejected with a 400 before anything is written, rather than handing the "
       "pipeline a file it cannot read.")
bullet("Normalises the identifiers. ",
       "A trailing .tif or .tiff is stripped from each value, because the pipeline matches feature "
       "files by bare slide stem. The source CSV, which sits on a read-only mount, is never "
       "modified - normalisation happens on the way out.")
bullet("Writes the manifest. ",
       "Every data row is written to train.csv. Header-only val.csv and test.csv are written "
       "alongside it so that any downstream glob in the upstream pipeline still resolves; they "
       "carry no rows, because no slide is held out.")
bullet("Records provenance. ",
       "A metadata file captures the source CSV, the row count, the detected identifier column, "
       "whether normalisation was applied, and a user-supplied seed. The seed does not shuffle "
       "anything - with every slide used for training there is nothing to shuffle - it is carried "
       "for provenance and appears in the generated directory name, which also takes a random "
       "suffix so repeated builds from the same CSV never overwrite one another.")

para(("Why this small step earns a section. ", "b"),
     "Every training failure traced back to input data during development originated here: an "
     "identifier column under an unexpected name, or file extensions the pipeline would not match. "
     "Both are now caught before a job is ever queued, which is why the failure modes in section "
     "10.2 contain no entry for a malformed manifest.")

h("7.3 Region-of-interest selection", before=10, after=4)
para("The lead analysis panel reproduces the PANTHER paper's figure: a magnified square region of "
     "the slide shown twice, once as raw tissue and once tiled with each patch tinted by the "
     "prototype it was assigned to. Choosing which region to show is not obvious, and the "
     "algorithm went through several corrections against real slides.")
bullet("Candidate windows. ",
       "Non-overlapping windows of 16 x 16 patches are enumerated over the slide's patch "
       "coordinates and ranked by occupancy (how many grid cells actually contain an extracted "
       "patch), then by prototype diversity, then by density. Ranking by diversity first was the "
       "original approach and it consistently landed on tissue boundaries that were half "
       "background; occupancy-first lands in the middle of dense tissue and produces the packed "
       "tiling the paper shows.")
bullet("The true patch pitch. ",
       "Patches are not necessarily laid out on the stored patch size. A dataset that extracts "
       "256-pixel patches at half the base magnification places them on a 512-pixel grid at "
       "level 0. Tiling on the stored size therefore painted only every other cell. The pitch is "
       "now derived as the statistical mode of the gaps between adjacent coordinates, which is "
       "robust to stray off-grid patches.")
bullet("Framing. ",
       "The tissue bounding box is computed from the 1st and 99th percentiles of the patch "
       "coordinates rather than their raw minimum and maximum, so a handful of artifact patches "
       "in the corners of the glass cannot stretch the default view across empty slide.")
bullet("Two user controls. ",
       "'Re-pick' advances to the next-ranked window, wrapping around. 'Select' arms the image "
       "viewer as a point picker: the user clicks anywhere on the assignment map, the click is "
       "reported as a normalised coordinate pair, and the server renders the window containing "
       "that point - or, if the click landed on a gap, the window whose centre is nearest. Both "
       "operations are synchronous and re-use a cached array of coordinates and assignments, so "
       "neither re-runs the encoder.")

h("7.4 Caching", before=10, after=4)
bullet("Inference cache (persistent). ",
       "A slide is identified by the SHA-256 of its bytes, streamed in one-megabyte chunks. "
       "Modification time and size are checked first as a cheap pre-filter, but the hash is the "
       "source of truth, and (model_id, hash) is a unique constraint in the database. Submitting a "
       "slide that has already been processed by that model returns the existing result instead of "
       "recomputing it; the user can override this per file with a 're-run' toggle.")
bullet("Assignment cache (in-memory). ",
       "Rendering several panels for the same (model, slide) pair would otherwise run the encoder "
       "once per panel. A process-local, thread-safe cache of the last 32 encoder passes, keyed by "
       "model and slide, is consulted first. The key is model-scoped deliberately - each model has "
       "its own prototypes, so assignments must never be shared between models. Locking is "
       "per-key, so a miss on one slide never blocks another, and two concurrent renders of the "
       "same slide compute once. The dataset-wide renderers deliberately bypass this cache: they "
       "stream every slide's features once and would evict everything useful.")

doc.add_page_break()

# ==========================================================================
h("8. Use Case Analysis and System Interactions", before=0)
# ==========================================================================
para("Thirteen use cases define the system's behaviour. Twelve are driven by the pathologist or "
     "researcher from the browser; the thirteenth is the operator task of deploying and "
     "configuring the stack.")

figure("fig3_usecase.png", "Figure 3 - Use-case model.", width=6.0)

table([
    ["ID", "Use case", "Primary flow"],
    ["UC1", "Extract features (TRIDENT)",
     "The user names a dataset, browses to a directory of slides, and picks a patch encoder. "
     "Locked fields (task, magnification, patch size derived from the encoder) are shown read-only "
     "alongside a live preview of the exact command. Submission blocks until extraction finishes."],
    ["UC2", "Build a training manifest",
     "The user browses to a manifest CSV. The system reports its row count and diagnostics "
     "(columns present, whether a slide-identifier column exists, how many values carry a .tif "
     "suffix), then writes the validated manifest to disk."],
    ["UC3", "Train a PANTHER model",
     "The user binds a features directory to its extraction run, chooses or builds a training "
     "manifest, sets "
     "hyperparameters, and submits. The response is immediate; the browser navigates to the new "
     "model's page and polls while the worker trains it and then renders its panels."],
    ["UC4", "Browse and manage models",
     "A filterable card grid over all trained models, with search, dataset filter, sort, and a "
     "favourites-only toggle."],
    ["UC5", "Inspect a model",
     "Four analysis panels. Section A: whole-slide thumbnail with a scale bar, the prototype "
     "assignment map, the mixture-weight bar chart, and the region of interest. The per-slide "
     "prototype-similarity violin. Section C: an on-tissue two-dimensional embedding map beside "
     "the abstract scatter. "
     "Section D: the prototype dictionary - one column per prototype showing its most "
     "representative patches in that prototype's colour."],
    ["UC6", "Re-pick or click-select a region of interest",
     "See section 7.3. Both controls update the stored panel and return the new artifact paths."],
    ["UC7", "Label prototypes and take notes",
     "A name box under each prototype column, saved on blur, plus a notes thread on the model and "
     "on each inference result."],
    ["UC8", "Compare models on one slide",
     "A strict top-down gate: choose a dataset, then a slide from a thumbnail grid, then up to "
     "four models. Each column renders that slide through its model. A synchronise toggle lifts a "
     "single zoom/pan transform and feeds it to the matching image in every column, so the same "
     "tissue is compared at the same magnification."],
    ["UC9", "Run inference on new slides",
     "Single or batch. Each selected path is checked against the cache before submission and "
     "marked as cached or to-be-processed, with a per-path re-run override. Results show the "
     "assignment heatmap, mixture plot, example patches with a lightbox, and a t-SNE projection."],
    ["UC10", "Manage the job queue",
     "A shared page showing the running job, the waiting list (draggable, each cancellable) and "
     "recent terminal jobs (each re-runnable). Polling is frozen while a drag is in progress so "
     "the row under the cursor cannot jump."],
    ["UC11", "Read a job log",
     "Every job status surface exposes a log link that opens the tail of that job's log file in a "
     "modal, refreshing while the job is in flight."],
    ["UC12", "Delete a model",
     "Removes the model's database rows in dependency order within one transaction plus the "
     "on-disk artifacts, refusing with a 409 if a job is currently running against it. Shared "
     "manifests and extraction runs are left untouched (section 14 records the current scope of "
     "this operation)."],
    ["UC13", "Deploy and configure",
     "The operator fills in the environment file, sets the allow-list of browsable container "
     "paths, and runs the build. Verification steps are documented."],
], widths=[0.45, 1.55, 4.9], size=8.5)

doc.add_page_break()

# ==========================================================================
h("9. Programming Languages, Tools, and Standards", before=0)
# ==========================================================================
table([
    ["Concern", "Choice"],
    ["Backend language", "Python 3.10+ (postponed annotation evaluation used throughout)"],
    ["Web framework", "FastAPI 0.115 on Uvicorn 0.32"],
    ["ORM and database", "SQLAlchemy 2.0 with typed models; SQLite in write-ahead-logging mode"],
    ["Validation", "Pydantic 2.10"],
    ["Frontend", "React 18, TypeScript 5.7 (strict), Vite 5, Tailwind CSS 3.4, React Router 6"],
    ["Frontend data layer", "The platform fetch API only - no Axios, React Query or SWR, and no "
     "state-management library. Local component state and polling."],
    ["Machine learning", "PyTorch, OpenSlide, h5py, scikit-learn, UMAP, Matplotlib, a CUDA build "
     "of FAISS - all imported lazily inside the functions that need them"],
    ["Testing", "pytest with FastAPI's TestClient (backend); Vitest with React Testing Library and "
     "jsdom (frontend)"],
    ["Packaging and deployment", "Docker and Docker Compose; nginx for static serving and proxying"],
    ["Version control", "Git. Feature branches and structured commit messages that state the "
     "problem, the root cause and the fix."],
], widths=[1.5, 5.4], size=9)

para(("Coding standards enforced across the project:", "b"), space_before=8)
bullet("Lazy heavy imports. ",
       "PyTorch, OpenSlide, h5py and the plotting stack are imported inside functions, never at "
       "module scope. The API boots on a machine with no GPU and no machine-learning dependencies "
       "installed, which is what made laptop development and dependency-free tests possible.")
bullet("One security primitive, used everywhere. ",
       "Every route that accepts a path calls the same resolution function. There is no second way "
       "to open a user-supplied file.")
bullet("The worker catches everything. ",
       "No handler exception may escape to the loop.")
bullet("The API client comes first. ",
       "A new endpoint is added to the typed client before any page uses it.")
bullet("Design tokens only. ",
       "Structural UI elements use semantic tokens (surface, ink, border, accent) rather than "
       "hard-coded colours, so the palette was changed once, globally, when the product was "
       "re-branded.")
bullet("Documentation is part of the change. ",
       "Each subsystem owns a reference document, and the convention is that a code change and its "
       "document change land together.")

para(("Tooling note.", "b"), " The repository carries a set of agent definitions under ",
     (".claude/agents/", "c"),
     ", one per subsystem, each bound to the reference document it owns. This was how "
     "documentation was kept synchronised with a fast-moving codebase across a three-month build.",
     space_before=6)

para(("Mentoring and review. ", "b"),
     "The academic supervisor oversaw methodology; the upstream pipelines are the published work "
     "of the Mahmood Lab at Harvard Medical School, and their repositories are the reference "
     "against which the integration was validated.")

doc.add_page_break()

# ==========================================================================
h("10. Testing Framework and Failure Modes", before=0)
# ==========================================================================
para("Testing is split so that system logic can be verified with no GPU, no machine-learning "
     "dependencies and no real slides. All 78 automated tests run in under three seconds on a "
     "laptop.")

table([
    ["Suite", "Count", "Scope"],
    ["Backend - pytest", "50",
     "Route-level tests through FastAPI's TestClient against a temporary SQLite database, plus "
     "pure-function tests. Every test gets its own database file; no shared mutable state."],
    ["Frontend - Vitest", "28",
     "Pure helpers and controlled-component behaviour, mounted with React Testing Library where "
     "interaction matters."],
], widths=[1.5, 0.6, 4.8], size=9)

para(("Testing principles.", "b"), space_before=6)
bullet("Test the logic, not the wiring. ", "Path resolution, manifest invariants, cache semantics and "
       "queue state transitions are the highest-value targets.")
bullet("No GPU, no heavy imports, no subprocesses. ",
       "Because the machine-learning imports are lazy, a test that never enters a render path "
       "never loads PyTorch. Subprocess boundaries are stubbed.")
bullet("Isolated state. ", "Temporary directories and temporary databases per test; no sleeping.")
bullet("A bug fix ships with a regression test. ",
       "For example, the region-of-interest containment and nearest-window fallback rules each "
       "have a direct unit test.")

h("10.1 Test-case trace table", before=10, after=4)
para("Representative rows from the implemented suites. Where an automated test covers the row, "
     "the last column names it, so the case is executable rather than aspirational. Two queue "
     "rows have no unit test: the compare-and-swap races were verified by construction and "
     "exercised manually with two browser tabs, as recorded in the queue design document.")

table([
    ["TC", "Module", "Scenario", "Expected result", "Automated test / verification"],
    ["TC-01", "Queue / worker", "A job is cancelled in the instant the worker claims it",
     "Exactly one side wins. The conditional update matches zero rows for the loser; the cancel "
     "call returns 409 and the job runs, or the job never starts.",
     "Verified by construction of the compare-and-swap claim; exercised manually with two "
     "browser tabs."],
    ["TC-02", "Queue", "Waiting jobs are dragged into a new order",
     "Positions are rewritten atomically; jobs that changed status mid-reorder are ignored and "
     "unnamed jobs keep their relative order at the back.", "POST /api/queue/reorder"],
    ["TC-03", "Jobs", "A job carries per-job parameters through the queue",
     "The params blob round-trips from enqueue to handler unchanged.",
     "test_enqueue_job_params_roundtrip"],
    ["TC-04", "Manifest builder", "A training manifest is built from a source CSV",
     "Every data row lands in train.csv; val and test are header-only; the directory name "
     "matches alltrain_seed_{seed}_{rand8}; metadata records the source CSV, the row count, the "
     "seed and the detected identifier column.",
     "test_single_split_all_rows_in_train, test_single_split_name_pattern, "
     "test_single_split_metadata"],
    ["TC-05", "Manifest builder", "The CSV has no slide-identifier column",
     "The request is rejected before anything is written.",
     "test_single_split_rejects_missing_slide_id, test_single_split_rejects_empty"],
    ["TC-06", "Manifest builder", "Slide identifiers carry a .tif suffix",
     "The suffix is stripped in the generated CSVs; the source CSV is untouched.",
     "test_single_split_strips_tif"],
    ["TC-07", "Filesystem sandbox", "A path outside the allowed roots is requested",
     "403 Forbidden, before any file is opened.", "test_403_outside_roots"],
    ["TC-08", "Thumbnails", "A slide the imaging library cannot open",
     "422, and the picker falls back to an icon rather than breaking the grid.",
     "test_generation_path_422_on_openslide_failure"],
    ["TC-09", "Thumbnails", "The same slide is requested twice",
     "The cache key is deterministic, so the second request is served from disk.",
     "test_cache_key_deterministic"],
    ["TC-10", "PANTHER training", "A single run is submitted",
     "Exactly one model row is created; a mismatched dataset or an "
     "unresolvable features directory is rejected.",
     "test_single_run_creates_one_model_no_group, test_single_run_rejects_dataset_mismatch, "
     "test_single_run_rejects_bad_features_dir"],
    ["TC-11", "Per-slide render", "A slide is requested for the comparison page",
     "A cached manifest returns 'ready' with no job; otherwise a render job is enqueued. A "
     "missing feature file or a malformed slide identifier is rejected with 422.",
     "test_render_slide_ready_on_cached_manifest, test_render_slide_enqueues_when_no_manifest, "
     "test_render_slide_422_when_h5_absent, test_render_slide_422_on_bad_slide_id"],
    ["TC-12", "Region of interest", "The user clicks a point on the assignment map",
     "The window containing the point is chosen; a click on a gap falls back to the nearest "
     "window centre; out-of-range coordinates are clamped.",
     "test_render_roi_at_point_containment, test_render_roi_at_point_nearest_fallback, "
     "test_render_roi_at_point_clamps_out_of_range"],
    ["TC-13", "Region of interest", "Selection is attempted before the panel exists",
     "409 Conflict with an explanatory message, not a crash.",
     "test_select_roi_409_when_no_section_a, test_select_roi_409_when_no_compare_manifest, "
     "test_select_roi_409_when_wsi_unavailable"],
    ["TC-14", "Assignment cache", "Several panels render the same (model, slide)",
     "The encoder runs once; the cache evicts past its capacity and never leaks assignments "
     "across models.",
     "test_get_or_compute_calls_compute_only_on_miss, test_lru_eviction_past_cap, "
     "test_per_model_slide_isolation"],
    ["TC-15", "Datasets", "A dataset is offered for comparison only when it carries a model "
     "from the current training path",
     "Datasets without one are not listed, and their slides endpoint returns 404.",
     "test_list_datasets_only_single_models, test_slides_404_when_only_legacy_models"],
    ["TC-16", "Datasets", "The features directory is missing or unreadable",
     "An empty slide list plus an explanatory note - never a 500.",
     "test_slides_missing_features_dir_graceful"],
    ["TC-17", "Frontend - numeric input", "A hyperparameter field is cleared mid-edit",
     "The field can be emptied without the cursor fighting the user; the value clamps to its "
     "range only on blur.",
     "'can be cleared mid-edit...', 'clamps to the range only on blur'"],
    ["TC-18", "Frontend - manifest scope", "The features directory is re-resolved to the same "
     "dataset",
     "The chosen manifest is preserved - the scope key is the dataset name, not the object "
     "identity.",
     "'is STABLE across distinct resolved objects with the same dataset'"],
    ["TC-19", "Frontend - zoom/pan", "A click is mapped to image coordinates under zoom and pan",
     "The transform is inverted correctly and clicks past an edge clamp to the [0,1] range.",
     "'inverts pan and zoom to recover natural coords', 'clamps a click past the left/top edge'"],
    ["TC-20", "Frontend - compare grid", "One to four models are laid out",
     "One to three form a single row; four wrap into a two-by-two grid; overflow is capped.",
     "'wraps 4 models into a 2x2 grid', 'caps at the 2x2 grid for any overflow count'"],
], widths=[0.4, 0.85, 1.5, 2.0, 1.65], size=8)

h("10.2 Failure modes and how the system responds", before=10, after=4)
table([
    ["Failure", "Response"],
    ["A training or rendering subprocess exits non-zero",
     "The traceback is written to the job log, the job is marked failed with the message on the "
     "row, and the model is marked failed. The worker continues with the next job. The user sees "
     "a red pill and a log link."],
    ["A single render inside a multi-render job fails",
     "Each render step is individually guarded, so a partial result still publishes. A missing "
     "panel is simply absent from the artifact manifest, and the interface substitutes a labelled "
     "placeholder."],
    ["A machine-learning dependency is missing from the image",
     "The failure is confined to the render job. Models still train; only the panels are absent. "
     "This is exactly how four missing dependencies were diagnosed and fixed on the GPU box "
     "without the application ever going down."],
    ["A slide has no embedded resolution metadata",
     "The thumbnail renders without a scale bar rather than failing."],
    ["A slide file cannot be found under the recorded directory",
     "The lookup walks the directory subtree by filename stem before giving up, and the affected "
     "panel is skipped with a note in the log."],
    ["A path outside the allowed roots is submitted",
     "403 before any filesystem operation, including when a raw path is pasted into a form."],
    ["The user cancels a job the worker has just claimed",
     "409 with an explanatory message; the job runs to completion. No partial-kill state exists."],
    ["A batch of slides contains some invalid paths",
     "207 Multi-Status; valid paths are queued and invalid ones are reported per path."],
    ["The database is contended",
     "Write-ahead logging plus a five-second busy timeout absorb it."],
], widths=[2.3, 4.6], size=8.5)

doc.add_page_break()

# ==========================================================================
h("11. Monitoring, Troubleshooting, and Integration", before=0)
# ==========================================================================
bullet("User-facing monitoring. ",
       "The queue page is the operational dashboard: what is running now with its elapsed time, "
       "what is waiting and in what order, and the last twenty terminal jobs with their outcome. "
       "Every model and inference additionally carries a status pill and, where relevant, "
       "an inline poller that refreshes the page's data when a job it is watching finishes.")
bullet("Per-job logs. ",
       "Every asynchronous job streams a line-buffered log file, always flushed. The tail is "
       "exposed through the API and rendered in a modal that refreshes while the job is in "
       "flight. This is the primary debugging surface, and it is reachable from every place a "
       "job status is shown, including from a failed model row.")
bullet("Execution records. ",
       "Each training attempt persists its exact command, return code, captured output and "
       "timings in its own table. A failed run remains fully inspectable after the fact.")
bullet("Deliberate degradation. ",
       "The interface never assumes a render exists. Every image path is resolved through a helper "
       "that substitutes a labelled placeholder for a missing or not-yet-rendered artifact, so a "
       "model that is halfway through rendering shows a coherent page rather than broken images.")
bullet("Diagnostics that surface unverified assumptions. ",
       "The slide listing reports how many TRIDENT-written thumbnails were found, so a wrong "
       "assumption about that directory shows up as a visible number rather than as silently "
       "slower thumbnails.")

para(("A symptom-to-cause table for first deployment", "b"),
     " is maintained in the backend operations guide. The recurring causes are: the environment "
     "file not being loaded into the server process; the allow-list naming host paths instead of "
     "container paths; a missing dependency in the shared virtual environment; and an output root "
     "that does not match where the renderers wrote.", space_before=6)

# ==========================================================================
h("12. Documentation Artifacts", before=12)
# ==========================================================================
para("Documentation is versioned with the code, and each document has a single owner subsystem.")
table([
    ["Document", "Contents"],
    ["README.md", "Product overview, screenshots, architecture summary, quick start, credits."],
    ["docs/structure.md", "End-to-end architecture, the domain model, the repository map, and an "
     "explicit statement of what is built versus deferred."],
    ["docs/backend.md", "The working backend reference: stack, every module, the full HTTP API, "
     "the job system, and the deploy-day assumptions to validate."],
    ["docs/frontend.md", "Routing, the typed API client, every page and component, and the "
     "cross-cutting patterns."],
    ["docs/database.md", "The schema, table by table, plus the additive-column convention."],
    ["docs/queue-design.md", "The queue's locked decisions, concurrency model and verification "
     "procedure."],
    ["docs/tests.md", "The testing strategy, fixtures and conventions."],
    ["docs/docker.md", "Host prerequisites, CUDA tag selection, build and run, volume layout, "
     "and a troubleshooting list."],
    ["docs/env-paths.md", "The host-versus-container path model - written because this was the "
     "largest source of deployment confusion."],
    ["docs/test-run.md", "A recorded end-to-end run on the GPU machine."],
], widths=[1.6, 5.3], size=8.5)

# ==========================================================================
h("13. Project Timeline", before=12)
# ==========================================================================
para("The project ran in five phases. Each phase closed with a working increment rather than a "
     "document, so the queue, the analysis layer and the deployment were each exercised before the "
     "next phase depended on them.")

table([
    ["Phase", "Focus", "Delivered"],
    ["1 - Interaction model",
     "Settle the workflow and the data model before committing to GPU integration.",
     "A working interface over a stubbed pipeline: job dispatch, status polling, and the "
     "annotation and comparison surfaces."],
    ["2 - Pipeline integration and the job system",
     "Replace the stub with the real TRIDENT and PANTHER pipelines.",
     "The single configuration surface for each pipeline (section 5), the manifest builder, the "
     "jobs table, and the background worker. The frontend moved to TypeScript."],
    ["3 - Visualization and analysis",
     "Turn clustering output into readable analysis.",
     "The four analysis panels (section 6), the zoom-and-pan viewer, and the region-of-interest "
     "selection algorithm."],
    ["4 - Researcher tools",
     "Let the expert act on what the model found, and control the machine.",
     "Prototype labelling, notes, the shared queue page with cancel and drag-reorder, model "
     "deletion, CSV validation, and the design system."],
    ["5 - Deployment, comparison, and verification",
     "Ship it on the target hardware and prove it works.",
     "Containerized GPU deployment, the Model Comparison view with synchronised navigation, and "
     "the automated test suites."],
], widths=[1.5, 2.2, 3.2], size=8.5)

para(("Effort distribution worth recording. ", "b"),
     "Roughly a third of the engineering effort went into reconciling assumptions about what the "
     "upstream pipelines expect on disk - the directory depth from which manifests are read, the "
     "directory name asserted on before training starts, the GPU-specific clustering library, the "
     "mismatch between the name one pipeline writes and the name the next accepts, and the fact "
     "that feature width is a property of the encoder rather than a hyperparameter. None of these "
     "are visible from reading the published papers. They are called out here because they, rather "
     "than the application code, dominated the schedule.")

# ==========================================================================
h("14. Known Limitations and Future Work", before=12)
# ==========================================================================
para("These are deliberate, documented boundaries rather than defects.")
bullet("No job cancellation once running. ",
       "A single thread cannot interrupt a subprocess cleanly without leaving partial output. "
       "Waiting jobs can be cancelled; running ones are left to finish. Removing this limitation "
       "means replacing the single thread with a real queue and worker pool.")
bullet("Single user, single GPU. ",
       "One worker thread serialises all GPU work. The queue is shared and any user may cancel or "
       "reorder any job, but there is no authentication and no per-user isolation.")
bullet("No authentication or access control. ",
       "Acceptable only because the system is reached over a controlled internal network. "
       "This is the first thing to add before any wider deployment.")
bullet("Output directories grow without bound. ",
       "Rendered figures, job logs and inference outputs are never pruned automatically. A cleanup "
       "endpoint is sketched but not implemented.")
bullet("Slides cannot be uploaded through the browser. ",
       "Files must already exist on the server within an allowed root.")
bullet("Feature extraction blocks its request. ",
       "The initial TRIDENT run is synchronous. It predates the job system and was left that way "
       "because it happens once per dataset; moving it onto the queue is straightforward.")
bullet("No resolution override. ",
       "Slides without embedded physical resolution render without a scale bar; there is no way to "
       "supply the value manually.")
bullet("Model deletion is not yet exposed for every model. ",
       "The cascading delete - database rows in dependency order plus on-disk artifacts - is "
       "keyed on a grouping identifier that the current training path does not populate, so a "
       "model must currently be removed by hand. Re-keying the cascade on the model identifier is "
       "a contained change and is the next item of work.")
bullet("No export. ",
       "Prototype labels, notes and inference results can be read in the interface but not "
       "exported to a file.")
bullet("No held-out evaluation mode. ",
       "Training uses the entire dataset, which is the right default for an unsupervised fit with "
       "no label to validate against. The consequence is that the system reports no held-out "
       "measure of prototype stability; confidence is assessed visually, through the similarity "
       "distributions and by comparing independently trained models on the same slide.")
bullet("One assumption remains unverified. ",
       "The exact subdirectory TRIDENT writes slide thumbnails to. The system probes three "
       "extensions, falls back to generating thumbnails itself, and reports a diagnostic count so "
       "the mismatch is visible.")

para(("Closing note. ", "b"),
     "The architecture that this document describes was chosen for one property above all others: "
     "that a failure anywhere in the machine-learning pipeline degrades into a red status and a "
     "readable log, rather than into an unresponsive application. Every significant problem "
     "encountered during deployment was diagnosed through that mechanism. If one design decision "
     "from this project is worth carrying forward, it is the decision to let a database table, "
     "rather than a function call, be the boundary between the interface and the model.")

doc.save(OUT)
print("wrote", OUT)
