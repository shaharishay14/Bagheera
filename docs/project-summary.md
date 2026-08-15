# Bagheera - Product Overview, Working Process, and Project Retrospective

**Team:** Shahar Ishay 322854308 · Daniel Rubinstein 314621467· Dolfin Varshev 315853101
**Client:** The Pathology Research Laboratory, Sheba Medical Center - Dr. Alexander Lobel
**Period:** November 2025 - August 2026

---

## 1. The product

**Bagheera is a browser-based control room for computational-pathology pipelines.**
It takes a research lab from a folder of raw whole-slide images (WSIs) all the way to a
trained model, a set of interpretable visualizations, and inference on new slides, without
anyone opening a terminal.

### 1.1 The problem we were asked to solve

The Sheba pathology research lab works with two open-source pipelines published by the
Mahmood Lab at Harvard Medical School:

- **TRIDENT** segments tissue, tiles each whole-slide image into patches, and runs a patch
  encoder to produce a per-slide feature file (`.h5`).
- **PANTHER** learns a set of *prototypes*, representative tissue patterns, over those
  features using an unsupervised mixture model.

Both are research-grade command-line tools. Using them means composing long shell
invocations, hand-editing CSV manifests, keeping track of which output directory belongs to
which experiment, and reading results out of a Jupyter notebook. That is a workflow built
for the data scientists, not for the pathologists, who need what those pipelines can do
without, in most cases, knowing how to code at all. Bagheera helps both. It gives the Sheba
data scientists one intuitive place to do the entire job through a GUI instead of a
terminal, and it lets the pathologists enjoy the capabilities of the pipelines through an
interface that is easy to use.

The lab's request was direct: *make this user friendly for both users, data scientists and
pathologists.* Wrap the pipelines in an interface the lab can drive without a developer, and
make the results of a training run something you can look at, reason about, and share as
knowledge, all in one place, rather than something you have to reconstruct from files on
disk.

### 1.2 Two roles, one system

Bagheera serves **two different people**, and most of our design decisions come from keeping
their halves of the workflow distinct:

- **The data scientists** own everything up to a trained model. They configure and run
  TRIDENT feature extraction, decide where the data and the outputs live on disk, choose the
  patch encoder, prepare the manifest CSV and the split, set PANTHER's hyperparameters, and
  submit training runs. Once a run finishes they read the analysis the system renders for
  that model to judge whether it came out sound. Their half of the UI is deliberately dense
  with paths, parameters, job status and streaming logs, because they need visibility into
  what the pipeline is actually doing and control over every knob.
- **The pathologists** are the domain experts and train nothing. They take an *already
  trained* model, run **inference** on new slides, read the visualizations that come back,
  and record what they see as **notes and annotations** on the model, on individual
  prototypes, and on each inference. Their half of the UI hides the machinery entirely: pick
  a model, pick slides, look at the results, write down what they mean.

**The visualizations are what the two roles share.** After every training run Bagheera
renders a fixed set of analysis panels for the model: a per-slide panel showing where each
prototype lands on real tissue (Section A), a validation-consistency view (Section B), an
on-tissue UMAP and abstract scatter of the feature space (Section C), and a prototype
dictionary showing the patches that define each prototype (Section D). Inference produces
its own per-slide views: a prototype heatmap over the slide, a mixture plot, example
patches, and a t-SNE. The data scientists read those panels as evidence about the model, the
pathologists read the same panels as evidence about the tissue. Rendering them
automatically, storing them, and putting them one click away from the model is a large part
of what Bagheera does, because in the original workflow every one of those figures had to be
produced by hand in a notebook.

That split is why the models browser is separate from the training pages, why inference is
reachable directly from a model without passing through any configuration form, and why
prototype labels, model notes, and inference notes are first-class stored data rather than
an afterthought. The data scientists produce a model, the pathologists turn it into
knowledge, and Bagheera is the surface where that handoff happens.

### 1.3 What Bagheera does

The system covers the full research loop as four guided steps in the browser. The first
three belong to the data scientists, the fourth is where the pathologists take over:

1. **Extract features (TRIDENT).** Pick a directory of slides, name the dataset, choose a
   patch encoder, and run. Bagheera invokes TRIDENT and produces the per-slide feature
   files.
2. **Define a split.** A manifest CSV is validated, a `slide_id` column must exist and the
   `.tif` extension is stripped automatically so PANTHER receives clean IDs, and the result
   is turned into a reproducible split on disk.
3. **Train prototypes (PANTHER).** Set the hyperparameters and submit. The run is queued
   rather than blocking the HTTP request, and the UI navigates straight to the new model's
   page where progress and a live job log stream in.
4. **Review, run inference, and annotate.** Browse the trained models, read the four
   analysis panels the system renders after training, place models **side by side** on the
   same slide in the Model Comparison view, run a chosen model on **new slides** through the
   inference page, and record the reading: a human-readable **label** on each prototype,
   **notes** on the model, **notes** on each inference.

The labelling and annotation features came straight out of the lab's requirements. Knowledge
has to be shareable, and nobody should have to work out a second time what a colleague
already worked out once. On its own a prototype is only an index, prototype 7 out of however
many prototypes were requested in PANTHER's hyperparameters, and it means nothing until a
pathologist looks at the patches it collected and writes down something like *"stroma with
lymphocytic infiltrate"*. Bagheera stores that reading against the model, so it stays
attached to the prototype for whoever opens it next instead of being worked out again from
scratch.

---

## 2. The working process

### 2.1 Working with the client

Working with the Pathology Research Laboratory at Sheba Medical Center was one of the best
parts of this project. We were building for professionals at the top of their field, in a
domain where the work carries real clinical weight, and getting to see how that lab actually
operates taught us more about building software for expert users than a specification ever
could.

The engagement did not follow the usual loop of building something, showing it, and being
told what was wrong with it. Dr. Alexander Lobel came to us with the requirements already
worked out, functional and non-functional, scoped, and clear about who would use the system
and for what. Very little of it changed over the course of the project. Our task was not to
discover what was needed, it was to understand it precisely and translate it faithfully into
a working system.

The meetings each had a distinct purpose:

- **Requirements, with Dr. Lobel.** He set out what the system had to do, for whom, and
  under what constraints, and walked us through the clinical and research context the
  software would sit inside.
- **Working sessions with the lab's data scientists.** They gave us the documents and the
  code we needed and, more valuably, showed us how they actually work: how a dataset is
  prepared, how TRIDENT gets configured, what they look at once a training run finishes.
  Those sessions are what allowed us to translate a command-line workflow into a coherent
  GUI rather than a set of forms that happen to call scripts.
- **Final review with Dr. Lobel.** We presented the finished system and he gave us a short
  list of final adjustments. The most substantial was replacing K-fold cross-validation with
  a single model trained on all slides, which we implemented along with the Model Comparison
  page so that models could still be inspected against one another.

Working with a client who knows exactly what they want is its own discipline. It puts the
burden on you to understand precisely, to ask the right questions early, and to resist
substituting your own assumptions for the ones the client already made deliberately.

### 2.2 How we worked as a team

The three of us, Daniel, Dolfin and Shahar, built this together, almost always at the same
time. Nearly all of the work happened in shared online sessions where we went through the
system piece by piece and discussed every decision as we made it, rather than splitting the
project into three separate lanes and stitching the results together afterwards. It made the
work slower in places and much better everywhere else, because there was no part of Bagheera
that only one of us understood.

Some of us were in reserve duty during the project and some were working alongside it, so
our hours were often evenings and weekends. That never became a problem. We found the time
and we got it done together.

Not all three of us knew each other before this project started. The connection was natural
and easy from the beginning, and we came out of it better friends than we went in. It was
one of the most meaningful and genuinely enjoyable experiences of our degree.

---

## 3. The difficulties

**The GPU machine at Sheba was the one real constraint on this project.** All of the actual
work, TRIDENT feature extraction, PANTHER training, anything that touches a real slide, runs
on the lab's remote workstation where the data and the GPU live. That environment could not
be replicated locally, and access to it was not something we controlled:

- **It was a shared resource.** Other people at the lab were working on the same machine, so
  we had to coordinate around them rather than use it whenever we were ready to.
- **It was not always running.** The lab had ongoing technical problems with it, and there
  were stretches where the machine was simply down or unreachable.
- **We were switched to a different machine near the end of the project**, which meant
  rebuilding the entire environment from scratch on new hardware at exactly the point where
  we most needed stability.
- **We did not always get a response.** Requests for access, or for help with a broken
  machine, sometimes went unanswered for a while, and there was nothing to do but wait.

Our own schedules were not the difficulty. Being in reserves or holding a job meant working
evenings and weekends, and we did that without much friction. The harder part was that the
machine was not reliably available during those hours either.

The one thing we built specifically to work around this was an **idempotent demo seeder**
(`scripts/seed_demo.py`), which populates the database with rows covering every state the UI
has to render. A large part of the interface only appears once real data exists, such as
model cards, job status and analysis panels, and the seeder let us confirm that those
components looked and behaved the way we intended without a pipeline run behind them. It was
a way to verify the UI, not a substitute for testing the system. Anything involving the real
pipelines had to wait until the machine was available to us.

---

## 4. How we got to the final stage

The project moved through six recognizable phases.

**Phase 0, requirements and design.** We met with Dr. Lobel several times, including a visit
to Sheba Medical Center where he showed us around and explained the entire process end to
end: how a tissue sample arrives, how it is prepared and scanned, and everything that
happens to it before it reaches a model. He laid out the requirements and specifications
there, and we turned them into the detailed design document, which we sent back to him for
confirmation before writing the system.

**Phase 1, a working shell.** The first commits built the skeleton end to end: a FastAPI
service, a React SPA, an annotations feed, a comparison page, and a job queue with cancel
and drag-reorder, all running against mock data. The value of this phase was that it turned
the design into something concrete and gave every later phase a structure to build into.

**Phase 2, restructuring around the real pipelines.** This is the phase the working sessions
with the lab's data scientists fed directly into. They handed over the code and the
documents we needed and walked us through their day-to-day workflow, and we reorganized the
entire project around the actual TRIDENT/PANTHER pipeline: model groups, async jobs, the
visualization layer, and the inference pipeline, along with the first architecture
documentation. This is where Bagheera stopped being a generic job-runner UI and became a
tool for this specific lab.

**Phase 3, making it real on the GPU box.** Docker and NVIDIA deployment, then the long
sequence of integration fixes: split paths, encoder-derived input dimensions, collision-safe
feature directories, and missing scientific dependencies. Unglamorous, essential, and the
phase most constrained by machine availability.

**Phase 4, the analysis layer.** Sections A, B, C, and D were implemented one at a time to
match the figures in the PANTHER paper and Dr. Lobel's requirements, followed by a run of
visualization refinements: framing panels on tissue, tiling regions of interest on the true
level-0 patch pitch, ranking ROI windows by tissue occupancy, and drawing per-patch borders,
until the rendered output looked like something a pathologist would recognize. Alongside
this came model deletion and manifest-CSV validation.

**Phase 5, consolidation and submission.** Single-model PANTHER training and the Model
Comparison page replaced K-fold as the primary flow, following Dr. Lobel's final review. A
pytest suite covering routes, services, and the worker, and a Vitest suite covering
components, the API contract, and queue ordering, went in behind them, along with the test
documentation, the figure specifications and renders, and the Detailed Design and STP/STD
submission documents.

---

## 5. What we take away

Technically, we built a full-stack system that wraps two substantial research pipelines,
runs GPU workloads asynchronously, renders scientific visualizations, and separates a data
scientist's workflow from a pathologist's inside a single interface, all of it constrained
to one machine with one GPU.

The rest of what we learned was not technical. We learned what it is like to build for a
client who is expert in their own field and precise about what they want. The work is
translation, not invention, and it rewards understanding the requirement exactly rather than
improving on it uninvited. We learned to run a project around a critical resource we did not
control, shared with other people, unreliable, and replaced under us near the end, and to
keep making progress on everything that did not depend on it. And we learned that three
people who mostly did not know each other can build something substantial by simply doing
the work together, in the same call, decision by decision.

We genuinely enjoyed building this. Bagheera was built to help both sides of the lab, the
research team that trains the models and the pathologists who use them, and it is an
impactful tool in work whose end purpose is classifying tissue as cancerous or not. If it
helps Sheba move faster and share what they learn in one place, the work has an impact well
beyond anything we could measure in commits.
