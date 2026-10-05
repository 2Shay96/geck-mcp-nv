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
| `native` | Windows | **Tested** on Windows 11 with the vanilla Steam GECK: status, build, install, plugin load and reload, cell verify, Render Window capture, preview, script compile, crash recovery ([docs/TESTING.md](../docs/TESTING.md)) |
| `wine` | Linux (Wine/Proton) | **Untested.** The helper must run in the same prefix as GECK |
| `crossover` | macOS + CrossOver | Tested on Mac via CrossOver (not a supported platform) |

Also untested: GECK Extender, and non-English GECK. The unit tests (plus 6 parser tests) pass on Linux and Windows 11;
CI runs them on Ubuntu, macOS and Windows.

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
3. **Build the helper if it is missing.** The Nexus download ships source only (no `.exe`, to avoid antivirus false
   positives); the GitHub repo includes a prebuilt `Probe.Mcp.exe`. On Windows this uses the C# compiler that comes with
   the .NET Framework 4 (already part of Windows):
   ```sh
   .venv\Scripts\python build_helper.py --project projects\hellowasteland.json
   ```
4. **Register the MCP server** in your client:
   ```json
   "geck": {
     "command": "/path/to/bridge/.venv/bin/python",
     "args": ["/path/to/bridge/run_mcp.py", "--project", "/path/to/bridge/projects/hellowasteland.json"]
   }
   ```
5. Ask your agent: *"Validate the spec, build the plugin and show me what it contains."*
   This uses `geck_spec_validate`, then `geck_plugin_build`, then `geck_plugin_inspect`, and touches nothing in the game.

## The 25 tools

| Group | Tools |
| --- | --- |
| Offline authoring | `geck_spec_validate`, `geck_plugin_build`, `geck_plugin_inspect`, `geck_master_lookup`, `geck_plugin_install` |
| Editor state | `geck_status`, `geck_inspect_windows`, `geck_show_windows`, `geck_capabilities`, `geck_project_attach` |
| Load & verify | `geck_plugin_load`, `geck_plugin_load_status`, `geck_cell_verify` |
| Records | `geck_records_find`, `geck_record_read`, `geck_record_set_model`, `geck_preview_open`, `geck_preview_close` |
| Save & check | `geck_plugin_save`, `geck_plugin_validate` |
| Recovery | `geck_operation_get`, `geck_recovery_acknowledge` |
| Pictures | `geck_render_capture` (Windows and macOS), `geck_image_cutout`, `geck_actor_photo` (macOS only for now) |

Tools that act on the running GECK take an optional `editor_session`; leave it out to use the GECK that is running
(see [docs/MCP-QUICKSTART.md](docs/MCP-QUICKSTART.md)). After changing bridge code, restart your MCP client.

The same jobs are available from the command line: `build_plugin.py` (`--project` uses the profile's state and build
folders), `install_plugin.py`, `live_load.py` (`--if-needed`), `cell_verify.py`, `compile_scripts.py` (build, then load in
GECK, compile every script, save and cache the compiled bytecode), `recover.py` (list or clear recovery barriers),
`photo_cli.py`, and `sprite_flipbook.py` (an animated sprite billboard NIF from PNG frames; needs PyFFI).

## Safety built in

- Every edit uses a request key. Repeats are refused or replayed, never run twice.
- Operations are journaled in SQLite. An interrupted operation blocks further edits until you review and acknowledge it,
  or until GECK has been restarted (then it is released automatically as `stale`).
- Install and save make content-addressed backups and check hashes before and after.
- The bridge refuses to load anything if GECK has unsaved changes, and never discards your work.

## Known limits (v0.1)

- `geck_plugin_load` loads your plugin with **FalloutNV.esm only**. No DLC or other masters yet.
- Editor record tools target configured STAT records. Richer records (creatures, quests, scripts, weapons ...)
  are made through the spec builder, not by editing inside GECK.
- Control IDs and menu captions are from the English vanilla GECK.
- `Probe.cs` still contains early experimental operations (`cell.load`, `window.layout.place`, `object.place`) that
  only accept the author's test objects and use real mouse input. The MCP server does not use them.
- Actor photos use macOS `screencapture`. `geck_render_capture` also works on Windows: PrintWindow at the size GECK
  renders (works when other windows cover it). PrintWindow sometimes returns only the grey window background, so a
  blank result is retried with a repaint request (about 12 s), then a DPI-aware screen copy is tried if nothing
  covers the Render Window. Look at the PNG: the tool only checks that it is not one flat colour.

Docs: [docs/MCP-QUICKSTART.md](docs/MCP-QUICKSTART.md) · [docs/PHOTO.md](docs/PHOTO.md) · [docs/M1-FAST-BRIDGE.md](docs/M1-FAST-BRIDGE.md)
