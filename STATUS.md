# GECK MCP bridge status

## 6 October 2026 — Codex takeover

Task: improve GECK MCP usability; investigate fix 7 (game console form resolution). User approved checked bridge milestones to GitHub. Branch: `codex/bridge-console-fix`; baseline `fdaf790`, clean before this work, matching freshly fetched origin/main.

Created `HANDOFF.md` and `MCPworkflow.md` from the recovered notes and current user instructions. No implementation changes yet. Fresh Windows verification: 168 bridge tests passed, 3 skipped; all 6 ESP verifier tests passed. Salvatore profile dry-run validates and reproduces installed Build C exactly: `6e3375186e2f46894e8d5eae45519e0292a62908592316e844d82cbb74349cde`. No workshop or game files were changed.

Initial comparison: backup `5a3f7fbf...` versus bridge build backup `382f249d...` has identical quest EDIDs and record headers, but different main-quest DATA flags, HEDR next-object-ID, and several creature fields. The same differences appear between GECK-saved backup `17222cef...` and current Build C. All four QUST records are present under the correct QUST top group in every inspected copy: main quest `0100080F`, summon `01000818`, far `01000819`, reset `0100081A`. Their record headers use flags 0 and form version 15. This does not establish the cause. Details and runtime test sequence: `docs/CONSOLE-DIAGNOSIS.md`.

Direct MCP verification: `geck_status` succeeded against the running GECK (PID 19108), with no unsaved changes and Object Window, Cell View and Render Window all visible/reachable. `geck_plugin_inspect(which="installed")` succeeded and confirmed the installed Build C hash and match to build. Private workshop sources and installed plugin have not been changed.

Runtime result: 2Shay reported clicked reference `0A000813`, confirmed `sqv 0A00080F` shows quest variables, and confirmed `startquest 0A000818` summons Salvatore without the original error. The unchanged bridge-built plugin works: the historical prefix 01 was incorrect for this running load order. Fix 7's two numeric-ID failures are resolved without writer changes. Updated `bridge/README.md` with file-local versus runtime FormID guidance. Vanilla EditorID lookup and far/reset commands were not retested.

GitHub milestone: recovered workflow and confirmed console diagnosis pushed on `codex/bridge-console-fix`, PR #2. This fix 7 milestone is complete.

Next action: plan fix 9 (workshop/public code duplication) around the current private workshop workflow before changing its imports or scripts.
