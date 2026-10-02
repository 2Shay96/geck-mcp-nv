# Changelog

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
