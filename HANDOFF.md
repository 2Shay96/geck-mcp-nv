# GECK MCP bridge handoff

Updated 6 October 2026 by Codex. Owner: 2Shay.

## Scope and location

Make MCP for GECK usable on the Shadow Windows PC, test each fix, and update GitHub after checked milestones. Work in `C:\Users\Shadow\Desktop\VibeCoding\fnv\geck-mcp-release\GECK-MCP-for-New-Vegas`, public repo `2Shay96/geck-mcp-nv`. Read workspace `AGENTS.md`, this file, `MCPworkflow.md`, and `STATUS.md`.

## Recovered context

The detailed history is `..\BRIDGE-FIXES.md`. Its 6 October status supersedes older sections and `..\HANDOFF-NEXT-SESSION.md`. Baseline main commit: `fdaf790`; fixes 1–6, 8 and 10 are recorded as merged. `docs/TESTING.md` records 168 bridge tests run with 3 skips on Windows, plus live editor acceptance. Those are previous results, not new Codex verification.

Fix 7: the game console does not resolve bridge-built plugin forms, although scripts and actor selection work. First compare a GECK-saved copy with the corresponding bridge-built copy, then perform a controlled game test with 2Shay. Verify actual quest IDs and load index rather than copying historical commands. The old notes mention Salvatore v1.1; that is mod scheduling, not a restriction on bridge work.

Fix 9: duplicate workshop/public code. Agree on a migration plan before changing the private workshop.

## Boundaries

The private workshop at `..\..\geck-bridge` has a separate mod agent. Read its inputs/backups as necessary; do not change its sources. Current Salvatore builds have moved beyond the old `382f249d` regression baseline: compare unchanged inputs before/after bridge changes. Use HelloWasteland for live editor acceptance. Game installation changes need a preserved original and restoration plan.

Reference workspace `FNV-SPRITE-FORGE-INTEGRATION-PLAN.md` only when bridge changes affect that integration. Do not work on Sprite Forge or change mod scope. Do not rebuild the Nexus archive unless requested.

## Next action

See `STATUS.md` for current evidence and the next step in fix 7.
