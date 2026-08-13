"""Generate the three figures for the Bagheera Detailed Design (rev. 2)."""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle
import os

OUT = os.path.dirname(os.path.abspath(__file__))

ORANGE = "#fab05e"
ORANGE_D = "#c9793a"
INK = "#2b2118"
GREY = "#8a8178"
BG_A = "#fff6ea"
BG_B = "#f3f1ee"
BG_C = "#e8f0f4"
BLUE = "#4a7c93"

plt.rcParams["font.family"] = "DejaVu Sans"


def box(ax, x, y, w, h, text, *, fc=BG_A, ec=ORANGE_D, fs=8.5, bold=False, lw=1.2):
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.010,rounding_size=0.018",
                       linewidth=lw, edgecolor=ec, facecolor=fc, zorder=2)
    ax.add_patch(p)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
            color=INK, zorder=3, fontweight="bold" if bold else "normal", linespacing=1.45)
    return p


def arrow(ax, xy1, xy2, *, style="-|>", color=ORANGE_D, lw=1.3, ls="-", rad=0.0):
    ax.add_patch(FancyArrowPatch(xy1, xy2, arrowstyle=style, mutation_scale=11, linewidth=lw,
                                 color=color, linestyle=ls, zorder=4,
                                 connectionstyle=f"arc3,rad={rad}", shrinkA=2, shrinkB=2))


def blank(w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    fig.subplots_adjust(left=0.01, right=0.99, top=0.955, bottom=0.01)
    return fig, ax


def save(fig, name, title):
    fig.suptitle(title, fontsize=11, color=INK, fontweight="bold", y=0.99)
    fig.savefig(f"{OUT}/{name}.png", dpi=200, bbox_inches="tight", facecolor="white",
                pad_inches=0.12)
    plt.close(fig)


# ---------------------------------------------------------------- Figure 1
def fig_architecture():
    fig, ax = blank(11.5, 7.4)

    ax.add_patch(Rectangle((0.02, 0.775), 0.96, 0.195, fc="#fdfaf6", ec=GREY, lw=0.9,
                           ls=(0, (4, 3)), zorder=1))
    ax.text(0.035, 0.947, "FRONTEND CONTAINER   ·   nginx :8080   —   serves the SPA, reverse-proxies /api/*",
            fontsize=8, color=GREY, va="center", fontweight="bold")
    box(ax, 0.045, 0.795, 0.21, 0.115, "React 18 + TypeScript\npages/  (10 routes)\nTailwind design tokens", fs=7.8)
    box(ax, 0.285, 0.795, 0.21, 0.115, "components/\nSectionA–D · ZoomPanImage\nDirectoryBrowser · ui/", fs=7.5)
    box(ax, 0.525, 0.795, 0.21, 0.115, "lib/api.ts\nthe FE↔BE contract\n(typed fetch wrapper)", fs=7.8, fc="#fdeed8")
    box(ax, 0.765, 0.795, 0.19, 0.115, "2 s polling loops\nJobStatusPoller\n(no websockets)", fs=7.8)

    ax.add_patch(Rectangle((0.02, 0.195), 0.96, 0.50, fc="#fbfaf8", ec=GREY, lw=0.9,
                           ls=(0, (4, 3)), zorder=1))
    ax.text(0.035, 0.672, "BACKEND / GPU CONTAINER   ·   FastAPI + Uvicorn :8000   —   CUDA runtime, TRIDENT + PANTHER baked in",
            fontsize=8, color=GREY, va="center", fontweight="bold")

    box(ax, 0.045, 0.545, 0.44, 0.10,
        "routes/  —  one router per resource   (14 routers · ~58 endpoints)\n"
        "fs · trident · runs · splits · panther · models · labels · notes\n"
        "inference · jobs · queue · viz · datasets · thumbnails",
        fs=7.3, fc="#fdeed8")
    box(ax, 0.515, 0.545, 0.44, 0.10,
        "models/schemas.py  —  Pydantic request / response models\n"
        "the validation boundary; ORM → schema via from_attributes",
        fs=7.5)

    box(ax, 0.045, 0.375, 0.44, 0.135,
        "services/  —  business logic\n"
        "fs.py (path sandbox) · runner.py (TRIDENT, sync)\n"
        "splitter.py · panther_runner.py · preview.py\n"
        "inference.py · thumbnails.py · model_delete.py",
        fs=7.3)
    box(ax, 0.515, 0.375, 0.44, 0.135,
        "services/  —  renderers & memoization\n"
        "visualization.py  (2 189 LOC — Sections A–D, heatmap,\n"
        "UMAP, ROI, violin) · assignment_cache.py (LRU, 32)\n"
        "post_train_viz.py · render_slide.py · inference_job.py",
        fs=7.3, fc="#fdeed8")

    box(ax, 0.045, 0.225, 0.29, 0.11,
        "worker.py\nONE daemon thread\npolls jobs every 2 s\nnever crashes the process", fs=7.6, fc="#ffe9cc")
    box(ax, 0.375, 0.225, 0.26, 0.11,
        "subprocess (blocking)\nbash run_trident.sh\nbash run_panther.sh\nCUDA_VISIBLE_DEVICES=0", fs=7.4, fc=BG_B, ec=GREY)
    box(ax, 0.675, 0.225, 0.28, 0.11,
        "GPU\nTRIDENT encoder pass\nPANTHER prototype fit", fs=7.8, fc=BG_C, ec=BLUE)

    ax.add_patch(Rectangle((0.02, 0.015), 0.96, 0.13, fc="#f7f5f2", ec=GREY, lw=0.9,
                           ls=(0, (4, 3)), zorder=1))
    ax.text(0.035, 0.122, "MOUNTED VOLUMES   —   all state lives outside the image", fontsize=8,
            color=GREY, va="center", fontweight="bold")
    vols = [("/state/db\nbagheera.db (SQLite, WAL)", 0.045, 0.175),
            ("/state/viz_cache\nrenders + job_logs/", 0.235, 0.175),
            ("/state/inference_outputs\nper-inference artifacts", 0.425, 0.19),
            ("datasets_splits\ntrain / val / test CSVs", 0.630, 0.165),
            ("/data   (read-only)\nWSI slides", 0.810, 0.145)]
    for t, x, w in vols:
        box(ax, x, 0.028, w, 0.062, t, fs=7.0, fc="white", ec=GREY, lw=0.9)

    arrow(ax, (0.63, 0.795), (0.63, 0.700))
    ax.text(0.645, 0.748, "HTTP  /api/*   (JSON + binary images)", fontsize=7.4, color=GREY, va="center")
    arrow(ax, (0.265, 0.545), (0.265, 0.513))
    arrow(ax, (0.735, 0.545), (0.735, 0.513))
    arrow(ax, (0.19, 0.375), (0.19, 0.338))
    arrow(ax, (0.337, 0.28), (0.372, 0.28))
    arrow(ax, (0.637, 0.28), (0.672, 0.28))
    arrow(ax, (0.115, 0.225), (0.115, 0.093))
    ax.text(0.128, 0.168, "jobs table\n(the interface contract)", fontsize=7.0, color=GREY, va="center")
    arrow(ax, (0.355, 0.375), (0.50, 0.093), rad=-0.06)
    arrow(ax, (0.87, 0.225), (0.885, 0.093), rad=-0.10)

    save(fig, "fig1_architecture", "Figure 1 — Logical architecture and physical deployment (as built)")


# ---------------------------------------------------------------- Figure 2
def fig_sequence():
    fig, ax = blank(12.0, 9.2)

    lanes = [("Pathologist\n(browser)", 0.085),
             ("React SPA\nPantherForm", 0.250),
             ("FastAPI\nroutes/panther.py", 0.418),
             ("SQLite\njobs table", 0.585),
             ("Worker thread\nservices/worker.py", 0.752),
             ("GPU\nPANTHER", 0.918)]
    top, bot = 0.925, 0.015
    for name, x in lanes:
        box(ax, x - 0.072, top, 0.144, 0.062, name, fs=7.5, bold=True, fc=BG_B, ec=GREY)
        ax.plot([x, x], [bot, top], color=GREY, lw=0.8, ls=(0, (3, 3)), zorder=1)
    P, R, A, D, W, G = [x for _, x in lanes]

    state = {"y": 0.888}

    def msg(x1, x2, text, *, color=ORANGE_D, ls="-", fs=7.2, lines=1):
        y = state["y"]
        ax.text((x1 + x2) / 2, y + 0.009, text, ha="center", va="bottom", fontsize=fs,
                color=INK, zorder=5, linespacing=1.4,
                bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="none", alpha=0.93))
        arrow(ax, (x1, y), (x2, y), color=color, ls=ls, lw=1.2)
        state["y"] = y - (0.044 if lines == 1 else 0.060)

    def note(xc, text, w=0.42):
        y = state["y"]
        box(ax, xc - w / 2, y - 0.034, w, 0.046, text, fs=6.9, fc="#fff9f0", ec=ORANGE, lw=0.9)
        state["y"] = y - 0.066

    msg(P, R, "Fill in split + hyperparameters, submit")
    msg(R, A, "POST /api/panther/single-runs")
    msg(A, D, "INSERT Model (status='pending', run_kind='single')\n"
              "+ enqueue_job(panther_train, ref_table='models')", lines=2)
    msg(A, R, "200 OK  { model_id, job_id }  —  returns immediately", color=BLUE)
    msg(R, P, "navigate → /models/:modelId", color=BLUE)
    note(0.40, "The HTTP request is already finished. All heavy work sits behind the jobs\n"
               "table, so a GPU failure can never take the API down with it.", w=0.52)

    msg(W, D, "poll every 2 s:  SELECT lowest queue_position WHERE status='queued'",
        color=GREY, ls=(0, (4, 2)))
    msg(W, D, "CAS:  UPDATE … SET status='running' WHERE id=? AND status='queued'")
    note(0.56, "0 rows changed ⇒ a user cancelled it first ⇒ skip to the next job.\n"
               "The database, not an application lock, picks the winner of the race.", w=0.50)

    msg(W, G, "subprocess: run_panther.sh   (blocking, CUDA_VISIBLE_DEVICES=0)")
    msg(G, W, "prototypes .pkl written to disk", color=BLUE)
    msg(W, D, "Model.status='ready'   +   enqueue_job(post_train_viz)")
    note(0.62, "The visualization job re-enters the SAME queue at the tail —\n"
               "one worker, one GPU consumer, no second scheduler.", w=0.46)
    msg(W, G, "post_train_viz: one encoder pass → Sections A · C · D + violin")
    msg(W, D, "Model.viz_artifacts = { … },  viz_status='ready',  job='succeeded'")

    msg(R, A, "GET /api/jobs?ref_id=…   (2 s poll, running the whole time)",
        color=GREY, ls=(0, (4, 2)))
    msg(A, R, "status + log_tail   →   JobStatusPoller re-renders", color=BLUE)
    msg(R, P, "Analysis panels appear (placeholders swap to real renders)",
        color=BLUE, fs=7.1)

    save(fig, "fig2_sequence",
         "Figure 2 — Sequence: submitting a PANTHER training run (async, database-mediated)")


# ---------------------------------------------------------------- Figure 3
def fig_usecase():
    fig, ax = blank(10.5, 8.8)

    def actor(x, y, label):
        ax.plot([x], [y + 0.036], marker="o", ms=8, mfc="white", mec=INK, mew=1.3, zorder=3)
        ax.plot([x, x], [y + 0.031, y - 0.004], color=INK, lw=1.3, zorder=3)
        ax.plot([x - 0.024, x + 0.024], [y + 0.021, y + 0.021], color=INK, lw=1.3, zorder=3)
        ax.plot([x, x - 0.020], [y - 0.004, y - 0.036], color=INK, lw=1.3, zorder=3)
        ax.plot([x, x + 0.020], [y - 0.004, y - 0.036], color=INK, lw=1.3, zorder=3)
        ax.text(x, y - 0.056, label, ha="center", va="top", fontsize=8.4,
                fontweight="bold", color=INK)

    ax.add_patch(Rectangle((0.235, 0.042), 0.745, 0.908, fc="#fffaf3", ec=ORANGE_D,
                           lw=1.2, zorder=1))
    ax.text(0.607, 0.928, "Bagheera  —  system boundary", ha="center", fontsize=8.8,
            color=ORANGE_D, fontweight="bold", zorder=3)

    ucs = [
        ("UC1", "Extract patch features from a WSI directory (TRIDENT, synchronous)"),
        ("UC2", "Create a reproducible slide split from a manifest CSV"),
        ("UC3", "Train a PANTHER prototype model (async, queued)"),
        ("UC4", "Browse, search, favourite and rename trained models"),
        ("UC5", "Inspect a model — Sections A · B · C · D analysis panels"),
        ("UC6", "Re-pick or click-select the region of interest on a slide"),
        ("UC7", "Label prototypes and attach free-text clinical notes"),
        ("UC8", "Compare up to 4 models rendered on one slide, side by side"),
        ("UC9", "Run a trained model on new slides (cached inference)"),
        ("UC10", "Manage the job queue — cancel · drag-reorder · re-run"),
        ("UC11", "Read a running job's live log"),
        ("UC12", "Delete a legacy model group and its on-disk artifacts"),
        ("UC13", "Deploy and configure the stack (compose, .env, allowed roots)"),
    ]
    y0, step = 0.878, 0.0665
    ax.text(0.607, 0.877, "", fontsize=1)
    for i, (tag, text) in enumerate(ucs):
        y = y0 - i * step
        e = FancyBboxPatch((0.275, y - 0.026), 0.675, 0.052,
                           boxstyle="round,pad=0.006,rounding_size=0.026",
                           fc=BG_A, ec=ORANGE_D, lw=1.1, zorder=2)
        ax.add_patch(e)
        ax.text(0.298, y, tag, ha="left", va="center", fontsize=8.0,
                color=ORANGE_D, fontweight="bold", zorder=3)
        ax.text(0.355, y, text, ha="left", va="center", fontsize=8.0, color=INK, zorder=3)

    actor(0.085, 0.640, "Pathologist /\nResearcher")
    actor(0.085, 0.170, "Operator\n(deployment)")

    for i in range(12):
        y = y0 - i * step
        arrow(ax, (0.112, 0.640), (0.271, y), style="-", lw=0.8, color=GREY, rad=0.0)
    for i in (9, 11, 12):
        y = y0 - i * step
        arrow(ax, (0.112, 0.170), (0.271, y), style="-", lw=0.8, color=GREY, rad=0.0)

    ax.text(0.607, 0.016, "UC1 · UC3 · UC8 · UC9  «include»  “enqueue a job” — every heavy use case is "
                          "mediated by the shared FIFO queue of UC10.",
            ha="center", fontsize=7.4, color=GREY, style="italic")

    save(fig, "fig3_usecase", "Figure 3 — Use-case model (as built)")


# fig_architecture() is intentionally NOT called: Figure 1 is being replaced by
# hand-authored artwork per FIGURE-1-SPEC.md. Re-enable only if you want the old
# generated version back. Figures 2 and 3 are still generated here.
fig_sequence()
fig_usecase()
print("done")
