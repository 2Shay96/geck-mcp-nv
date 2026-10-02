# Port notes: Fallout 3 → Fallout: New Vegas

Upstream: https://github.com/maksimka2432fr23/codex-skill-mcp-fallout3, commit `b3c1044a` (2026-09-06), MIT.

## Changes
- Package `geck_mcp` → `geck_mcp_nv`. Command `geck-mcp-nv`, MCP server name `geck-mcp-nv`.
  This avoids clashing with the bridge's `geck_mcp` package.
- Default game folder: `...\steamapps\common\Fallout New Vegas`.
  Variables `GECK_MCP_FALLOUT3_DIR` / `FALLOUT3_DIR` → `GECK_MCP_FNV_DIR` / `FALLOUTNV_DIR`.
- Load order: `%LOCALAPPDATA%\Fallout3\plugins.txt` → `%LOCALAPPDATA%\FalloutNV\plugins.txt`.
- Script extender: FOSE → NVSE (`nvse_loader.exe -editor`). `geck_launch(via_fose)` → `geck_launch(via_nvse)`.
  The log allowlist is now `EditorWarnings.txt`, `nvse.log`, `nvse_loader.log` and `nvse_editor.log`.
- MCP SDK: works with 1.x (`FastMCP`) and 2.x (`MCPServer`). The `<2` pin was removed so the bridge and this
  server can share one Python environment.
- User-facing text and docs say Fallout: New Vegas. The Russian README was removed because it was not updated.

## Unchanged and unverified on FNV
- Window titles (`Garden of Eden Creation Kit`, `Cell View`, `Object Window`) and the Render Window title regex
  `[Free camera, perspective]`.
- Status-bar parsing, the Cell View/Object Window control layout, the File > Data dialog flow and the Save dialog flow.
- Behaviour with **GECK Extender** installed.
- The ESP walker: FNV uses the same 24-byte record/group headers as FO3, but it has not been tested on FNV plugins yet.

## Verified here
- `python -m unittest discover -s tests`: 23 passed (Linux, Python 3.13, MCP SDK 2.2.0; the UI tools are Windows-only).
- A real stdio MCP client listed 46 tools and ran `geck_doctor`.
