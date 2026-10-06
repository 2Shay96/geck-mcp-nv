# GECK MCP bridge status

## 6 October 2026 — Codex takeover

Task: improve GECK MCP usability; investigate fix 7 (game console form resolution). User approved checked bridge milestones to GitHub. Branch: `codex/bridge-console-fix`; baseline `fdaf790`, clean before this work, matching freshly fetched origin/main.

Created `HANDOFF.md` and `MCPworkflow.md` from the recovered notes and current user instructions. No implementation changes yet. Fresh Windows verification: 168 bridge tests passed, 3 skipped; all 6 ESP verifier tests passed. Salvatore profile dry-run validates and reproduces installed Build C exactly: `6e3375186e2f46894e8d5eae45519e0292a62908592316e844d82cbb74349cde`. No workshop or game files were changed.

Initial comparison: backup `5a3f7fbf...` versus bridge build backup `382f249d...` has identical quest EDIDs and record headers, but different main-quest DATA flags, HEDR next-object-ID, and several creature fields. The same differences appear between GECK-saved backup `17222cef...` and current Build C. All four QUST records are present under the correct QUST top group in every inspected copy: main quest `0100080F`, summon `01000818`, far `01000819`, reset `0100081A`. Their record headers use flags 0 and form version 15. This does not establish the cause. Details and runtime test sequence: `docs/CONSOLE-DIAGNOSIS.md`.

Direct MCP verification: `geck_status` succeeded against the running GECK (PID 19108), with no unsaved changes and Object Window, Cell View and Render Window all visible/reachable. `geck_plugin_inspect(which="installed")` succeeded and confirmed the installed Build C hash and match to build. Private workshop sources and installed plugin have not been changed.

Runtime result: 2Shay reported clicked reference `0A000813`, confirmed `sqv 0A00080F` shows quest variables, and confirmed `startquest 0A000818` summons Salvatore without the original error. The unchanged bridge-built plugin works: the historical prefix 01 was incorrect for this running load order. Fix 7's two numeric-ID failures are resolved without writer changes. Updated `bridge/README.md` with file-local versus runtime FormID guidance. Vanilla EditorID lookup and far/reset commands were not retested.

GitHub milestone: recovered workflow and confirmed console diagnosis pushed on `codex/bridge-console-fix`, PR #2. This fix 7 milestone is complete.

## Fix 9 implementation

Completed in private isolated worktree `_worktrees/geck-workshop--codex--bridge-dependency`, branch
`codex/bridge-dependency`. Workshop core imports and 16 reusable commands now delegate to the public implementation;
archived copies are ignored. Profiles, mod sources, caches and asset pipeline remain private. Public bridge 0.2.1
ports the missing `--collision-static` feature, so the defeated sprite behavior is preserved.

Checked: public 169 tests passed, 3 skipped; ESP verifier 6 passed; workshop 13 passed. Full old/new non-install asset
builds at seed 0 matched all 48 files. Both current profile dry-run routes matched `c8fa39d0...`; inputs advanced with
the mod agent's current work, so the old Build C hash is not the current baseline. Fresh delegated native GECK status
passed using isolated state. No game installations or live script compilation performed.

Public prerequisite PR #2 merged after all four pull-request CI jobs passed (Ubuntu, macOS, Windows bridge and Windows
port). Private migration PR #1 is open against windows-pc. 2Shay confirmed the mod agent is still running and explicitly
instructed that its checkout remain untouched; no private merge/adoption occurred.

## Fix 9 adopted — 6 October 2026

2Shay confirmed the other agents had finished and explicitly requested the merge. Private PR #1 merged at `1f5d3a7`
after latest PR CI passed, then the primary workshop windows-pc checkout fast-forwarded successfully. All six prior
uncommitted mod files are preserved byte-for-byte and remain uncommitted. Backup is workshop
`_to_delete/bridge-before-fix9-primary`. Post-adoption 13 workshop tests passed; current delegated build dry-run
reproduces `c8fa39d0...`. The canonical public bridge is now used by the active workshop. Fix 9 complete.

## Final live acceptance — complete, 6 October 2026

Native vanilla GECK/MCP workflow passed: HelloWasteland load and forced reload, 14/14 references, cell framing and
render capture (user confirmed the view was perfect); fresh stdio MCP test-plugin load, preview open/close, actual
script compile/save/cache/rebuild via CLI without --skip-load, compiled-plugin reload, guarded MCP save and persisted
validation. Clean GECK restart created a new session and HelloWasteland again loaded/verified/rendered correctly.

One post-restart capture safely failed while Cell View covered Render Window; existing guarded render max/redraw,
then restore, recovered capture. No code change required. No unresolved Hello operations remain. Salvatore plugin
and game plugins.txt hashes are unchanged. The throwaway ESP was moved from Data to ignored test evidence. GECK
remains open, clean, with HelloWasteland loaded; the mod agent can now use it. Full results and limits: docs/TESTING.md.

Next action: complete for the tested native Windows bridge workflow. Nexus/release packaging was not requested.
