# SARecomp / KatanaRecomp — provenance log

Purpose: record what was *learned* from the reference project, never code. One entry
per study session. Anything copied from this project is out of bounds until a written
licence grant exists (`docs/04-REFERENCE-REPOS.md`, boundary rules).

Repository: <https://github.com/sonicfreak1337/SARecomp>
Licence at time of review: **none** (`license: null`; no `LICENSE` file in the tree).
Reference status: read-only benchmark.

---

## Session 1 — 2026-11-04 — repository survey

**What was inspected:** repository metadata (via GitHub API), the full file tree, the
README, and the documentation index. Nothing was cloned or executed.

**What was learned (ideas only):**

* The project separates concerns into a runtime/port layer (`src/sonic_*`) and a build
  layer with one CMake module per concern (`cmake/Linux*.cmake`, `cmake/Sonic*.cmake`).
  The per-concern module split is a pattern worth copying as a *structure* (we would
  write our own files).
* Frame pacing is treated as an explicit contract: files named around an
  "execution clock" and a "frame completion contract" exist, and the public docs
  distinguish simulated frame rate from display frame rate. That vocabulary is useful
  for our M9 design (render rate decoupled from 60 Hz logic).
* Input is layered: device handling, bindings, a native input *policy*, and separate
  controller-prompt sets. This matches what a launcher needs (rebinding + prompt
  glyphs) and is a better shape than wiring device inputs straight into game hooks.
* The renderer has a model pipeline with explicit hierarchy/palette batching stages,
  rather than one monolithic draw path. Relevant to our PVR2→Vulkan work.
* A native texture catalogue and sound catalogue exist as first-class concepts —
  i.e. the port layer can override assets without touching game code. That is the
  design we want for texture packs (M9).
* The installer/disc-import flow lives in a dedicated setup subproject plus a
  documented installation guide, and stores a machine-readable tool descriptor
  (`baseline/dev-tools.json`) — a good model for our launcher (M8).
* Validation is evidenced by stored baseline bundles (`baseline/*.json`) rather than
  prose claims. Worth adopting: our milestones should produce artefacts, not assertions.

**What was not done:** no file was copied, no algorithm was transcribed, no code was
vendored. No claim in their README was independently reproduced.

**Follow-up:** send the permission request in `permission-request-draft.md`; if a grant
arrives, re-evaluate reuse for the **port layer only** (input bindings, frame pacing,
launcher), never for the translator or runtime wholesale.

---

## Template for future entries

```
## Session N — YYYY-MM-DD — <topic>
Inspected: <files/dirs>
Learned (ideas): <bullets>
Copied: none
Open questions: <bullets>
```
