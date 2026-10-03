# Testing log

What has been run, where, and what happened. Newest first.

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
