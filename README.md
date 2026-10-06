# GECK MCP for New Vegas: WIP prototype (v0.2.1)

Download: [Nexus Mods](https://www.nexusmods.com/newvegas/mods/99851?tab=files).

**Let an AI agent (Claude, Codex or any MCP client) build and edit Fallout: New Vegas plugins and drive the GECK.**

> ⚠️ **Work-in-progress prototype.** The `geck` bridge is tested end to end on **Windows 11** with the vanilla
> Steam GECK (see [docs/TESTING.md](docs/TESTING.md)). Linux/Proton is written but untested. Read the status table
> first, back up your Data folder, and use a throwaway plugin.

## What's inside

| Folder | MCP server | What it does | Tested |
| --- | --- | --- | --- |
| [`bridge/`](bridge/README.md) | `geck` (25 tools) | **Builds whole plugins from a JSON spec** (records, cells, placed objects, stable FormIDs) without GECK. **Compiles scripts with GECK's own compiler** and caches the bytecode. Loads plugins in GECK, checks cells against the build, sets models, saves with backups. Also actor photos and animated sprite billboards. | ✅ Windows 11 (vanilla GECK) · ❓ Linux/Proton · also tested on Mac via CrossOver |
| [`windows/`](windows/README.md) | `geck_nv` (46 tools) | **FNV port of [GECK MCP for Fallout 3](https://github.com/maksimka2432fr23/codex-skill-mcp-fallout3)** by maksimka2432fr23. Windows UI automation: launch GECK through NVSE, navigate Cell View and the Object Window, drag objects into the Render Window, load order, transactions and rollback, placed-reference patches. | ❓ Windows (not yet run against the FNV GECK) |

You can run either server on its own, or both at once (their tool names don't overlap).

## Why it exists

The GECK is a 2010 GUI editor with no scripting interface. Other AI modding kits edit plugins through xEdit
and leave the GECK to you. This project gives an agent the GECK itself: loading, verifying, saving and
compiling scripts. It also adds an offline builder, so the agent can write a whole mod as a readable spec.

It is being used to make a real mod: *Salvatore Ganacci*, a sprite-based creature boss with its own skeleton,
scripts and quests. It was built from a spec and compiled through the bridge, and the boss already pursues and
fights the player in game.

## Quick start

1. Read [`bridge/README.md`](bridge/README.md) (any OS), [`windows/README.md`](windows/README.md) (Windows), or both.
2. Install Python 3.12+ and create a virtual environment in the folder you'll use.
3. Nexus download: build the GECK helper once with `build_helper.py` (see [`bridge/README.md`](bridge/README.md), step 3).
   The download contains source only, no `.exe`; GitHub has a prebuilt one.
4. Register the server in your MCP client (examples are in each README).
5. First prompt: *"Run geck_status (or geck_doctor) and tell me what you see. Don't change anything."*

## Requirements

- Fallout: New Vegas and its GECK (Steam: Library → Tools). This package contains **no** game files, GECK or ESM data.
  Each user builds their own master index locally.
- Python 3.12+ and an MCP client.
- Optional: NVSE (for `geck_launch(via_nvse=true)`). PyFFI for the sprite tools installs with `bridge/requirements.lock.txt`.

## Safety

- Every tool that writes makes backups first. Read-only tools are labelled.
- The bridge refuses to load plugins over unsaved GECK work. The Windows server refuses file edits while GECK or the game runs.
- Windows UI tools move your mouse and type. Don't use the PC while they run.
- Report problems. Don't trust results you haven't checked in GECK or in game.

## Status and roadmap

v0.2 is a portfolio/prototype release. 0.2.0 fixed what broke while building a real mod on Windows: tools now work
through Claude's Cowork device proxy, hidden GECK windows are restored, stale recovery barriers clear themselves after
a GECK restart, and the Render Window can be captured on Windows. Next steps: a GECK Extender pass, running the
`windows/` server against the FNV GECK, a Linux/Proton test, DLC masters, and one combined installer. See
[CHANGELOG.md](CHANGELOG.md).

## Licence and credits

- MIT. See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
- `bridge/` © 2026 2Shay. `windows/` © 2026 maksimka2432fr23, with the FNV port by 2Shay.
- Made with AI coding agents (Anthropic Claude and OpenAI Codex), directed and tested by 2Shay.
- Not affiliated with or endorsed by Bethesda Softworks, ZeniMax, Microsoft, Anthropic or OpenAI.
  Fallout and G.E.C.K. are trademarks of their owners.
