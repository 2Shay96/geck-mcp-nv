# GECK MCP bridge handoff

## Runtime diagnostics - current state, 18 October 2026

R1/R2 are implemented on codex/runtime-diagnostics and accepted in Windows vanilla:
fresh item counts and a checkpoint delta, truthful rejected-query error reporting,
then owned helper archival after user-confirmed normal FNV exit. Older priorities
below are historical. Runtime CLI/MCP usage and limits are documented in
bridge/docs/MCP-QUICKSTART.md; current evidence is in docs/TESTING.md and STATUS.md.

The shared core prepares allowlisted batches, binds incremental observations to exact
commands/forms, preserves provenance, compares explicit checkpoints and evaluates
versioned rules. Mapping confidence is user-attested or unverified; no installed
extender or historical prefix is proof. User executes batches/gameplay actions;
closing collection does not stop SCOF. New saves/loads require a new baseline.

Offline: 189 bridge tests (3 skipped), 6 ESP checks, 23 Windows-port checks; fresh
stdio MCP/CLI reports agree. Valid quest-variable/reference probes have offline
coverage only. Raw evidence, saves, game assets and private profiles stay local.

Next action: review the scoped runtime PR after four required CI jobs pass. Merge,
version tags and Nexus publication still require 2Shay's explicit approval.


Updated 6 October 2026 by Codex. Owner: 2Shay.

## Scope and location

Make MCP for GECK usable on the Shadow Windows PC, test each fix, and update GitHub after checked milestones. Work in `C:\Users\Shadow\Desktop\VibeCoding\fnv\geck-mcp-release\GECK-MCP-for-New-Vegas`, public repo `2Shay96/geck-mcp-nv`. Read workspace `AGENTS.md`, this file, `MCPworkflow.md`, and `STATUS.md`.

## Recovered context

The detailed history is `..\BRIDGE-FIXES.md`. Its 6 October status supersedes older sections and `..\HANDOFF-NEXT-SESSION.md`. Baseline main commit: `fdaf790`; fixes 1–6, 8 and 10 are recorded as merged. `docs/TESTING.md` records 168 bridge tests run with 3 skips on Windows, plus live editor acceptance. Those are previous results, not new Codex verification.

Fix 7: the game console does not resolve bridge-built plugin forms, although scripts and actor selection work. First compare a GECK-saved copy with the corresponding bridge-built copy, then perform a controlled game test with 2Shay. Verify actual quest IDs and load index rather than copying historical commands. The old notes mention Salvatore v1.1; that is mod scheduling, not a restriction on bridge work.

Fix 9: migration implemented and tested in `_worktrees/geck-workshop--codex--bridge-dependency`. Public prerequisite
PR #2 (bridge 0.2.1 static collision support) and private workshop PR #1 are both merged. On 6 October, 2Shay
confirmed all agents had finished and authorized local adoption. The active workshop windows-pc checkout now uses
the public bridge; its six pre-existing uncommitted mod files remain byte-identical and uncommitted. Fix 9 complete.

## Boundaries

The private workshop at `..\..\geck-bridge` has a separate mod agent. Read its inputs/backups as necessary; do not change its sources. Current Salvatore builds have moved beyond the old `382f249d` regression baseline: compare unchanged inputs before/after bridge changes. Use HelloWasteland for live editor acceptance. Game installation changes need a preserved original and restoration plan.

Reference workspace `FNV-SPRITE-FORGE-INTEGRATION-PLAN.md` only when bridge changes affect that integration. Do not work on Sprite Forge or change mod scope. Do not rebuild the Nexus archive unless requested.

## Next action

See `STATUS.md` for current evidence and the next step in fix 7.
