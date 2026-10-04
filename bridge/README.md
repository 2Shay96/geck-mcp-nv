# GECK bridge (`geck`): spec-to-plugin builder + GECK control

The bridge is the original part of GECK MCP for New Vegas. It has two layers:

1. **Offline plugin authoring (any OS, no GECK needed).** You describe a mod in a JSON *spec*: records,
   interior cells and placed objects. The bridge writes a valid `.esp` with stable FormIDs, checks every
   `@EditorID` reference against your own masters, and installs it with backups.
2. **GECK control.** A small 32-bit helper (`Probe.Mcp.exe`) runs next to GECK and drives it mostly through
   Windows messages; only the photo camera uses real input. The bridge uses it to load plugins, verify cells
   against the build, set models, save, **compile scripts with GECK's own compiler**, and take actor photos.

## Tested where?

| Launcher (`"launcher"` in the profile) | Platform | Status |
| --- | --- | --- |
| `native` | Windows | **Tested** on Windows 11 with the vanilla Steam GECK: status, build, install, plugin load, cell verify ([docs/TESTING.md](../docs/TESTING.md)) |
| `wine` | Linux (Wine/Proton) | **Untested.** The helper must run in the same prefix as GECK |
| `crossover` | macOS + CrossOver | Tested on Mac via CrossOver (not a supported platform) |

Also untested: GECK Extender, and non-English GECK. The 133 unit tests (plus 6 parser tests) pass on Linux; on Windows
27 of them fail because their fixtures assume POSIX/CrossOver paths (see TESTING.md).

## Setup

Requirements: Python 3.12+, Fallout: New Vegas with GECK, and an MCP client (Claude Desktop/Code, Codex, ...).

```sh
cd bridge
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt      # Windows: .venv\Scripts\python.exe
```

1. **Build the master index** (read-only, run once per game update). Set `FNV_DATA` if your Data folder is elsewhere.
   ```sh
   .venv/bin/python esm_index.py FalloutNV.esm
   ```
2. **Make a profile.** Copy `projects/example-<your OS>.json` to `projects/hellowasteland.json` and fix the paths.
3. **Register the MCP server** in your client:
   ```json
   "geck": {
     "command": "/path/to/bridge/.venv/bin/python",
     "args": ["/path/to/bridge/run_mcp.py", "--project", "/path/to/bridge/projects/hellowasteland.json"]
   }
   ```
4. Ask your agent: *"Validate the spec, build the plugin and show me what it contains."*
   This uses `geck_spec_validate`, then `geck_plugin_build`, then `geck_plugin_inspect`, and touches nothing in the game.

## The 24 tools

| Group | Tools |
| --- | --- |
| Offline authoring | `geck_spec_validate`, `geck_plugin_build`, `geck_plugin_inspect`, `geck_master_lookup`, `geck_plugin_install` |
| Editor state | `geck_status`, `geck_inspect_windows`, `geck_capabilities`, `geck_project_attach` |
| Load & verify | `geck_plugin_load`, `geck_plugin_load_status`, `geck_cell_verify` |
| Records | `geck_records_find`, `geck_record_read`, `geck_record_set_model`, `geck_preview_open`, `geck_preview_close` |
| Save & check | `geck_plugin_save`, `geck_plugin_validate` |
| Recovery | `geck_operation_get`, `geck_recovery_acknowledge` |
| Pictures (macOS only for now) | `geck_actor_photo`, `geck_render_capture`, `geck_image_cutout` |

The same jobs are available from the command line: `build_plugin.py`, `install_plugin.py`, `live_load.py`, `cell_verify.py`,
`compile_scripts.py` (build, then load in GECK, compile every script, save and cache the compiled bytecode),
`photo_cli.py`, and `sprite_flipbook.py` (an animated sprite billboard NIF from PNG frames; needs PyFFI).

## Safety built in

- Every edit uses a request key. Repeats are refused or replayed, never run twice.
- Operations are journaled in SQLite. An interrupted operation blocks further edits until you review and acknowledge it.
- Install and save make content-addressed backups and check hashes before and after.
- The bridge refuses to load anything if GECK has unsaved changes, and never discards your work.

## Known limits (v0.1)

- `geck_plugin_load` loads your plugin with **FalloutNV.esm only**. No DLC or other masters yet.
- Editor record tools target configured STAT records. Richer records (creatures, quests, scripts, weapons ...)
  are made through the spec builder, not by editing inside GECK.
- Control IDs and menu captions are from the English vanilla GECK.
- `Probe.cs` still contains early experimental operations (`cell.load`, `window.layout.place`, `object.place`) that
  only accept the author's test objects and use real mouse input. The MCP server does not use them.
- Photos use macOS `screencapture`. A Win32 capture is planned.

Docs: [docs/MCP-QUICKSTART.md](docs/MCP-QUICKSTART.md) · [docs/PHOTO.md](docs/PHOTO.md) · [docs/M1-FAST-BRIDGE.md](docs/M1-FAST-BRIDGE.md)
