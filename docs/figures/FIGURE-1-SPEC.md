# Figure 1 — generation prompt

**Target file:** `docs/figures/fig1_architecture.png`
**Caption in the document:** *Figure 1 — Logical architecture and physical deployment. Arrows show
dependency and data flow; each shaded region is a separate deployment unit.*

The **design** is right — keep the palette, cards, panels, and spacing exactly as they are. This
revision corrects a caption that overstated what the jobs table does, makes the three downward
arrows start on a card edge instead of in the middle of another arrow, and defines what a legal
crossing looks like. Paste the block below verbatim.

---

## Verification of the previous render

**Correct:** the stale `train / val / test` label is gone, `slide files` is a clean straight
vertical, `image bytes` leaves the panel edge, and every arrow direction matches the code.

**Wrong:**

| # | Problem | Fix |
| --- | --- | --- |
| 1 | The bottom caption claimed the jobs table is **the only** channel between the API and the GPU. It is not: `POST /api/trident/run` calls `runner.execute(cmd)` on the request thread (`routes/trident.py:52`), reaching the GPU with no job row and no worker. Only the inference-time TRIDENT path is asynchronous (`services/runner.py`, module note). | Caption now reads `Every training, visualization and inference job reaches the GPU through the jobs table.` — true of every path the figure draws. The synchronous first extraction stays out of the figure by choice; see the note below the dataflow table. |
| 2 | `dataset CSV` and `PNG figures` **appear to sprout from the middle of `command line` and `tensors`** — a T-junction, the exact thing the no-shared-trunk rule forbids. | Both now leave a card **bottom edge** at the horizontal position of their drop column, so each is one unbroken vertical from card to volume. |
| 3 | Cause of #2: the spec named a **start point** (`bottom-right corner`) and a **corridor** (`the gutter between worker.py and subprocess`) that are not vertically aligned. A straight drop was impossible, so the renderer added a horizontal leg — and that leg lay exactly on top of the horizontal arrow already in that gutter. | Start point and corridor are now the same x. The spec asks for the drop column, never a corner, and says outright that no horizontal segment is permitted on these arrows. |
| 4 | The routing rules forbade junctions but never said what a **legal crossing** is, and capped the whole image at one hop — while the geometry needs three. A renderer with no legal way to cross will merge lines instead, which is precisely how #2 happened. | All three crossings are now named, and the **hop goes on the horizontal line** so each vertical stays perfectly straight and visibly starts at its card. |
| 5 | `job record` runs rightward from `worker.py` across column A, so it must cross `dataset CSV`. The old spec left this unnamed. | Named as the third crossing, with `dataset CSV` running through and `job record` hopping. |
| 6 | A straight drop to `/state/inference_outputs` needs clear space to the right of `GPU` that is still underneath the right `services/` card — the previous layout left none. | Row 3 now states that `GPU` ends clearly to the left of the right `services/` card's right edge. |

**Volume order** — unchanged, and load-bearing. Each volume sits directly below the column that
reaches it, and `/data` sits directly beneath `subprocess`:

`/state/db · datasets_splits · /data · /state/viz_cache · /state/inference_outputs`

**The three drop columns** — every downward arrow into the volumes uses one of these, and each is a
strictly vertical line:

| Column | Runs between | Feeds |
| --- | --- | --- |
| A | `worker.py` and `subprocess` | `datasets_splits` |
| B | `subprocess` and `GPU` | `/state/viz_cache` |
| C | `GPU`'s right edge and the panel's right edge | `/state/inference_outputs` |

## The dataflow, verified against the code

| Arrow | Label (the data) | Verified at |
| --- | --- | --- |
| person → frontend panel | `page requests` | — |
| `lib/api.ts` → `routes/` | `JSON requests` | `frontend/src/lib/api.ts` |
| `lib/api.ts` ⇢ `routes/` | `status polls` | `JobStatusPoller`, 2 s |
| `schemas.py` → `routes/` | `parsed models` | `app/models/schemas.py` |
| `routes/` → `services/` logic | `request params` | `routes/splits.py` |
| `routes/` → `jobs` **amber** | `queued row` | `enqueue_job` in `routes/panther.py`, `inference.py`, `models.py` |
| `jobs` → `worker.py` **amber** | `claimed row` | `worker.py` poll loop |
| `worker.py` → `services/` renderers | `job record` | `register_handler` ×4 |
| `worker.py` → `subprocess` | `command line` | `runner.py`, `panther_runner.py` |
| `subprocess` → `GPU` | `tensors` | `run_trident.sh`, `run_panther.sh` |
| `services/` logic → `datasets_splits` | `dataset CSV` | `splitter.create_single_split` |
| `services/` renderers → `/state/viz_cache` | `PNG figures` | `visualization.py` |
| `services/` renderers → `/state/inference_outputs` | `features, PNGs` | `inference_job.py` |
| `/data` ⇢ `subprocess` | `slide files` | `runner.py` |
| volumes panel ⇢ `routes/` | `image bytes` | `routes/viz.py` `serve_viz` |

**One path is deliberately not drawn.** `POST /api/trident/run` builds the argv and calls
`runner.execute(cmd)` on the request thread, so the *first* feature extraction for a dataset reaches
the GPU synchronously — no job row, no worker (`routes/trident.py:52`). It predates the job system
and was left synchronous because it happens once per dataset; `services/runner.py` says so in its
module note. Drawing it would need a sixteenth arrow from `routes/` in row 1 down to `subprocess` in
row 3, cutting through both rows and every column, for a path the user takes once. **Do not add it.**
The caption is worded to stay true without it: it claims the jobs table for training, visualization
and inference, which is every path the figure does draw.

---

## The prompt

> Create a clean, modern software architecture diagram as a single flat vector-style illustration
> on an opaque white background. Landscape, roughly 3:2, high resolution.
>
> **Overall feel:** calm, spacious, editorial — the visual language of a well-designed product
> documentation page, not a legacy flowchart tool. Flat shapes, generous empty space, a restrained
> warm palette, one clear reading direction from top to bottom. Roughly a third of the canvas should
> be empty space. When in doubt, make things smaller and the gaps larger.
>
> **Palette:**
> - Page background: pure white.
> - Group panels: a soft warm off-white, almost imperceptible against the page.
> - Cards: white with a very light warm-grey hairline outline and a barely-there soft shadow.
> - Highlight colour: a warm amber-orange, used for exactly three cards and two arrows and nothing
>   else. Highlighted cards get a pale amber fill, an amber outline, and a thick amber vertical bar
>   flush against their left edge.
> - One cool slate-blue card for the GPU.
> - One neutral grey card with a dashed outline for the external process.
> - Text: very dark warm brown for titles, medium warm grey for secondary lines.
>
> **Typography:** a single geometric humanist sans throughout, two weights only. Card titles in
> semibold dark brown; the one line under each title in regular medium-grey, clearly smaller but
> still comfortably legible. Group labels in small letterspaced uppercase grey, placed above their
> panel with clear air beneath, never touching or overlapping it. All text horizontal, left-aligned
> inside cards, crisply rendered and correctly spelled.
>
> **Two empty vertical channels.** Inset all three panels from the left and right edges of the
> canvas so there is a clear empty column down each side of the whole diagram. The left channel
> carries the two amber arrows; the right channel carries one dashed arrow back up. No card, panel,
> or label may intrude into either channel.
>
> **Layout — four horizontal groups stacked top to bottom, separated by wide empty white bands:**
>
> 1. **Top, no panel:** a small simple line-art person icon beside the text `Pathologist / Researcher`.
>
> 2. **Panel labelled `FRONTEND CONTAINER`.** Three equal white cards in a row:
>    - `React 18 + TypeScript` / `10 page components`
>    - `components/` / `shared UI and viewers`
>    - `lib/api.ts` / `the FE↔BE contract` — **highlighted amber**
>
> 3. **Panel labelled `BACKEND + GPU CONTAINER`.** Three rows of cards, with clear breathing room
>    between the rows:
>    - Row 1: a wide card `routes/` / `one router per resource` filling the left two thirds, and
>      beside it `schemas.py` / `the validation boundary`
>    - Row 2: two equal cards, `services/` / `business logic` on the left and `services/` /
>      `renderers and cache` on the right
>    - Row 3: **three narrow cards with wide empty gutters between them** — a **highlighted amber**
>      card `worker.py` / `one background daemon thread` occupying only the left third, then after a
>      wide gap a **grey dashed-outline** card `subprocess` / `blocking`, then after another gap a
>      **slate-blue** card `GPU` / `TRIDENT · PANTHER`. Row 3 must be visibly less crowded than the
>      rows above it — the gutters are load-bearing, arrows pass down through them.
>    - **Three clear vertical columns must exist through row 3**, because three arrows drop through
>      it to the volumes below. Size and place the row-3 cards so that all three columns are wide,
>      empty, and each one has a row-2 `services/` card directly above it and its target volume
>      directly below it, so that each drop is a single straight vertical line:
>      **column A** between `worker.py` and `subprocess`; **column B** between `subprocess` and
>      `GPU`; **column C** to the right of `GPU`. For column C to exist, `GPU` must end clearly to
>      the left of the right `services/` card's right edge — do not stretch `GPU` to the panel edge.
>
> 4. **Panel labelled `MOUNTED VOLUMES`.** Five equal white cards in a row, each with a tiny
>    line-art drive icon before its title. **This order matters** — each volume sits below the gutter
>    that reaches it, and `/data` sits directly beneath `subprocess`:
>    - `/state/db` / `SQLite` — and inside this card, at its right, a small **highlighted amber**
>      pill labelled `jobs`
>    - `datasets_splits` / `whole-dataset CSV`
>    - `/data` / `slide images, read-only`
>    - `/state/viz_cache` / `rendered figures`
>    - `/state/inference_outputs` / `features and figures`
>
> **Arrows** — thin, flat, right-angled with softly rounded corners, small solid triangular heads, in
> a light warm grey. Each carries a **short label of at most two words naming the data that travels
> along it**, in small grey text floating in clear white space beside the line. Every arrow starts on
> the edge of one card or panel and ends on the edge of another. Draw exactly these fifteen, with the
> arrowhead on the second thing named:
>
> - `Pathologist / Researcher` → the top edge of the `FRONTEND CONTAINER` panel — `page requests`
> - `lib/api.ts` **bottom-left corner** → `routes/` top edge — `JSON requests`
> - `lib/api.ts` **bottom-right corner** → `routes/` top edge, **dashed**, landing well to the right
>   of the previous arrow — `status polls`
> - `schemas.py` left edge → `routes/` right edge, short and horizontal — `parsed models`
> - `routes/` **bottom edge, left half** → the left `services/` card top edge, short vertical —
>   `request params`
> - `routes/` **left edge** → the amber `jobs` pill — `queued row` — **thick amber**, running down
>   the empty left channel and entering `/state/db` from its left edge. The arrowhead is on `jobs`.
> - the `jobs` pill → `worker.py` **left edge** — `claimed row` — **thick amber**, pointing upward,
>   running back up the same left channel on a parallel track with a clear constant gap from the
>   arrow above. It stays outside the panels for its whole length and never passes over the
>   `MOUNTED VOLUMES` label or any other text.
> - `worker.py` **top edge** → the right `services/` card bottom-left corner — `job record`. Its
>   horizontal run crosses column A; `dataset CSV` passes straight through and `job record` hops.
> - `worker.py` **right edge** → `subprocess` left edge, horizontal — `command line`
> - `subprocess` right edge → `GPU` left edge, horizontal — `tensors`
> - the left `services/` card **bottom edge** → `datasets_splits` **top edge** — `dataset CSV` — a
>   single straight vertical line down **column A**, the gap between `worker.py` and `subprocess`.
>   It leaves the card bottom edge at the horizontal position of that column, so the line has **no
>   horizontal segment and no bend anywhere**. It crosses `command line` on the way down.
> - the right `services/` card **bottom edge** → `/state/viz_cache` **top edge** — `PNG figures` — a
>   single straight vertical line down **column B**, the gap between `subprocess` and `GPU`. Same
>   rule: it leaves the card bottom edge at that column's horizontal position, with **no horizontal
>   segment and no bend**. It crosses `tensors` on the way down.
> - the right `services/` card **bottom edge** → `/state/inference_outputs` **top edge** — `features,
>   PNGs` — a single straight vertical line down **column C**, to the right of `GPU`. **No horizontal
>   segment, no bend.** It crosses nothing.
> - `/data` **top edge** → `subprocess` **bottom edge** — `slide files` — **dashed**, pointing
>   **upward**, a single straight vertical line with no bends, because `/data` sits directly below
>   `subprocess`. It touches no other arrow.
> - the **right edge of the `MOUNTED VOLUMES` panel** → `routes/` **bottom-right corner** — `image
>   bytes` — a single **dashed** arrow running right into the empty right channel, up the outside of
>   the panels, then left into `routes/`
>
> **Routing rules — these matter more than anything else in the image:**
> - **Every arrow begins on the edge of a card or panel and ends on the edge of a card or panel.**
>   Both ends must visibly touch an edge. An arrow whose tail lands on another arrow — anywhere
>   along that arrow, including where two lines meet — is wrong, even if it looks tidy. If a line
>   appears to start out of another line, the drawing has failed.
> - **Every arrow is a single independent line. No arrow may branch off, tee into, run alongside, or
>   share any segment with another arrow. No forks, no Y-junctions, no T-junctions, no trees, no
>   shared trunks.**
> - When two or more arrows leave the same card, they leave from different points on different
>   edges, separate immediately, and stay clearly apart along their entire length.
> - No arrow may cross, touch, or pass behind any card, panel, group label, or text.
> - **Crossings.** Exactly three exist, and all three are unavoidable consequences of the layout:
>   - `dataset CSV` crosses `command line`, in column A
>   - `dataset CSV` crosses `job record`, in column A, higher up
>   - `PNG figures` crosses `tensors`, in column B
>
>   Draw each as a clean 90° crossing: the **vertical line runs straight through, unbroken**, and the
>   **horizontal line carries a small semicircular hop** over it. Neither line may start, stop, bend,
>   change width, or gain an arrowhead at a crossing. A crossing is two lines passing — never two
>   lines meeting. No other pair of arrows may cross anywhere in the image.
> - Amber is used only for the two `jobs` arrows. Every other arrow is grey.
> - **Nothing points into `lib/api.ts`, `React 18 + TypeScript`, or `components/`.** The only arrows
>   touching the frontend are the two leaving `lib/api.ts` and the one entering the panel from above.
> - Every card must have at least one arrow touching it.
>
> **At the very bottom**, one line of small text with a short amber rule to its left:
> `Every training, visualization and inference job reaches the GPU through the jobs table.`
>
> **Render only the text listed above, spelled exactly as written.** Each label appears exactly once.
> Do not invent additional labels, file names, captions, titles, or annotations. Do not draw any
> dimensions, measurements, pixel or point sizes, rulers, grid lines, alignment guides, callout
> numbers, legends, keys, colour swatches, scale bars, watermarks, code snippets, or UI chrome. No
> 3-D, no gradients, no isometric perspective, no drop shadows beyond the faintest lift, no clip-art
> servers or clouds, no gloss.

---

## Rejection checklist

Regenerate on any of these:

- **Any arrow whose tail begins on another arrow instead of on a card or panel edge.** Trace each of
  `dataset CSV`, `PNG figures` and `features, PNGs` upward from its arrowhead: each must arrive at
  the bottom edge of a `services/` card without ever touching `command line` or `tensors` except as
  a clean 90° crossing.
- **Any arrow that branches out of, tees into, or shares a segment with another arrow.**
- An arrow that starts in mid-air instead of on a card or panel edge.
- Any bend, jog, or horizontal segment in `dataset CSV`, `PNG figures`, `features, PNGs` or
  `slide files` — all four are single straight vertical lines.
- A crossing where the vertical is the one that hops, or is broken, or stops at the junction. The
  vertical always runs through; the horizontal hops.
- More or fewer than three crossings in the whole image, or a crossing where the two lines meet
  rather than pass.
- `GPU` stretched to the right edge of its panel, leaving no column C for `features, PNGs`.
- `train / val / test` anywhere — the dataset is no longer split.
- A caption claiming the jobs table is the **only** channel to the GPU — it is not, and the wording
  above is chosen to be true. Do not "tighten" it back.
- A sixteenth arrow from `routes/` to `subprocess` — the synchronous first extraction is out of
  scope for this figure on purpose.
- `job record` pointing into `worker.py` instead of out of it.
- An amber arrowhead anywhere except on the `jobs` pill and on `worker.py`'s left edge.
- Anything pointing into `lib/api.ts`, `React 18 + TypeScript`, or `components/`.
- `slide files` pointing down into `/data`.
- An arrow passing over a panel label, a card title, or any other text.
- Row 3 filling its full width — `worker.py` must be narrow, with wide gutters beside it.
- Any label longer than two words, any duplicated label, or any misspelling.

**What must not be added back:** router names, service file names, job-type names, port numbers,
endpoint counts, cache sizes, poll intervals. All of that belongs in the prose around the figure.
