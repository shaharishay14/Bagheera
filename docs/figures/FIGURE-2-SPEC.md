# Figure 2 — generation prompt

**Target file:** `docs/figures/fig2_sequence.png`

**Caption in the document — this needs updating, the figure now shows two flows:**
*Figure 2 — Sequence: submitting a PANTHER training run, and running inference on a new slide. The
HTTP request completes before any GPU work begins; the jobs table is the only channel between the
API and the worker.*

This file was a build spec for a plotting script. It is now a **copy-paste prompt for an image
model**, in the same design language as `FIGURE-1-SPEC.md`: white cards on near-invisible warm
panels, one amber accent used sparingly, one slate-blue card for the GPU, uppercase letterspaced
labels, no measurements anywhere on the image. Paste the block under **The prompt** verbatim.

---

## What changed, and why

| # | Was | Now |
| --- | --- | --- |
| 1 | Lifeline 1 was `Pathologist` / `(browser)`. | **`User` / `Pathologist / Researcher`.** Both roles submit training runs and inferences; the split between them is Figure 3's subject, not this one's. Naming one role here would have implied the other cannot do it. |
| 2 | One sequence only — the training run. | **A second section below it: running inference on a new slide.** It is the other half of the product, it is the only flow with a persistent cache, and it reuses the same six lifelines, so it costs one section header rather than a second figure. |
| 3 | Referred to `FIGURE-1-SPEC.md §2` for canvas, palette and fonts. That section no longer exists — Figure 1 is a prompt now, not a spec. | Self-contained. |
| 4 | Named pixel canvases (`2000 × 1550 px`), hex colours and a minimum print width. An image model cannot honour those and will sometimes *draw* them. | No numbers of any kind. Colours in words, proportions as ratios. |
| 5 | Message labels carried raw SQL and Python: `INSERT Model (status='pending', run_kind='single') + enqueue_job(panther_train, ref_table='models')`. At figure scale that is an unreadable smear, and it is the same density problem Figure 1 was rewritten to solve. | Every label is at most five words, no parentheses, no quotes, no argument lists. The SQL lives in the pseudocode block of §7.1 of the document, where it belongs. |
| 6 | Told the renderer messages 13–15 were concurrent with 6–12 but placed them last, with a fallback note admitting the sequence would read as false. | **The layout carries the concurrency.** Messages 6–12 touch only lifelines 4–6 and 13–15 only lifelines 1–3, so they are drawn side by side in two equal-height panels. Nothing has to be bracketed or explained away. |
| 7 | Three floating note boxes, one spanning lifelines 2–4 across the middle of the drawing. | The "request is already finished" note is a **full-width divider band** — it is the figure's main claim, so it separates the halves rather than floating in them. The rest are short italic lines under the message they qualify. |
| 8 | An optional activation bar "if it does not clutter". | Dropped. The panels already mark the busy span. |

## Section 1 — the training run, verified against the code

Colour by kind: **command** solid medium warm grey with a filled head; **return** solid light warm
grey with a hollow head; **poll** grey dashed; **queue handoff** amber. Amber is restricted to the
four handoff arrows — two per section — and two header cards.

| # | From → To | Label on the arrow | Kind | Verified at |
| --- | --- | --- | --- | --- |
| 1 | User → React SPA | `submit training form` | command | — |
| 2 | React SPA → FastAPI | `POST /api/panther/single-runs` | command | `routes/panther.py:241` |
| 3 | FastAPI → SQLite | `insert model · queue job` | **amber** | `enqueue_job(job_type="panther_train", ref_table="models")`, `routes/panther.py:330` |
| 4 | FastAPI → React SPA | `200 OK · model + job id` | return | no `status_code` on the route ⇒ FastAPI default 200; `PantherSingleRunStartResponse` carries `model_id`, `job_id`, `split_id`, `split_name` |
| 5 | React SPA → User | `navigate to model page` | return | — |
| 6 | Worker thread → SQLite | `poll every 2 s` | poll | `POLL_INTERVAL_SECONDS = 2.0`, `services/worker.py:34` |
| 7 | Worker thread → SQLite | `claim · compare-and-swap` | **amber** | `SELECT … WHERE status='queued' ORDER BY queue_position, created_at LIMIT 1` then `UPDATE … WHERE id=? AND status='queued'`, `worker.py:96–110` |
| 8 | Worker thread → GPU | `run_panther.sh · blocking` | command | `services/panther_runner.py`, `backend/scripts/run_panther.sh` |
| 9 | GPU → Worker thread | `prototypes written` | return | `_train_one_fold`, `panther_train.py:32` |
| 10 | Worker thread → SQLite | `model ready · queue viz` | command | `enqueue_job(job_type="post_train_viz")`, `panther_train.py:158` |
| 11 | Worker thread → GPU | `render A · C · D + violin` | command | `post_train_viz.py` renders `section_a`, `section_c`, `section_d`, `section_b_violin` |
| 12 | Worker thread → SQLite | `viz ready · job succeeded` | command | `post_train_viz.py:53` sets `viz_status`; `worker.py` sets `status='succeeded'` |
| 13 | React SPA → FastAPI | `GET /api/jobs` | poll | `listJobs`, `frontend/src/lib/api.ts:1038` |
| 14 | FastAPI → React SPA | `status + log tail` | return | `JobStatusPoller`, 2 s `setTimeout` |
| 15 | React SPA → User | `panels appear` | return | `resolveVizUrl` swaps placeholders for renders |

## Section 2 — the inference run, verified against the code

The point of this section is the **cache**: the browser asks before it submits, and the API asks
again before it queues. A verified hit returns the stored result and no job is created at all.

| # | From → To | Label on the arrow | Kind | Verified at |
| --- | --- | --- | --- | --- |
| 16 | User → React SPA | `pick model · pick slides` | command | UC9, single or batch |
| 17 | React SPA → FastAPI | `GET /api/inferences/lookup` | command | `routes/inference.py:191`, called per path before submission |
| 18 | FastAPI → React SPA | `cached or new` | return | `InferenceLookupResponse`; the UI marks each path |
| 19 | React SPA → FastAPI | `POST /api/inferences` | command | `routes/inference.py:92` |
| 20 | FastAPI → SQLite | `insert rows · queue jobs` | **amber** | `enqueue_job(job_type="inference", ref_table="inferences")`, `routes/inference.py:165` |
| 21 | FastAPI → React SPA | `200 OK · per-slide status` | return | `InferenceCreateResponse`, one entry per path marked `queued`, `cached` or `rejected` |
| 22 | Worker thread → SQLite | `claim · compare-and-swap` | **amber** | same `claimNextJob` as message 7 |
| 23 | Worker thread → GPU | `TRIDENT features · blocking` | command | `subprocess.run` under `TRIDENT_REPO_PATH`, `services/inference_job.py:97` |
| 24 | Worker thread → GPU | `render heatmap · patches · t-SNE` | command | `inference_job.py:164–197` renders heatmap, mixture plot, example patches, t-SNE |
| 25 | Worker thread → SQLite | `result ready · job succeeded` | command | `inference_job.py:200` sets `status='ready'` |

### Accuracy notes — do not "improve" these

- **Message 4 is `200 OK`, not `201`.** `@router.post("/single-runs")` declares no `status_code`, so
  FastAPI returns its default 200. An earlier draft said 201 and was wrong.
- **Message 11 is `A · C · D + violin`, not `A · B · C · D`.** `post_train_viz` renders `section_b` —
  validation consistency — only when the model has val slides. A single-model run puts every row in
  `train.csv` (`splitter.create_single_split`), so there are none and Section B is skipped for
  exactly this flow. The violin is a separate artifact (`section_b_violin`) and is always rendered.
- **Message 23 is TRIDENT, not PANTHER.** Inference on an unseen slide has to extract that slide's
  patch features first; only then are they projected onto the trained prototypes. The GPU lifeline is
  labelled `PANTHER` for the training section, so the section-2 label carries the pipeline name.
- **The cache is a verified hit, not a filename match.** `lookup_cached_inference` pre-filters on
  mtime and size, then confirms the stored SHA-256 (`services/inference.py:154`). Modification time
  is an optimisation; the hash is the source of truth.
- **The caption's claim is true here, unlike Figure 1's first draft.** Nothing connects `routes/` to
  `worker.py` in either direction; `enqueue_job` writes a row and the worker reads rows. The
  synchronous TRIDENT path that broke Figure 1's caption is UC1's separate first extraction and does
  not appear in either sequence.

### Deliberately not drawn

- **The second claim in section 1.** Message 10 queues the visualization job, so the worker must poll
  and compare-and-swap again before message 11. The mechanism is identical to messages 6 and 7 and
  doubles the height of the panel to say nothing new. The note inside the panel carries it.
- **The polling loop in section 2.** It is the same `GET /api/jobs` loop as messages 13–15. Drawn
  once, referenced by a note in section 2.
- **FastAPI reading the jobs table during the poll.** Message 13 is served by a `SELECT` against the
  same table. Drawing it means an arrow from lifeline 3 to lifeline 4, crossing the gutter between
  the two panels and landing in the middle of the worker sequence.
- **`207 Multi-Status`.** `POST /api/inferences` returns 207 when some paths are rejected and others
  succeed (`routes/inference.py:181`). The happy path is 200 and that is what the figure draws.
- **The batch row.** `InferenceBatch` is created only when more than one valid path is submitted.
- **The legacy K-fold path** (`POST /api/panther/runs`), **manifest creation** (a separate earlier
  request), **error branches** (§10.2), and the `render_slide` job type — different flows, same queue.

---

## The prompt

> Create a clean, modern UML-style sequence diagram as a single flat vector illustration on an opaque
> white background. Portrait, roughly 4:5, high resolution.
>
> **Overall feel:** calm, spacious, editorial — the visual language of well-designed product
> documentation, not a legacy UML tool. Flat shapes, generous empty space, a restrained warm palette,
> one clear reading direction from top to bottom. Roughly a third of the canvas should be empty
> space. When in doubt, make things smaller and the gaps larger.
>
> **Palette:**
> - Page background: pure white.
> - Group panels: a soft warm off-white, almost imperceptible against the page.
> - Header cards: white with a very light warm-grey hairline outline and a barely-there soft shadow.
> - Highlight colour: a warm amber-orange, used for exactly two header cards, four arrows, two thin
>   section rules and one short rule at the bottom, and nothing else. Highlighted cards get a pale
>   amber fill, an amber outline, and a thick amber vertical bar flush against their left edge.
> - One cool slate-blue header card for the GPU.
> - Text: very dark warm brown for titles, medium warm grey for secondary lines and arrow labels.
>
> **Typography:** a single geometric humanist sans throughout, two weights only. Header-card titles in
> semibold dark brown; the one line under each title in regular medium-grey, clearly smaller but
> still comfortably legible. Section and panel labels in small letterspaced uppercase grey, with
> clear air beneath. All text horizontal, crisply rendered and correctly spelled.
>
> **Layout.**
>
> **Six lifelines**, evenly spaced left to right across the full width, each headed by a white card
> holding a bold title and one smaller grey line beneath it:
>
> 1. `User` / `Pathologist / Researcher`
> 2. `React SPA` / `PantherForm`
> 3. `FastAPI` / `routes/panther.py`
> 4. `SQLite` / `jobs table` — **highlighted amber**
> 5. `Worker thread` / `services/worker.py` — **highlighted amber**
> 6. `GPU` / `TRIDENT · PANTHER` — **slate-blue**
>
> Below each header card a thin vertical **dashed light-grey lifeline** runs all the way to the
> bottom of the drawing. Leave wide, even gaps between adjacent lifelines so message labels never
> touch a neighbouring line.
>
> The body has **two sections stacked top to bottom**. Each section opens with a **section rule**: a
> thin amber horizontal line spanning the full width with its title just above it in small
> letterspaced uppercase grey, and clear empty space above and below.
>
> ---
>
> **SECTION RULE — `TRAINING A MODEL`.** Then three zones:
>
> **Zone 1 — the request.** Five messages, spanning lifelines 1 to 4. No panel behind them.
>
> **Zone 2 — a full-width divider band.** A soft warm off-white horizontal strip spanning the whole
> width, containing one line of centred dark text: `The HTTP request is finished here. Everything
> below happens after the browser has already been answered.` The lifelines pass down through it. No
> arrow starts, ends, or crosses inside this band.
>
> **Zone 3 — two panels side by side, of equal height, with a clear empty gutter between them.**
> - The **left panel** sits behind lifelines 1, 2 and 3, labelled `MEANWHILE · POLLING EVERY 2 S`.
> - The **right panel** sits behind lifelines 4, 5 and 6, labelled `THE WORKER, ON ITS OWN THREAD`.
>
> Both panels start at the same height and end at the same height, so the reader sees at a glance
> that the browser's polling and the worker's job happen at the same time. The left panel holds only
> three messages and is therefore mostly empty — leave it that way, the emptiness is the point.
>
> ---
>
> **SECTION RULE — `RUNNING INFERENCE ON A NEW SLIDE`.** Then one zone, no panels: ten messages
> running straight down, spanning all six lifelines.
>
> ---
>
> **Messages.** Thin flat horizontal arrows with small triangular heads. Each carries a short label
> **above** its arrow, in small grey text, with a white halo behind the text so it stays legible
> wherever it crosses a lifeline. Four kinds, and no others:
> - **command** — solid medium warm grey line, solid filled head
> - **return** — solid light warm grey line, hollow outlined head
> - **poll** — light grey dashed line, small head
> - **queue handoff** — thicker amber line, solid amber head. Exactly four messages are amber.
>
> Draw exactly these twenty-five, in this order, top to bottom within their zone. The arrowhead is
> always on the second lifeline named.
>
> **Section 1, zone 1:**
> 1. `User` → `React SPA` — `submit training form` — command
> 2. `React SPA` → `FastAPI` — `POST /api/panther/single-runs` — command
> 3. `FastAPI` → `SQLite` — `insert model · queue job` — **amber**
> 4. `FastAPI` → `React SPA` — `200 OK · model + job id` — return
> 5. `React SPA` → `User` — `navigate to model page` — return
>
> **Section 1, zone 3, right panel:**
> 6. `Worker thread` → `SQLite` — `poll every 2 s` — poll
> 7. `Worker thread` → `SQLite` — `claim · compare-and-swap` — **amber**
> 8. `Worker thread` → `GPU` — `run_panther.sh · blocking` — command
> 9. `GPU` → `Worker thread` — `prototypes written` — return
> 10. `Worker thread` → `SQLite` — `model ready · queue viz` — command
> 11. `Worker thread` → `GPU` — `render A · C · D + violin` — command
> 12. `Worker thread` → `SQLite` — `viz ready · job succeeded` — command
>
> **Section 1, zone 3, left panel:**
> 13. `React SPA` → `FastAPI` — `GET /api/jobs` — poll
> 14. `FastAPI` → `React SPA` — `status + log tail` — return
> 15. `React SPA` → `User` — `panels appear` — return
>
> **Section 2:**
> 16. `User` → `React SPA` — `pick model · pick slides` — command
> 17. `React SPA` → `FastAPI` — `GET /api/inferences/lookup` — command
> 18. `FastAPI` → `React SPA` — `cached or new` — return
> 19. `React SPA` → `FastAPI` — `POST /api/inferences` — command
> 20. `FastAPI` → `SQLite` — `insert rows · queue jobs` — **amber**
> 21. `FastAPI` → `React SPA` — `200 OK · per-slide status` — return
> 22. `Worker thread` → `SQLite` — `claim · compare-and-swap` — **amber**
> 23. `Worker thread` → `GPU` — `TRIDENT features · blocking` — command
> 24. `Worker thread` → `GPU` — `render heatmap · patches · t-SNE` — command
> 25. `Worker thread` → `SQLite` — `result ready · job succeeded` — command
>
> **Four short notes**, in small grey italic text sitting in clear empty space to the right of the
> lifelines they follow, each separated from its message by a hair of white space and touching no
> arrow:
> - under message 7: `0 rows changed → cancelled a moment ago → take the next job`
> - under message 10: `the viz job re-enters the same queue at the tail`
> - under message 18: `a verified hash hit returns the stored result and queues nothing`
> - under message 21: `answered here too — the slides are still unprocessed, and the browser polls
>   exactly as above`
>
> **Rules — these matter more than anything else in the image:**
> - **No arrow of any kind may connect lifeline 3 to lifeline 5.** The API and the worker never
>   exchange a message; every handoff between them passes through lifeline 4. That absence is the
>   whole point of the figure.
> - Every arrow starts on one lifeline and ends on another. No arrow starts or ends in mid-air, on a
>   panel edge, on a section rule, or on another arrow.
> - **No arrow may branch off, tee into, run alongside, or share any segment with another arrow.**
>   No forks, no Y-junctions, no T-junctions, no shared trunks.
> - Every message is a **single straight horizontal line**. No bends, no diagonals, no self-calls, no
>   curved or looping arrows.
> - **Time flows strictly downward.** No two messages sit at the same height within a zone, and no
>   arrow points upward.
> - No arrow may cross, touch, or pass behind a header card, a panel label, a section rule, a note,
>   or the divider band.
> - No label may touch another label, or overlap a lifeline's dashes without its white halo.
> - Amber appears only on messages 3, 7, 20 and 22, on the two amber header cards, and on the three
>   thin rules. Every other arrow is grey.
>
> **At the very bottom**, one line of small text with a short amber rule to its left:
> `The API and the worker never call each other — every handoff between them is a row in the jobs table.`
>
> **Render only the text listed above, spelled exactly as written.** Each label appears exactly once,
> except `claim · compare-and-swap`, which appears once per section. Do not invent additional
> messages, labels, lifelines, file names, captions, titles, or annotations. Do not draw any
> dimensions, measurements, pixel or point sizes, timestamps, rulers, grid lines, alignment guides,
> message numbers, legends, keys, colour swatches, scale bars, watermarks, code snippets, SQL, or UI
> chrome. No 3-D, no gradients, no isometric perspective, no drop shadows beyond the faintest lift,
> no gloss.

---

## Rejection checklist

Regenerate on any of these:

- **Any arrow between `FastAPI` and `Worker thread`.** This is the one unforgivable error.
- Lifeline 1 headed `Pathologist` alone, or `Researcher` alone. It is `User` over
  `Pathologist / Researcher`.
- The two sections merged, interleaved, or drawn side by side. Section 2 sits **below** section 1,
  under its own amber section rule, on the same six lifelines.
- The two zone-3 panels drawn at different heights, stacked vertically, or merged into one — the
  side-by-side equal-height arrangement is what states the concurrency.
- A poll message drawn inside the right panel, or a worker message drawn inside the left panel.
- Panels drawn around section 2 — it has none.
- Message 4 reading `201` instead of `200 OK`, or message 21 reading `207`.
- Message 11 reading `A · B · C · D` — Section B needs held-out slides and this flow has none.
- Message 23 reading `PANTHER` — inference extracts features with TRIDENT first.
- Any arrow that branches out of, tees into, or shares a segment with another arrow.
- Any arrow that bends, curves, loops back to its own lifeline, or points upward.
- Any label containing SQL, parentheses, quotes, an argument list, or more than five words.
- More or fewer than four amber arrows, or an amber arrow that is not message 3, 7, 20 or 22.
- More or fewer than six lifelines, or lifelines in a different left-to-right order.
- A note box sitting on top of an arrow, or a label unreadable where it crosses a lifeline.
- An activation bar, an `alt` or `par` fragment box, a `loop` bracket, or any other UML fragment
  notation — the panels and section rules do that work.
- Any message drawn inside the divider band.
- A caption or footer claiming the jobs table is the only channel to the **GPU**. It is the only
  channel to the **worker**. The wording above is chosen to be true; do not "tighten" it.

**What must not be added back:** SQL statements, Python call signatures, `run_kind` and `ref_table`
values, hex colours, pixel sizes, poll-interval arithmetic, error branches, `207` responses, the
batch row, the K-fold path. All of that belongs in the prose around the figure.
