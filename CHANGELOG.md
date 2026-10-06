# Changelog

## 0.2.1: shared bridge and final live acceptance (2026-10-06)

- Final native Windows 11 / vanilla GECK acceptance completed on 6 October: direct MCP load/reload/cell/render,
  stdio MCP preview and guarded save, actual script compilation through the CLI, and successful load/render after
  a clean GECK restart. Salvatore and game plugin activation list were unchanged. See docs/TESTING.md for evidence
  and the covered-window capture retry.

- Bridge 0.2.1: port the workshop sprite tool's `--collision-static` option and collision motion readback so
  the workshop can depend on this implementation without losing its unmovable defeated sprite. Fixed collision
  uses static layer, motion system 7, fixed quality, zero mass/inertia and clears the dynamic BSX flag.
  Existing dynamic collision behavior and deterministic hash-seed handling are preserved.

- Document file-local versus runtime FormIDs for game console commands. The Salvatore main-quest lookup failure
  was resolved on the unchanged bridge-built plugin by using runtime index `0A` instead of file-local `01`;
  `sqv 0A00080F` and `startquest 0A000818` were verified in game by 2Shay. No plugin writer change was required.

## 0.2.0: Windows fixes from the Salvatore build (2026-10-05)
### bridge/
- **MCP tools work through the Claude desktop device proxy (Cowork).** The proxy drops tool arguments named
  `session_id` (confirmed: a direct stdio client delivers it, the proxy forwarded `{}`), so every tool that required
  it failed with `session_id Field required`. The argument is now `editor_session` and optional on every tool; when it
  is left out the running GECK session is used, and the expected title / plugin hash / model guards still apply.
  `session_id` stays accepted as an alias.
- **Hidden GECK windows.** On native Windows GECK can leave Object Window, Cell View and Render Window hidden (after a
  load, or when GECK starts without user input), which failed load verification with `Cell View selector matched 0
  windows`. The helper has a new `windows.show` operation (ShowWindow without activation, no clicks; refused while GECK
  is busy or modal). `geck_plugin_load_status` and `geck_cell_verify` use it, and the new **`geck_show_windows`** tool
  exposes it. `geck_status` reports `windowsVisible` and `renderWindowReachable`.
- **`loaded_unverified`.** When the plugin is clearly loaded (title, responsive editor) but the check itself cannot run,
  the load ends `loaded_unverified` instead of failing and leaving a barrier.
- **Stale recovery barriers are released.** An uncertain operation from an earlier GECK session (GECK closed, crashed or
  killed, then restarted) no longer blocks editor work: the next editor call marks it `stale` and reports it under
  `releasedStaleOperations`. New CLI `recover.py --list / --release-stale / --ack ID --note ... [--offline]`.
- **Loads no longer use the mouse.** 0.1.1 parked the real cursor over each Data list row for up to 2 s, so a load
  failed when the user moved the mouse or was away. Posted double-clicks toggle the rows without the cursor (tested
  with the cursor elsewhere and while the mouse was in use); each toggle is read back and retried up to 3 times.
- **Failed loads clean up.** If the Data dialog step fails before OK (e.g. a checkbox that does not toggle), the dialog
  is cancelled and the load is `failed_before_change` (no barrier). `data.state` and `data.cancel` no longer need a
  dummy argument in the helper.
- **Reload completion.** Reloading the plugin GECK already shows was reported done before GECK even started reloading
  (the title names the plugin before and after). A reload is now done only after the reload was seen, or after 45 s.
- **Templates and indexes follow the profile.** Record templates and master indexes are read from the profile's
  `state_dir` first, then from `bridge/state` (job 038 failed with `no template dump` although the profile had it).
  `build_plugin.py` gains `--project`; its default output is `<state>/../build`, the folder the MCP tools use.
  `cell_verify.py` reads the receipt from that folder too.
- **`compile_scripts.py`** loads with `live_load.py --if-needed`: no reload when this GECK session already loaded the same
  plugin bytes; a load whose plugin is active but whose cell check failed still counts.
- **`geck_render_capture` on Windows** (was macOS only): PrintWindow in GECK's own DPI context (the image is the size GECK
  renders and reports), retried with a repaint request when it returns only the grey background; then a DPI-aware
  screen copy if no other window covers the Render Window. A flat (blank/black) result fails with `CAPTURE_BLANK`.
- `ALCH` (aid items) added to the generic record types.
- **Sprite tools.** `sprite_flipbook.py --collision-material organic` (a name or a number) replaces the Havok material
  of the borrowed vanilla collision, which sets the sound when the sprite is knocked about (ported from the Salvatore
  workshop). `sprite_flipbook.py` and `tools/creature_skeleton.py` re-run themselves with `PYTHONHASHSEED=0`, so the
  same input gives the same NIF/KF bytes (PyFFI writes string tables in set order; two hash seeds gave two different
  meshes). `creature_skeleton.py` finds the game Data folder from `--data`, `--project`, `$FNV_DATA` or the usual Steam
  folder (was a hard-coded macOS path). PyFFI 2.2.3 and setuptools 84.0.0 (PyFFI imports distutils, removed in
  Python 3.12) are in `requirements.lock.txt`, so the sprite tests run in CI.
- Unit tests pass on Windows (fixtures no longer assume POSIX/CrossOver paths; Wine launcher tests skip on Windows);
  CI runs them on windows-latest too.

## 0.1.1: first Windows-tested release (2026-10-03)
### bridge/
- Fixed on native Windows: plugin load failed with `MODAL_BLOCKED` because GECK's Data dialog stayed hidden; the helper
  now shows it.
- Fixed on native Windows: Data list checkboxes did not toggle (and a sent click could stall GECK until the mouse moved);
  the helper now posts the double-click with the cursor parked over the row. Wine/CrossOver behaviour is unchanged.
- First Windows 11 end-to-end run (status, build, install, live load, cell verify): see `docs/TESTING.md`.
- The Nexus download is source only (no `.exe`): build `Probe.Mcp.exe` with `build_helper.py`. GitHub keeps the prebuilt helper.

## 0.1.0: WIP prototype (2026-10-02)
First public release, as a work-in-progress prototype.

### bridge/
- Offline spec-to-plugin builder: codec, stable FormIDs, `@EditorID` references to indexed masters,
  template-cloned records, validation, install with backups.
- GECK control through `Probe.Mcp.exe`: status, plugin load, cell verification, record model edits, save,
  script compilation with GECK's compiler, and actor photos (macOS).
- New for the release:
  - `launcher` profile setting (`crossover` / `wine` / `native`) for Linux and Windows
  - a cross-platform lock
  - example profiles and the vanilla `hello-wasteland` spec
  - author paths removed
- Tested end to end only on macOS + CrossOver with vanilla GECK.

### windows/
- Fallout: New Vegas port of GECK MCP for Fallout 3 (maksimka2432fr23, MIT): FNV paths, NVSE loader,
  FalloutNV plugins.txt, works with MCP SDK 1.x and 2.x. Unit tests pass. Not yet run against the FNV GECK.

### Known gaps
- No Windows or Linux end-to-end run yet. GECK Extender is untested.
- The bridge loads FalloutNV.esm only (no DLC masters).
- Photos are macOS-only.
