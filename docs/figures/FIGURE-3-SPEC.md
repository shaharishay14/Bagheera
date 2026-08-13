# Figure 3 — generation prompt

**Target file:** `docs/figures/fig3_usecase.png`
**Caption in the document:** *Figure 3 — Use-case model.*

This file was a build spec for a plotting script. It is now a **copy-paste prompt for an image
model**, in the same design language as `FIGURE-1-SPEC.md`: white cards on near-invisible warm
panels, one amber accent used sparingly, uppercase letterspaced group labels, no measurements
anywhere on the image. Paste the block under **The prompt** verbatim.

**Latest correction.** The previous render sized each panel to its own contents, so the pathologist's
five cards came out smaller than the researcher's five and UC6's label overran its card. The prompt
now builds **one three-by-five grid across the whole boundary first**, sizes the cell from the
longest label (UC6), and treats the group panels as tinted backgrounds that can never resize a card.

---

## The actors — two roles, split by what they are trying to find out

This revision replaces the old `Pathologist / Researcher` compound actor and the separate `Operator`
with **two real roles**, because the two do different work for different reasons:

- **The researcher builds and runs the machine.** Adding datasets, extracting features, building
  manifests, setting hyperparameters and training, keeping the queue and the model library in order,
  and standing the stack up. Their question is *does the pipeline produce a model.*
- **The pathologist reads what the model found and judges it.** Inspecting panels, moving the region
  of interest, naming prototypes and writing notes, comparing models on the same tissue, and running
  a trained model on new slides. Their question is *is this model any good.* Naming a prototype and
  writing a note is not bookkeeping — it is the act of judging the model, which is why UC7 sits with
  the pathologist and not with the operator of the machine.

| Actor | Use cases |
| --- | --- |
| **Researcher** | UC1, UC2, UC3, UC4, UC10, UC11, UC12, UC13 |
| **Pathologist** | UC5, UC6, UC7, UC8, UC9 |

> **This diverges from the document.** §8 currently opens *"Twelve are driven by the pathologist or
> researcher from the browser; the thirteenth is the operator task of deploying and configuring the
> stack."* That sentence describes one compound actor plus an operator and will contradict the
> figure. It needs rewriting to the two-role split above, and UC13's primary-flow cell should say
> *the researcher* rather than *the operator*. Nothing else in §8 changes — the thirteen use cases
> and their primary flows are untouched.

**The one judgement call:** UC4 `Browse and manage models` is filed under the researcher, next to
UC12, because in the code it is library management — search, dataset filter, sort, favourites,
rename, delete. A pathologist obviously also browses to reach UC5. If you would rather it sat with
the pathologist, it moves cleanly: it is the last card of the second panel and the first slot of the
third is free.

## The use cases, verified against §8 of the document

Labels are the document's, character for character. **Do not paraphrase them.**

| ID | Label on the card | Actor | `queued` pill |
| --- | --- | --- | --- |
| UC1 | `Extract features (TRIDENT)` | Researcher | no |
| UC2 | `Build a training manifest` | Researcher | no |
| UC3 | `Train a PANTHER model` | Researcher | **yes** |
| UC4 | `Browse and manage models` | Researcher | no |
| UC5 | `Inspect a model` | Pathologist | no |
| UC6 | `Re-pick or click-select a region of interest` | Pathologist | no |
| UC7 | `Label prototypes and take notes` | Pathologist | no |
| UC8 | `Compare models on one slide` | Pathologist | **yes** |
| UC9 | `Run inference on new slides` | Pathologist | **yes** |
| UC10 | `Manage the job queue` | Researcher | no |
| UC11 | `Read a job log` | Researcher | no |
| UC12 | `Delete a model` | Researcher | no |
| UC13 | `Deploy and configure` | Researcher | no |

### Why exactly those three pills

Every `enqueue_job` call site in the backend, and the use case it belongs to:

| Call site | Job type | Use case |
| --- | --- | --- |
| `routes/panther.py:330` | `panther_train` | **UC3** |
| `routes/panther.py:229` | `panther_train` | UC3, legacy K-fold — not creatable from the interface |
| `routes/models.py:484` | `render_slide` | **UC8** |
| `routes/inference.py:165`, `:346` | `inference` | **UC9** |
| `routes/models.py:273` | `post_train_viz` | UC5, re-shuffling preview slides |
| `services/panther_train.py:158`, `:214` | `post_train_viz` | enqueued **by the worker**, not by a user |

UC3, UC8 and UC9 are the three where a user submits something and is answered before the work runs.
UC5's panels are produced by a job that UC3 enqueues automatically — marking UC5 would suggest the
user queues it, which is not what happens. **UC1 carries no pill**: `POST /api/trident/run` calls
`runner.execute` on the request thread, so submission blocks until extraction finishes (§14 of the
document, *"Feature extraction blocks its request"*).

The pills also happen to sit one per actor concern: the researcher queues a training run, the
pathologist queues a comparison render and an inference.

### Accuracy notes — do not "improve" these

- **UC12 reads `Delete a model`**, matching the §8 table. An earlier draft read "Delete a legacy
  model group", which is what the code does — `DELETE /api/models/model-groups/{id}` is keyed on a
  grouping identifier the current training path never populates. The document handles that
  deliberately: the use case is named for its intent and the gap is recorded in §14 (*"Model deletion
  is not yet exposed for every model"*). The figure follows the document.
- **UC5 reads `Inspect a model`** with no section list. §6.2 of the document is titled *Prototype
  similarity within a slide*, not "Section B", and Section B is skipped entirely for single-model
  runs. Naming sections on the card would raise a question the card cannot answer.
- **UC2 reads `Build a training manifest`, never "split".** §7.2 is explicit: the HTTP resource, the
  table and the directory are all called `splits` for historical reasons, but nothing is
  partitioned — every row goes to `train.csv` — and the artifact is precisely a training manifest.
- **UC6's controls are synchronous** (§7.3, *"Both operations are synchronous and re-use a cached
  array of coordinates and assignments"*), which is why it carries no pill.

### Deliberately not drawn

- **A separate `Operator` actor.** Deployment is configuration work, and configuration is the
  researcher's. A third actor holding one use case implied a third person who does not exist in a
  single-user system.
- **«include» and «extend» arrows.** Thirteen dashed dependency arrows are what made an earlier
  attempt illegible; none of the modelled relationships need them. The amber pills and the footer
  line carry the queue relationship in less ink.
- **A "System", "Database" or "Worker" actor.** The worker thread is internal. There are two actors.
- **Decomposition of UC5 into its four panels** — that lives in the §6 tables.
- **The legacy K-fold training flow as its own use case.** It is not creatable from the interface.
- **Shared use cases.** No card belongs to both actors. A use case with two association lines is the
  fastest way back to the fifteen-line tangle this figure was rebuilt to escape, and nothing in the
  system is genuinely co-owned.

---

## The prompt

> Create a clean, modern UML use-case diagram as a single flat vector illustration on an opaque white
> background. Landscape, roughly 4:3, high resolution.
>
> **Overall feel:** calm, spacious, editorial — the visual language of well-designed product
> documentation, not a legacy UML tool. Flat shapes, generous empty space, a restrained warm palette,
> one clear reading direction from top to bottom. Roughly a third of the canvas should be empty
> space. When in doubt, make things smaller and the gaps larger.
>
> **Palette:**
> - Page background: pure white.
> - Group panels: a soft warm off-white, almost imperceptible against the page.
> - Cards: white with a very light warm-grey hairline outline and a barely-there soft shadow.
> - Highlight colour: a warm amber-orange, used for exactly three small pills and one short rule at
>   the bottom, and nothing else.
> - Actors and boundary: warm grey line art, thin and even.
> - Text: very dark warm brown for titles, medium warm grey for secondary text.
>
> **Typography:** a single geometric humanist sans throughout, two weights only. Card labels in
> regular dark brown; the small `UC` identifiers in semibold medium grey; group and boundary labels
> in small letterspaced uppercase grey. All text horizontal, left-aligned inside cards, crisply
> rendered and correctly spelled.
>
> **Layout — a narrow actor column on the left, a large system boundary on the right.**
>
> **The boundary** is a single rectangle with a thin warm-grey outline and no fill, occupying roughly
> the right three quarters of the canvas with clear white margin all around it. Its label
> `BAGHEERA — SYSTEM BOUNDARY` sits in small letterspaced uppercase grey just inside its top-left
> corner, with air beneath.
>
> **One grid governs the whole boundary. Build it before you draw anything else.**
>
> Rule the inside of the boundary into **three equal columns and five equal rows** — fifteen
> identical rectangular cells, the same width and the same height as each other, evenly spaced, with
> the same gap between every pair of neighbours. This grid spans the full inner width of the boundary
> and does not change from top to bottom. **Thirteen cells hold a card; two are left empty.**
>
> **Size the cell from the longest label first.** The longest label in the figure is UC6,
> `Re-pick or click-select a region of interest`. Set the cell wide enough and tall enough that this
> label sits comfortably inside a card on **two lines**, with generous padding on all four sides and
> the identifier line above it. Then give **every one of the thirteen cards that exact size** — the
> short labels simply have more empty space beneath them. Do not shrink a card to fit its own text
> and do not grow one either.
>
> **The three group panels are only tinted backgrounds laid behind rows of this grid.** They are soft
> warm off-white rectangles, each with a small letterspaced uppercase grey label above it inside the
> boundary and clear air beneath the label. A panel never resizes, re-spaces, or re-aligns the cards
> sitting on it. Leave a wide empty band between one panel and the next.
>
> 1. Panel `PREPARE AND TRAIN` covers **row 1** — `UC1` `UC2` `UC3`
> 2. Panel `OPERATE AND MAINTAIN` covers **rows 2 and 3** — `UC4` `UC10` `UC11`, then `UC12` `UC13`
>    and an empty third cell
> 3. Panel `INTERPRET AND APPLY` covers **rows 4 and 5** — `UC5` `UC6` `UC7`, then `UC8` `UC9` and an
>    empty third cell
>
> **Panels 2 and 3 have exactly the same shape** — two rows, five cards, one empty cell in the same
> corner — so they must come out exactly the same width and exactly the same height, with cards of
> exactly the same size. If the bottom panel looks smaller or its cards look tighter than the middle
> one, the grid was not built first and the drawing has failed.
>
> Leave the two empty cells empty. Do not stretch a card across an empty cell.
>
> **Each card** holds its identifier in small semibold grey on the first line, and its label beneath,
> left-aligned to the same gutter on every card in the image:
>
> - `UC1` — `Extract features (TRIDENT)`
> - `UC2` — `Build a training manifest`
> - `UC3` — `Train a PANTHER model`
> - `UC4` — `Browse and manage models`
> - `UC5` — `Inspect a model`
> - `UC6` — `Re-pick or click-select a region of interest`
> - `UC7` — `Label prototypes and take notes`
> - `UC8` — `Compare models on one slide`
> - `UC9` — `Run inference on new slides`
> - `UC10` — `Manage the job queue`
> - `UC11` — `Read a job log`
> - `UC12` — `Delete a model`
> - `UC13` — `Deploy and configure`
>
> **Three cards only — `UC3`, `UC8` and `UC9` — carry a small amber pill** reading `queued`, sitting
> at the card's top-right corner, clear of the text. Pale amber fill, amber outline, small amber
> text. No other card carries a pill or any other marker.
>
> **Two actors**, outside the boundary, in the left column: simple line-art stick figures in warm
> grey, each with a two-line caption beneath it in dark brown.
> - The upper actor, vertically centred against the first two panels: `Researcher` `(builds and runs)`
> - The lower actor, vertically centred against the third panel: `Pathologist` `(reads and judges)`
>
> **Three association lines**, and only three. Thin, plain, light warm grey, **with no arrowheads at
> either end** — these are UML associations, not flow. Each is a single straight horizontal line
> running from the actor's caption block to the **left edge of a group panel**, crossing the boundary
> outline once on the way:
> - `Researcher` → the left edge of panel `PREPARE AND TRAIN`
> - `Researcher` → the left edge of panel `OPERATE AND MAINTAIN`
> - `Pathologist` → the left edge of panel `INTERPRET AND APPLY`
>
> **Rules — these matter more than anything else in the image:**
> - The two lines leaving the upper actor leave from **two different points on its right edge**,
>   separate immediately, and stay clearly apart for their entire length with an even gap between
>   them. They never touch each other or the third line.
> - **No arrow may branch off, tee into, run alongside, or share any segment with another.** No
>   forks, no Y-junctions, no T-junctions, no shared trunks.
> - **No line crosses another line anywhere in the image.** The layout makes this achievable — the
>   researcher's two panels are the top two and the pathologist's is the bottom one, so nothing needs
>   to reach past anything. If a crossing seems necessary, move the actor, not the line.
> - The only thing a line may cross is the boundary outline, once, at a right angle.
> - **No line passes through, over, or behind a card, a panel label, or any text.** Every line ends
>   on a panel's left edge, in clear empty space.
> - Both actors sit entirely outside the boundary rectangle. All thirteen cards sit entirely inside
>   it.
> - **All thirteen cards are identical in width and in height**, in every panel, regardless of how
>   much text each one holds. The cards in `INTERPRET AND APPLY` are the same size as the cards in
>   `OPERATE AND MAINTAIN` and the same size as those in `PREPARE AND TRAIN`.
> - **All text stays inside its card**, with clear padding between the last character and every card
>   edge. A label wraps onto a second line if it needs one; it never runs past the outline, never
>   overlaps the card below or beside it, and is never shrunk to a smaller size than the other labels
>   to make it fit. Every label on the figure is set at the same size.
> - Every card's identifier sits on its own line at the top, and every label starts on the same line
>   beneath it, left-aligned to the same gutter across all thirteen cards.
>
> **At the very bottom**, below the boundary, one line of small text with a short amber rule to its
> left:
> `Use cases marked queued are answered immediately and finish on the shared job queue of UC10.`
>
> **Render only the text listed above, spelled exactly as written.** Each label appears exactly once.
> Do not invent additional use cases, actors, labels, captions, titles, or annotations. Do not draw
> any dimensions, measurements, pixel or point sizes, rulers, grid lines, alignment guides, legends,
> keys, colour swatches, scale bars, watermarks, code snippets, stereotype guillemets, or UI chrome.
> No 3-D, no gradients, no isometric perspective, no drop shadows beyond the faintest lift, no gloss.

---

## Rejection checklist

Regenerate on any of these:

- **A third actor of any kind** — `Operator`, `System`, `Database`, `Admin` or `Worker`. There are
  exactly two: `Researcher` and `Pathologist`.
- A compound actor caption reading `Pathologist / Researcher`. The whole point of this revision is
  that they are two people with two questions.
- **More than three association lines**, a line running to an individual card instead of to a group
  panel's left edge, or a panel touched by both actors.
- Any association line with an arrowhead — UML associations have none.
- Any line crossing another line, passing over a card, or passing over a panel label.
- Any line that branches out of, tees into, or shares a segment with another line.
- An actor drawn inside the boundary, or a use case drawn outside it.
- A use case in the wrong panel. `UC5` `UC6` `UC7` `UC8` `UC9` are the pathologist's five and sit in
  the bottom panel; the other eight are the researcher's.
- **A label paraphrased.** Every one of the thirteen must match the table above character for
  character. In particular: `Build a training manifest`, never anything containing "split";
  `Delete a model`, not "model group"; `Inspect a model`, with no section list; `Extract features
  (TRIDENT)`, with no "synchronous" appended.
- A `queued` pill on any card other than `UC3`, `UC8`, `UC9` — and never on `UC1`, which blocks its
  request.
- More or fewer than thirteen cards, or identifiers out of order within a panel.
- **Cards in `INTERPRET AND APPLY` smaller than cards in `OPERATE AND MAINTAIN`.** The two panels
  hold five cards each in the same two-by-three shape and must come out identical. Compare them
  directly before accepting the render.
- **Any label touching, crossing or spilling past its card's outline** — check `UC6`
  `Re-pick or click-select a region of interest` first, it is the longest and it fails first.
- A label set smaller than the others to squeeze it in, or a label on three or more lines.
- Cards of unequal width or height anywhere, or labels not aligned on a common gutter.
- Ellipses or stadium shapes instead of cards — the card is the shared language of all three figures.
- `«include»` or `«extend»` arrows, dashed dependency lines, or guillemet stereotypes anywhere.
- Rows stretched to fill their panel — the two empty slots in `OPERATE AND MAINTAIN` and `INTERPRET
  AND APPLY` are deliberate and hold the three-column grid.

**What must not be added back:** primary-flow descriptions, endpoint names, job-type names, hex
colours, pixel sizes, print widths, the K-fold path. All of that belongs in the §8 table and the
prose around the figure.
