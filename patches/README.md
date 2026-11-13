# Engine patches

`setup.ps1` fetches `dream-recomp` at a pinned commit. This directory holds the project's delta
against that commit, so a fresh clone builds the same engine this project was developed on.

| Patch | What it carries |
|---|---|
| `0001-engine-local-changes.patch` | The sum of ledger entries 001–021 in `docs/ENGINE-CHANGES.md`: the diagnostics and instruction tracer, the hook-dispatch fix, the replay host-state skip, the SR-write rule, the exception-handler stop address (the translated-path fault), the flash side-effect marking, the inlined RAM fast path, cached host memory for the offscreen readback, hor+ widescreen, presentation decoupled from the 60 Hz logic, and 4:3 pillarboxing for flat 2D screens (`frame_uses_depth`, plus the presenter's bar discard). Touches `runtime/`, `translator/`, `render/` and `cmake/`. |

`setup.ps1` applies each patch after fetching the engine, and is safe to re-run: a tree that
already has the patch is detected with `git apply --reverse --check` and left alone.

## Refreshing the patch

When the ledger changes, regenerate the file from two trees with the same layout: `a/` a pristine
engine at the pinned commit, `b/` the working engine, both containing the changed source
directories (`runtime/`, `translator/`, `render/`).

```powershell
# a/ = freshly fetched engine; b/ = the checkout with the changes applied
git diff --no-index --no-renames --no-color --src-prefix= --dst-prefix= a b > 0001-engine-local-changes.patch
```

Apply it with `git apply -p1` from inside `engine/`. Verify before committing:

```powershell
cd engine; git apply --check <repo>\patches\0001-engine-local-changes.patch
```

The engine is GPL-2.0 and this repository is a derivative work (see `LICENSE`); the patch contains
only project-written changes, no game data.
