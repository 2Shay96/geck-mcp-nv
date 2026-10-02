# Windows UI-automation server (`geck_nv`): untested FNV port

This folder is a **Fallout: New Vegas port of [GECK MCP for Fallout 3](https://github.com/maksimka2432fr23/codex-skill-mcp-fallout3)**
by **maksimka2432fr23** (MIT). It is a local stdio MCP server with 46 tools. It drives the GECK
window through pywinauto, which means real mouse, keyboard and UI Automation input. It can also back up and patch
placed references in plugin files while GECK is closed.

> **Status: UNTESTED against a real New Vegas GECK.** The port changed paths and names only (see
> [PORT-NOTES.md](PORT-NOTES.md)). The FO3 and FNV editors share most of their UI, but nobody has run this
> against FNV yet. The unit tests pass (23/23 on Linux with MCP SDK 2.2.0). A stdio client listed all 46 tools
> and ran `geck_doctor`. Please report what works.

## What it adds next to the bridge

| Workflow | Tools (examples) |
| --- | --- |
| Diagnose | `geck_doctor`, `geck_list_processes`, `geck_tail_log` |
| Launch | `geck_launch(via_nvse=true)` runs `nvse_loader.exe -editor` |
| Navigate | `geck_cell_select`, `geck_cell_go_to_exterior`, `geck_object_filter` |
| Place objects | `geck_place_object_in_render` (drag from the Object Window), `geck_placement_plan_from_status_bar` |
| Plugins & load order | `geck_list_plugins`, `geck_read_load_order`, `geck_write_load_order` |
| Safety | `geck_transaction_begin`, `geck_transaction_rollback`, `geck_transaction_verify` |
| Placed-ref edits (GECK closed) | `geck_esp_list_refs`, `geck_esp_patch_ref_position`, `geck_esp_delete_refs` |

Full list: [docs/tools.md](docs/tools.md).

## Setup (Windows, PowerShell)

Requirements: Windows 10/11, Python 3.11+, Fallout: New Vegas with GECK installed (NVSE optional).

```powershell
cd <unzipped folder>\windows
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

### Connect an MCP client

**Codex:** merge [examples/codex-config.toml](examples/codex-config.toml) into `~/.codex/config.toml`.

**Claude Desktop / Claude Code:** add to the `mcpServers` section of your config:

```json
"geck_nv": {
  "command": "C:\\Tools\\geck-mcp-for-new-vegas\\windows\\.venv\\Scripts\\python.exe",
  "args": ["-m", "geck_mcp_nv"],
  "cwd": "C:\\Tools\\geck-mcp-for-new-vegas\\windows",
  "env": { "GECK_MCP_FNV_DIR": "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Fallout New Vegas" }
}
```

Optional: copy `skills/geck-mcp` into your agent's skills folder so it learns the safe workflow.

First prompt to try: *"Run geck_doctor and tell me whether GECK is running. Don't modify anything."*

## Configuration

| Environment variable | Purpose |
| --- | --- |
| `GECK_MCP_FNV_DIR` | Your FNV install folder (set it explicitly) |
| `FALLOUTNV_DIR` | Fallback game-folder variable |
| `GECK_MCP_GECK_EXE` / `GECK_MCP_DATA_DIR` | Override GECK.exe / Data paths |
| `GECK_MCP_LOAD_ORDER_FILE` | plugins.txt to use (default `%LOCALAPPDATA%\FalloutNV\plugins.txt`; set this for MO2 profiles) |
| `GECK_MCP_BACKUP_DIR` / `GECK_MCP_SCREENSHOT_DIR` | Output folders (default: under the server's working folder) |

## Safety

- UI tools move the mouse and send keys. Don't use the PC while they run.
- File tools refuse to edit while GECK or the game is running. Back up first (`geck_transaction_begin`).
- Only REFR/ACHR/ACRE placement edits are supported. Compressed records and XXXX subrecords are rejected.

## Licence and credits

MIT. Original work © 2026 maksimka2432fr23 ([LICENSE](LICENSE), unchanged). The FNV port changes are by 2Shay
under the same licence. Not affiliated with Bethesda, Microsoft, OpenAI or Anthropic. No game files are included.
