---
name: geck-mcp-nv
description: Inspect and automate Fallout: New Vegas GECK through the local geck MCP server, including GECK/NVSE startup, Cell View and Object Window navigation, placement, plugin backups, logs, and bounded ESP editing. This is UI/file automation, not native access to GECK internals.
---

# GECK MCP

## Setup and discovery

Requires the separately configured local `geck_nv` MCP server from the `windows/` folder of
GECK MCP for New Vegas: an UNTESTED Fallout: New Vegas port of
https://github.com/maksimka2432fr23/codex-skill-mcp-fallout3 (MIT).
It has not yet been run against a real New Vegas GECK; verify every step with `geck_doctor`,
`geck_control_tree` and screenshots before trusting it.
Installing this skill alone does not install or connect the server.

Use the configured game directory (`GECK_MCP_FNV_DIR`) and server paths;
never assume the author's Steam library or Windows account. Use
`geck_launch(via_nvse=true)` for NVSE editor launch.

Use `geck_doctor` first. Discover available `geck_*` tools; do not infer failure from deferred tool visibility. Server source changes require an MCP reconnect/restart before the running session gains new behavior and schemas. Do not assume editing Python hot-reloads an existing server.

## Essential boundaries

- The user’s request to produce a saved mod authorizes the necessary saves and backups. A request to inspect GECK does not authorize plugin edits. Do not discard unsaved work or change load order unless within the user's request.
- Before changing an existing plugin, use `geck_transaction_begin` or `geck_backup_plugin`. A disk backup does not include unsaved GECK changes. For a new unnamed mod, use and inspect Save As; the save helper requires an existing named plugin.
- Use explicit plugin names in all file operations; never rely on the historical test-plugin default. Keep plugin work in the configured Data directory.
- Use NVSE editor mode when recompiling scripts containing NVSE functions.
- Prefer high-level tools and control selectors. Inspect unfamiliar dialogs with `geck_control_tree`; try both win32 and uia backends before screenshot-based coordinate clicks.
- Generic placed-record editing supports REFR/ACHR/ACRE only. Never use it to edit NAVM, scripts, quests, or arbitrary records. Compressed placed records and XXXX extended subrecords are deliberately rejected; do not bypass that rejection.

## UI placement and saved-state verification

1. Inspect `geck_list_plugins`, `geck_read_load_order`, and `geck_active_plugin`. Confirm the intended active plugin and create a disk rollback point.
2. Find the cell with `geck_cell_select` or `geck_cell_go_to_exterior`; inspect `geck_cell_view_snapshot`. Search/select objects with `geck_object_filter`, `geck_object_select`, and `geck_cell_find_refs`.
3. Place with `geck_place_object_in_render`. Check the new reference in Cell View and visually in Render Window. Disk readers cannot see this placement until it is saved.
4. If a saved mod is requested, call `geck_save_active_plugin`. A result with `saved=false` is unverified, not permission to repeatedly save: inspect dialogs and `EditorWarnings.txt`. The helper checks a changed, stable file and editor state; it does not prove gameplay correctness.
5. Read saved records with `geck_esp_list_refs`. Record the exact target FormID, `cell_form_id`, and `world_form_id`. These are on-disk IDs; do not assume a UI load-order prefix is interchangeable.
6. Use `geck_esp_nearby_refs(cell_form_id=...)` for scoped coordinates. `geck_placement_report` requires the anchor's cell_form_id and a live selected anchor. Restrict conclusions to the intended refs in that cell; other distant refs in a large cell are not necessarily errors.

## Precise correction without conflicting with GECK

1. While GECK is open, select a known-good anchor and use `geck_status_bar` and `geck_placement_plan_from_status_bar` to capture numeric coordinates plus offsets. Record the cell and target ref.
2. Preserve existing target rotation unless a change is requested. Direct ESP rotations are radians. UI status-bar angle units are not verified: keep `use_status_rotation=false`. A plan's fallback zero rotation is not a reason to reset the target.
3. Save authorized pending UI changes and close GECK without discarding work. Direct edits and rollback are blocked while GECK/NVSE or a game-directory process is running. Never try to evade the guard.
4. Create a rollback point and call `geck_esp_patch_ref_position` with the captured x/y/z. Omit rot_x/rot_y/rot_z to preserve them; supply only axes deliberately changed.
5. Verify the disk result and scoped nearby refs, then reopen the plugin for visual checks. Bounds, object origin, collision and floor contact still require GECK/game validation.

The legacy `geck_esp_patch_ref_to_status_bar` and offset variant now return `applied=false` with deferred patch arguments. They never write a plugin from live status-bar state. Apply those arguments only after saving authorized UI changes and closing GECK; verify any proposed rotation first.

## Delete and recover

- Identify exact saved FormIDs before deletion. `geck_esp_delete_refs_by_base` can match many objects; inspect those matches first. Deleting an override from this file is not equivalent to deleting the underlying master object from the game.
- With GECK closed, begin a transaction, edit/delete, and inspect `geck_transaction_verify`. Verification describes disk state; it is not a full dependency/link validator.
- On an incorrect result, use the recorded transaction ID with `geck_transaction_rollback`, also with GECK closed. Then reopen and verify visually.
- Mutations validate container boundaries, use a verified temporary file and atomic replacement, and compare the original before replacement. This does not coordinate with every possible external editor; avoid concurrent editing.

## Diagnosis and reporting

For “проверь GECK”, run doctor and inspect processes/windows without launching or editing unnecessarily. For warnings, use `geck_tail_log(log_name="EditorWarnings.txt")`. For navigation, use cell/object tools before raw clicks.

Report the changed plugin and refs, verification performed, and any actual limitations. Retain useful window handles in working context; do not overwhelm the user with an inventory of handles or tools.
