# MCP for GECK workflow

## Workspace and ownership

Keep sources, notes, and diagnostic artifacts inside `C:\Users\Shadow\Desktop\VibeCoding`. Public bridge repo: `fnv\geck-mcp-release\GECK-MCP-for-New-Vegas`, remote `origin` (`2Shay96/geck-mcp-nv`). Private mod repo: `fnv\geck-bridge` (`2Shay96/geck-workshop`); bridge work does not edit it without coordination.

Read workspace `AGENTS.md`; claim bridge work in `ACTIVE.md`. Preserve other claims and changes. Check git status and fetch origin before starting; pull with `--ff-only` only when safe. Work on a dedicated branch. Do not reset, force-push, rewrite shared history, or delete files. Move unwanted files to `_to_delete`.

## Verification

Run PowerShell directly; Codex does not require Claude's runner. From `bridge`, run `.venv\Scripts\python.exe -m unittest discover -s tests` and relevant ESP checks. Record pass/fail/skips honestly. Live acceptance uses the HelloWasteland profile and the procedures in `docs/TESTING.md`. Do not interrupt unsaved GECK or game work. MCP server code changes require a client restart; CLI processes load fresh code.

For writer changes, compare builds from the same unchanged spec, templates, FormIDs and compiled-script cache. An intentional byte change must be explained and checked for unrelated changes. Coordinate game tests with 2Shay, preserve the installed plugin, and restore it after testing.

## GitHub milestones

On 6 October 2026, 2Shay authorized checked bridge milestones to be committed and pushed. This applies to the bridge task, not unrelated projects or publishing Nexus releases. Commit checked source/docs after meaningful milestones, with explicit file lists; never `git add .` or `git add -A`. Identity: `2Shay <327810178+2Shay96@users.noreply.github.com>`. Review the staged diff, commit, push the task branch, and use a PR for review before merging to main. Record local tests and GitHub checks separately. If additional approval is needed for merging, present the concrete tested PR.

Do not commit secrets, virtual environments, build outputs, diagnostic logs, Bethesda archives, or derived master indexes/templates. Gitignored evidence can stay under `bridge/evidence` or `bridge/state`.

## Handoff

Update `STATUS.md` after meaningful investigation or implementation, including evidence, remaining uncertainty, and one concrete next action. Keep `HANDOFF.md` as the start file; update `CHANGELOG.md` and `docs/TESTING.md` when behavior or verification changes. Remove your `ACTIVE.md` claim when handing back the session; leave an explanatory note if interrupted.
