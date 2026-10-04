# Changelog

## 0.1.1: first Windows-tested release (2026-10-03)
### bridge/
- Fixed on native Windows: plugin load failed with `MODAL_BLOCKED` because GECK's Data dialog stayed hidden; the helper
  now shows it.
- Fixed on native Windows: Data list checkboxes did not toggle (and a sent click could stall GECK until the mouse moved);
  the helper now posts the double-click with the cursor parked over the row. Wine/CrossOver behaviour is unchanged.
- First Windows 11 end-to-end run (status, build, install, live load, cell verify): see `docs/TESTING.md`.

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
