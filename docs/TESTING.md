# Testing log

What has been run, where, and what happened. Newest first.

## 2026-10-06: final live native MCP acceptance, bridge 0.2.1

Shadow Windows PC, vanilla Steam GECK, native launcher, public main `3d9dcf4` at test start. No bridge code changed
in this session. Used the registered Codex `geck-hello` tools for HelloWasteland and a fresh stdio MCP client for an
isolated throwaway `HelloAcceptanceFinal.esp` (one STAT and one object script from the existing HelloPreview fixture).

| Check | Result | Evidence |
| --- | --- | --- |
| Status, validate, build, install, attach through MCP | pass | Clean GECK; HelloWasteland build/installed SHA `23650eea...`; all three editor panes visible/reachable |
| Initial HelloWasteland load | pass | `loaded_verified`, 14/14 references; explicit `editor_session` accepted |
| Forced HelloWasteland reload | pass | `reload=true` completed as `loaded_verified`; 14/14 references still match |
| Cell framing and render captures | pass | Frames `light.red` and `barrel.left`; nonblank 455x169 PrintWindow PNGs. 2Shay confirmed the view was perfect, correcting an accidental negative answer |
| Fresh stdio MCP discovery / test-plugin load | pass | 25 tools; isolated plugin built/installed, loaded and attached with its configured STAT identity |
| Script compiler CLI, without `--skip-load` | pass | Automatically recognised `already_loaded`; HelloPreviewScript actually compiled with no errors, saved, cached, rebuilt and installed; no uncompiled scripts remain; exit 0 |
| Compiled test-plugin reload / attach | pass | Forced MCP reload returned `loaded_verified` |
| Preview open / close through MCP | pass | HelloPreviewTile preview opened and closed; lifecycle/identity checked, preview image not separately visually assessed |
| Guarded whole-plugin MCP save / persisted validation | pass | `save_entire_active_plugin=true` with expected hash/model; `saved_verified`, then persisted STAT/model validation passed |
| Clean GECK restart / new session | pass | PID changed 19108 → 21476; HelloWasteland loaded and verified again with 14/14 refs |
| Post-restart render capture | pass after uncovering | Initial `CAPTURE_BLANK` safely refused because Cell View covered Render Window. Existing guarded helper `render.steps` max/redraw brought it forward: nonblank 1280x777 PrintWindow. After restoring normal layout, nonblank 910x338 screen capture at 200% DPI |
| Cleanup / preserved mod | pass | No unresolved Hello operations; GECK left clean on HelloWasteland. SalvatoreGanacci.esp and game plugins.txt SHA-256 unchanged. New throwaway ESP moved out of Data into ignored evidence, not deleted |

Raw evidence: `bridge/state/acceptance/final-20261006-codex/` (ignored): `final-direct-mcp.json`,
`preview-mcp.jsonl`, `render-layout.json`, `cleanup.json`, `protected-files.json`, test profile/spec/script and saved
test ESP. Captures are under ignored `bridge/photos/render-20261006-*.png`.

Not repeated: deliberate crash mid-load (prior acceptance already covered it), GECK Extender, Wine/Proton or macOS.
The compiler is a supported CLI, not an MCP compilation tool. The fresh stdio test covers preview/save; those steps
were not performed using the HelloWasteland connector because its profile deliberately has no configured STAT records.

## 2026-10-06: Codex bridge takeover and console diagnosis

Fix 9 follow-up: public suite **169 tests passed, 3 skipped**, ESP verifier **6 passed**; isolated workshop migration
suite **13 passed**. Static Havok collision is checked by NIF readback and deterministic CLI output. Full non-install
old/new Salvatore asset builds matched **48/48 files byte-for-byte** at seed 0. Both public/delegated current profile
dry-runs matched `c8fa39d051cfc109405a71ed30206a292ca439f6b0509cda2cfe4d27c26174f0`. A fresh delegated
native GECK status succeeded with isolated state. No writer changes, game writes or new live compilation/load cycle.

Shadow Windows PC; branch `codex/bridge-console-fix`, baseline `fdaf790`.

| Check | Result | Notes |
| --- | --- | --- |
| Bridge unit suite | pass | 168 tests run, 3 skipped |
| ESP verifier suite | pass | 6 tests run |
| Salvatore profile dry-run | pass | Validates and matches installed Build C SHA-256 `6e3375186e2f46894e8d5eae45519e0292a62908592316e844d82cbb74349cde`; no files installed |
| GECK status through Codex MCP | pass | Direct `geck_status`: no unsaved changes, Object Window/Cell View/Render Window visible and reachable |
| Installed plugin inspection through MCP | pass | `geck_plugin_inspect(which="installed")`: generated, installed hash matches build |
| Runtime actor ID | user verified | 2Shay clicked Salvatore: `0A000813`; plugin contains ACRE `01000813` |
| Main quest console lookup | user verified pass | `sqv 0A00080F` shows quest variables using the unchanged bridge-built plugin. Earlier commands used wrong runtime prefix 01 |
| Corrected summon command | user verified pass | `startquest 0A000818` summons Salvatore without “Invalid info” on the unchanged bridge-built plugin |

No GECK edits, plugin swaps, writer changes or new full live acceptance run in this session.

## 2026-10-05: 0.2.0 fixes, Windows 11, native launcher

Same Shadow cloud PC as 3 Oct (display scaled 200%). Branch `bridge-fixes`. Runner jobs `.claude-runner\done\046`-`063`.
Live tests used only throwaway plugins: `HelloWasteland.esp` (profile `projects/hellowasteland.json`) and a local
acceptance plugin `HelloPreview.esp` (one STAT for the preview tools, one 5-line object script for
`compile_scripts.py`; files in `bridge/state/acceptance/`, not shipped). Driver: `bridge/state/acceptance/acceptance.py`.

| Check | Result | Notes |
| --- | --- | --- |
| Fix 3 cause | confirmed | Direct stdio client (job 047): `session_id` reaches the server. Through the Claude desktop device proxy the server received `{}` |
| `bridge` unit tests, Windows | pass | Job 054: 161 run, 9 skipped (6 sprite tests without PyFFI, 2 Wine launcher tests, 1 symlink without privilege). Job 063 with PyFFI installed: 168 run, 3 skipped. Linux without PyFFI: 168 pass, 9 skipped |
| Salvatore regression | pass | Spec at workshop HEAD: sha256 `382f249d…` (byte-identical). Current workshop spec (author field edited, uncommitted): `a5d045c3…` with the old and the new code |
| `build_plugin.py <spec> --dry-run --state <workshop state>` | pass | Job 038 failed here with `no template dump` |
| Helper rebuild (`build_helper.py`) | pass | Old exe kept in `bridge/state/helper-old/` |
| Acceptance round 1 (job 052) | pass, except capture | status → load (`loaded_verified`, 44 s) → cell verify 14/14 with frame → reload (68 s) → cell verify 14/14 → `compile_scripts.py` without `--skip-load` (load, compile, save, cache, rebuild, install; exit 0) → preview open/close → kill GECK mid-load, restart |
| Acceptance round 2 (job 053, after the GECK restart) | pass, except one capture | The first load released the killed load's barrier (`releasedStaleOperations`), then the same steps passed again |
| MCP through the Claude desktop device proxy (server `geck-hello`, HelloWasteland profile) | pass | `geck_status` (3 windows visible, Render Window reachable); `geck_plugin_load` without a session (released the barrier left by the kill test) → `loaded_verified`; reload → `loaded_verified` only after the reload was seen; `geck_cell_verify` with `editor_session` and with none, framing `light.red` / `barrel.left`; `geck_plugin_install`, `geck_plugin_save`, `geck_recovery_acknowledge` with `editor_session` reached the server (install unchanged; save and acknowledge refused by their own guards, as expected for this profile). Proxy check: `editor_session: "999:1"` → `STALE_SESSION` (argument arrives); `session_id: "999:1"` → accepted as if absent (the proxy drops it) |
| Render capture | pass | Jobs 054-056 and MCP: PNGs of the framed cell (floor tiles, barrel, light markers), 455x169 (PrintWindow, = the client size GECK reports) or 910x338 (screen copy at 200% scaling); 4 of 4 non-blank in job 056. Found on the way: a DPI-unaware screen copy took the wrong area (job 052); a covered Render Window gave a picture of the covering window (overlap check added); PrintWindow alternates between the rendered view and the plain grey background (retry with a repaint request added) |
| Sprite tools (job 063, no GECK) | pass | PyFFI 2.2.3 + setuptools 84.0.0 from the lock file; 168 unit tests, 3 skipped (the 6 sprite tests now run). Vanilla `clutter\ashtray\ashtray01.nif` (material 24) as collision template: no option keeps 24, `organic` → 6, `cloth` → 1, read back from the written NIF. Same frames with hash seed 1, 2 or unset → one mesh sha; the workshop script without the re-run gave a different mesh for seeds 1 and 2, and with seed 0 the same bytes as the public one. `creature_skeleton.py --project` (mistergutsy, 40 files, 8 KFs edited): identical bytes for seeds 1 and 2 and to the workshop script. Salvatore esp regression unchanged (`382f249d…` / `a5d045c3…`) |
| Loads without the mouse (jobs 058-061) | pass | Experiment with GECK's Data dialog (then Cancel): posted double-clicks toggle a row with the cursor elsewhere; a sent `WM_NOTIFY NM_DBLCLK` timed out. Helper changed to post-only toggles (verified, up to 3 tries). Job 061: 3 loads (HelloWasteland → HelloPreview → HelloWasteland) all `loaded_verified`, every toggle on the first try, while 2Shay used the mouse (214 distinct cursor positions in 641 samples) |

Not run: Linux/Proton; macOS + CrossOver with this version; `windows/` server; GECK Extender. The new windows-latest
CI job has not run yet (it runs on the first push).

### Found and fixed during these runs
- GECK started by a script had Object Window, Cell View and Render Window all hidden before any load (job 051). A
  posted `WM_NULL` did not bring them back; `ShowWindow` did. Started by hand, they were visible. This matches jobs
  031/041 (hidden after a load).
- A Data list checkbox did not toggle while nobody was at the PC (job 049); the load then left the Data dialog open and a
  barrier. Now the dialog is cancelled and the load fails cleanly (`failed_before_change`).
- Reloading the already-shown plugin was reported `loaded_verified` before GECK started reloading (job 051).

## 2026-10-03: Windows 11, native launcher (first real Windows run)

Machine: Shadow cloud PC, Windows 11 Home 10.0.22621, NVIDIA RTX 2000 Ada. Fallout: New Vegas + vanilla GECK from Steam
(default folder). Python 3.12.10. Profile `bridge/projects/hellowasteland.json` copied from `example-windows.json`
(`"launcher": "native"`). Repo at `ba37349` plus the two helper fixes below.

| Step | Result | Notes |
| --- | --- | --- |
| GECK renders (FalloutNV.esm, exterior cell) | pass | Loads in under a minute; camera responsive |
| `bridge` unit tests | 106 of 133 pass, 6 skipped | 20 failures + 7 errors are test-fixture issues, not tool bugs: fixtures use CrossOver bottle paths (`WRONG_EDITOR`, launcher command asserts with `/`), SQLite files still open at temp cleanup (`WinError 32`), symlinks need a privilege (`WinError 1314`). Known: CI skips windows-latest |
| `test_esp_check.py` | pass (6) | |
| `windows` unit tests | pass (23) | |
| `esm_index.py FalloutNV.esm` | pass | 465,017 records, 70,872 indexed |
| `Probe.Mcp.exe status` | pass | No SmartScreen/Defender prompt (git clone has no download mark) |
| status one-liner | pass | `ok: true`, persistent worker |
| `build_plugin.py examples/hello-wasteland.spec.json` | pass | 18 records, 14 references, validation OK |
| MCP over stdio (`run_mcp.py`) | pass | 24 tools; `geck_status` ok |
| `install_plugin.py` | pass | New `Data\HelloWasteland.esp`, sha256 `23650eea…45a7` |
| `live_load.py --timeout 1500` | **fail, fixed, pass** | See fixes 1 and 2. After the fixes: `loaded_verified` in 66 s |
| `cell_verify.py --cell HelloWasteland --frame light.red` | pass | 14/14 references matched; camera framed. Render Window shows the tiled room, fire and lights |

### Fixes found by this run (in `bridge/Probe.cs`, helper rebuilt with the .NET Framework `csc.exe`)
1. **Data dialog stayed hidden.** On Windows the modal Data dialog opened by the posted menu command was created but
   not shown until GECK received real input, so the load failed with `MODAL_BLOCKED` ("no dialog appeared").
   The helper now shows exactly one hidden `Data` dialog owned by the editor after 500 ms.
2. **Data checkboxes did not toggle.** GECK hit-tests the cursor position of the double-click, so the sent synthetic
   double-click did nothing on Windows, and a sent button-down can block in the list's drag detection until the real
   mouse moves (GECK showed "not responding"; a mouse move freed it, no data changed). On native Windows the helper now
   parks the cursor over the row (no real click), posts the four mouse messages and restores the cursor.
   Under Wine (detected via `ntdll!wine_get_version`) the original sent double-click is unchanged.

Each failed attempt was left as an unresolved operation; after checking that the Data dialog was cancelled and the
editor was clean, the barrier was cleared with `acknowledge` and a note.

### Not run yet
- `windows/` server against the real GECK (`geck_doctor`, `geck_list_windows`, `geck_cell_view_snapshot`)
- A second pass with GECK Extender
- `geck_status` through the Claude desktop and Codex registrations after an app restart
- macOS + CrossOver re-check with the rebuilt helper (the Wine code path is unchanged)

## 2026-10-02/03: macOS + CrossOver
Status, build, install, live load and cell verify (14/14) passed on the author's Mac; see `RELEASE-STATUS.md`
outside the repo for details.
