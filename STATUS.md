# GECK MCP bridge status

## 6 October 2026 — Codex takeover

Task: improve GECK MCP usability; investigate fix 7 (game console form resolution). User approved checked bridge milestones to GitHub. Branch: `codex/bridge-console-fix`; baseline `fdaf790`, clean before this work, matching freshly fetched origin/main.

Created `HANDOFF.md` and `MCPworkflow.md` from the recovered notes and current user instructions. No implementation changes yet. Fresh Windows verification: 168 bridge tests passed, 3 skipped; all 6 ESP verifier tests passed. Salvatore profile dry-run validates and reproduces installed Build C exactly: `6e3375186e2f46894e8d5eae45519e0292a62908592316e844d82cbb74349cde`. No workshop or game files were changed.

Initial comparison: backup `5a3f7fbf...` versus bridge build backup `382f249d...` has identical quest EDIDs and record headers, but different main-quest DATA flags, HEDR next-object-ID, and several creature fields. The same differences appear between GECK-saved backup `17222cef...` and current Build C. All four QUST records are present under the correct QUST top group in every inspected copy: main quest `0100080F`, summon `01000818`, far `01000819`, reset `0100081A`. Their record headers use flags 0 and form version 15. This does not establish the cause. Details and runtime test sequence: `docs/CONSOLE-DIAGNOSIS.md`.

GECK is open with a bare title; FalloutNV was not running at inspection. Private workshop sources and installed plugin have not been changed.

Next action: obtain 2Shay's runtime console reference ID and current `sqv` result before preparing a plugin swap. An asynchronous question is pending; do not swap the installed mod while the game is running.
